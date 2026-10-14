<?php
/**
 * AI access gate (Phase 13, ADR-077).
 *
 * Enforces the merchant's free / paid / forbidden decision at the edge of
 * the site, and publishes it in the two machine-readable places agents
 * actually look: `robots.txt` and a `/.well-known/ai-policy` document.
 *
 * WHY THE DECISION IS CACHED LOCALLY RATHER THAN ASKED EACH TIME
 *
 * This runs on `template_redirect`, on every request, on shared hosting.
 * An HTTP round trip to Cloud Core there would put Core's latency on
 * every page load and Core's uptime on the merchant's. So the policy
 * table is cached and evaluated in PHP.
 *
 * That means the same rule is implemented twice, which is a duplication
 * risk with a real failure mode: the edge blocks one thing while the
 * report shows another. Three things hold it together, and none of them
 * is "we'll be careful":
 *
 *   1. Core stays authoritative. `GET /telemetry/access-decision`
 *      returns the real answer, and the plugin's copy is a cache with a
 *      TTL, not a fork.
 *   2. The signature list is generated FROM Core's canonical list and a
 *      test in each runtime asserts the two are identical.
 *   3. Every enforced decision is reported back in the page-view event,
 *      so a disagreement between edge and Core is visible in the data
 *      rather than invisible in the code.
 *
 * WHAT THIS GATE HONESTLY CANNOT DO
 *
 * It identifies agents by User-Agent header, which is a claim, not an
 * identity. It therefore stops honest agents and does not stop dishonest
 * ones. That is stated on the dashboard rather than buried here, because
 * a merchant who believes "Forbidden" means "cannot" has been misled by
 * their own admin screen.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Access_Gate
{
    public const CACHE_KEY = 'aiol_access_policies';
    public const CACHE_TTL = 900; // 15 minutes
    public const CRON_HOOK = 'aiol_access_policy_refresh';

    public const FREE      = 'free';
    public const PAID      = 'paid';
    public const FORBIDDEN = 'forbidden';
    public const UNSET     = 'unset';

    private AIOL_Client $client;
    private AIOL_Logger $logger;

    public function __construct(AIOL_Client $client, AIOL_Logger $logger)
    {
        $this->client = $client;
        $this->logger = $logger;
    }

    public function register(): void
    {
        if (!self::is_enabled()) {
            return;
        }
        // Priority 5: after AIOL_Actors has observed (priority 1) so the
        // request is still recorded even when it is about to be refused,
        // and before AIOL_Telemetry buffers at 20 so the buffered event
        // carries the decision that was actually enforced.
        add_action('template_redirect', [$this, 'enforce'], 5);
        add_filter('robots_txt', [$this, 'robots_txt'], 10, 2);
        add_action('init', [$this, 'register_policy_endpoint']);

        // The cron that keeps the enforced-at-the-edge cache from Core.
        // Without this, `policies()` reads an empty transient forever and
        // every request silently evaluates against zero rules — which
        // is indistinguishable from "not configured" and was caught only
        // by tracing register() end to end, not by any earlier test,
        // because no test exercised the cron wiring itself.
        add_action(self::CRON_HOOK, [$this, 'refresh']);
        if (!wp_next_scheduled(self::CRON_HOOK)) {
            wp_schedule_event(time() + 30, 'aiol_fifteen_minutes', self::CRON_HOOK);
        }
        // Prime the cache on the very next request rather than waiting up
        // to 15 minutes for the first cron tick, if nothing is cached yet.
        if (get_transient(self::CACHE_KEY) === false) {
            add_action('init', [$this, 'refresh'], 20);
        }
    }

    public static function is_enabled(): bool
    {
        $settings = get_option('aiol_settings', []);
        // OFF by default. Turning a site's AI access control on without
        // the merchant choosing it could remove them from answer surfaces
        // overnight. An unmade decision must never behave like a decision.
        return is_array($settings) && !empty($settings['access_gate']);
    }

    // -----------------------------------------------------------------
    // Enforcement
    // -----------------------------------------------------------------

    public function enforce(): void
    {
        $ua = isset($_SERVER['HTTP_USER_AGENT'])
            ? sanitize_text_field(wp_unslash((string) $_SERVER['HTTP_USER_AGENT']))
            : '';

        $actor = AIOL_Actors::classify($ua);

        // Humans are never gated. Not a special case bolted on: the whole
        // table is about machine access, and no configuration should be
        // able to return 403 to a customer's browser.
        if ($actor['type'] === AIOL_Actors::HUMAN) {
            return;
        }

        $decision = self::evaluate($actor, self::policies());
        $GLOBALS['aiol_access_decision'] = $decision;

        if ($decision['tier'] === self::FORBIDDEN) {
            $this->refuse(403, $decision);
        }
        if ($decision['tier'] === self::PAID) {
            $this->refuse(402, $decision);
        }
    }

    /**
     * Pure evaluation — no WordPress, no I/O, unit-testable, and the
     * direct counterpart of `access_policy_service.evaluate()`.
     *
     * Four precedence levels, most specific first, FIRST MATCH WINS and
     * evaluation stops. No scoring and no "strictest wins": the merchant
     * must be able to read the table and predict the outcome, and an
     * algorithm that blends rows cannot be read.
     *
     * @param array{type:string,label?:string,signature?:?string,confidence?:string} $actor
     *        'signature', when the caller already knows Core's canonical
     *        signature key (e.g. reading AiAgent records for the
     *        dashboard), is used directly. Only when absent is it
     *        re-derived from 'label' via a reverse lookup against the
     *        canonical table — the path `enforce()` uses, because a raw
     *        User-Agent classification produces a label, not a signature
     *        key. Skipping the direct path for dashboard reads was a real
     *        bug: a merchant-renamed agent's label no longer matches the
     *        canonical table, silently disabling agent-level policy rows.
     * @param array<int,array> $policies
     * @return array{tier:string,reason:?string,terms_url:?string,policy_id:?string,decision:string}
     */
    public static function evaluate(array $actor, array $policies): array
    {
        $signature = self::signature_for($actor);
        $purpose   = AIOL_Actors::purpose_for($actor['type'], $signature);

        $levels = [
            ['signature' => $signature, 'purpose' => $purpose],
            ['signature' => $signature, 'purpose' => null],
            ['actor_type' => $actor['type'], 'purpose' => $purpose],
            ['actor_type' => $actor['type'], 'purpose' => null],
        ];

        foreach ($levels as $want) {
            foreach ($policies as $policy) {
                if (!self::matches($policy, $want)) {
                    continue;
                }
                $tier = (string) ($policy['tier'] ?? self::UNSET);
                return [
                    'tier'      => $tier,
                    'decision'  => self::decision_for($tier),
                    'reason'    => $policy['reason'] ?? null,
                    'terms_url' => $policy['terms_url'] ?? null,
                    'policy_id' => $policy['id'] ?? null,
                ];
            }
        }

        // No rule matched. NOT "allowed" — nobody decided, and the
        // dashboard counts these precisely so the absence stays visible
        // instead of hardening into de-facto policy.
        return [
            'tier'      => self::UNSET,
            'decision'  => 'not_configured',
            'reason'    => null,
            'terms_url' => null,
            'policy_id' => null,
        ];
    }

    private static function matches(array $policy, array $want): bool
    {
        $policy_purpose = $policy['purpose'] ?? null;
        if (($want['purpose'] ?? null) !== $policy_purpose) {
            return false;
        }
        if (isset($want['signature'])) {
            return ($policy['agent_signature'] ?? null) === $want['signature']
                && ($policy['actor_type'] ?? null) === null;
        }
        return ($policy['actor_type'] ?? null) === ($want['actor_type'] ?? null)
            && ($policy['agent_signature'] ?? null) === null;
    }

    private static function decision_for(string $tier): string
    {
        switch ($tier) {
            case self::FREE:      return 'allowed';
            case self::PAID:      return 'payment_required';
            case self::FORBIDDEN: return 'blocked';
            // UNSET behaves exactly like no rule at all. "I created the
            // row but haven't chosen yet" must not read as "I allowed it".
            default:              return 'not_configured';
        }
    }

    private static function signature_for(array $actor): ?string
    {
        if (array_key_exists('signature', $actor)) {
            return $actor['signature'];
        }
        return AIOL_Actors::signature_for_label($actor['label'] ?? '');
    }

    /**
     * Refuse, in a way an agent operator can act on.
     *
     * A bare 403 with no body tells a well-behaved crawler nothing about
     * whether to come back, and tells a human operator investigating it
     * nothing at all. The reason and the terms link are the difference
     * between a policy and a wall.
     */
    private function refuse(int $status, array $decision): void
    {
        nocache_headers();
        status_header($status);
        header('Content-Type: text/plain; charset=utf-8');
        header('X-AIOL-Access-Decision: ' . $decision['decision']);

        if (!empty($decision['terms_url'])) {
            header('Link: <' . esc_url_raw((string) $decision['terms_url']) . '>; rel="terms-of-service"');
        }

        $reason = $decision['reason'] !== null && $decision['reason'] !== ''
            ? (string) $decision['reason']
            : ($status === 402
                ? __('Automated access to this site requires a licence.', 'ai-operating-layer')
                : __('Automated access to this site is not permitted for this purpose.', 'ai-operating-layer'));

        echo esc_html($reason) . "\n";
        if (!empty($decision['terms_url'])) {
            echo esc_url_raw((string) $decision['terms_url']) . "\n";
        }
        exit;
    }

    // -----------------------------------------------------------------
    // Policy cache
    // -----------------------------------------------------------------

    /** @return array<int,array> */
    public static function policies(): array
    {
        $cached = get_transient(self::CACHE_KEY);
        return is_array($cached) ? $cached : [];
    }

    /**
     * Refresh the cache from Cloud Core.
     *
     * On failure the PREVIOUS cache is kept rather than cleared. Clearing
     * would mean a Core outage silently opens a site the merchant chose
     * to close — the failure mode with the worse consequence, so it is
     * the one not chosen.
     */
    public function refresh(): bool
    {
        $response = $this->client->list_access_policies(200);
        if (is_wp_error($response) || !isset($response['items'])) {
            $this->logger->error('Access policy refresh failed; keeping the previous cache.');
            return false;
        }
        set_transient(self::CACHE_KEY, $response['items'], self::CACHE_TTL);
        return true;
    }

    // -----------------------------------------------------------------
    // Machine-readable publication
    // -----------------------------------------------------------------

    /**
     * robots.txt lines derived from the policy table.
     *
     * Only FORBIDDEN produces a `Disallow`. PAID does not: `robots.txt`
     * has no vocabulary for "you may, for a fee", and writing Disallow
     * there would tell an agent the answer is no when the merchant's
     * answer is "ask". The 402 and the policy document carry that.
     */
    public function robots_txt(string $output, $public): string
    {
        $lines = [];
        foreach (self::policies() as $policy) {
            if (($policy['tier'] ?? '') !== self::FORBIDDEN) {
                continue;
            }
            $signature = $policy['agent_signature'] ?? null;
            if ($signature === null) {
                continue; // an actor-type rule has no single UA to name
            }
            $lines[] = 'User-agent: ' . $signature;
            $lines[] = 'Disallow: /';
            $lines[] = '';
        }
        if ($lines === []) {
            return $output;
        }
        return $output . "\n# AI Operating Layer — AI access policy\n" . implode("\n", $lines);
    }

    public function register_policy_endpoint(): void
    {
        add_rewrite_rule('^\.well-known/ai-policy$', 'index.php?aiol_ai_policy=1', 'top');
        add_filter('query_vars', static function (array $vars): array {
            $vars[] = 'aiol_ai_policy';
            return $vars;
        });
        add_action('template_redirect', [$this, 'render_policy_document'], 1);
    }

    /**
     * The full policy, including the tiers robots.txt cannot express.
     * Machine-readable, and deliberately states what is NOT known — an
     * agent reading this should be able to tell "we decided to allow you"
     * from "nobody has decided about you".
     */
    public function render_policy_document(): void
    {
        if (get_query_var('aiol_ai_policy') !== '1') {
            return;
        }
        $rules = [];
        foreach (self::policies() as $policy) {
            $rules[] = [
                'applies_to' => $policy['agent_signature'] ?? ($policy['actor_type'] ?? null),
                'subject_kind' => isset($policy['agent_signature']) ? 'agent' : 'actor_type',
                'purpose'    => $policy['purpose'] ?? 'any',
                'decision'   => $policy['tier'] ?? self::UNSET,
                'reason'     => $policy['reason'] ?? null,
                'terms_url'  => $policy['terms_url'] ?? null,
            ];
        }

        nocache_headers();
        header('Content-Type: application/json; charset=utf-8');
        echo wp_json_encode([
            'version' => 1,
            'site'    => home_url('/'),
            'generated_at' => gmdate('c'),
            'default_when_no_rule_matches' => 'allowed_but_undecided',
            'notes' => [
                'Identification is by User-Agent header, which is self-reported and not verified.',
                'A decision of "unset" means no rule matched: access is not refused, and no permission has been granted either.',
                '"paid" indicates a licence is required; this document records intent and performs no metering or billing.',
            ],
            'rules' => $rules,
        ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        exit;
    }
}
