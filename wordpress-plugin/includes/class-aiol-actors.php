<?php
/**
 * Actor detection — absorbed and rebuilt from the legacy bot monitor
 * (capability map #14, #15; ADR-046).
 *
 * WHY THIS IS NOT A "BOT MONITOR"
 *
 * The legacy module matched 18 User-Agent strings and logged "GPTBot
 * visited". Two things are wrong with that framing, and both matter more
 * as agentic traffic grows:
 *
 * 1. **A User-Agent is a claim, not an identity.** Anyone can send
 *    `ClaudeBot`. Presenting a header match as fact is the same error as
 *    treating unverified evidence as verified — the thing this whole
 *    architecture exists to avoid. So every observation carries a
 *    CONFIDENCE, and header-only matches are DETECTED, never VERIFIED.
 *
 * 2. **"Bot vs human" is the wrong axis.** A crawler indexing for later,
 *    an AI answering a user's question right now, and an agent acting on a
 *    user's behalf are three different things with three different business
 *    meanings. Phase 10+ will care about the third; a boolean cannot
 *    express it.
 *
 * PRIVACY (narrowed from legacy, deliberately)
 *
 * The legacy log stored IP address and full request URI. This one stores
 * neither: no IP, no query string, path only, User-Agent truncated. An
 * adapter log is not an analytics product, and storing less is the only
 * reliable way not to leak more.
 *
 * `aiol_actor_observed` fires for every observation so a future phase can
 * consume the signal without this class growing an opinion about it.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Actors
{
    public const OPTION      = 'aiol_actor_log';
    public const MAX_ENTRIES = 200;

    // --- Actor types -------------------------------------------------------
    public const HUMAN          = 'human';
    public const SEARCH_CRAWLER = 'search_crawler';
    public const AI_CRAWLER     = 'ai_crawler';      // indexes for later training/answers
    public const AI_USER_AGENT  = 'ai_user_agent';   // fetching for a user's live question
    public const AGENT_TOOL     = 'agent_tool';      // acting on a user's behalf
    public const UNKNOWN        = 'unknown';

    // --- Confidence --------------------------------------------------------
    public const DETECTED = 'detected';   // header matched a known signature
    public const PROBABLE = 'probable';   // heuristic, weaker signal
    public const VERIFIED = 'verified';   // reverse-DNS/IP confirmed - NOT implemented
    public const CONF_UNKNOWN = 'unknown';

    /**
     * Signature => [actor type, label]. Inherited from the legacy list and
     * extended, but reclassified: the legacy version called all of these
     * "AI bots". `ChatGPT-User`, `Claude-User` and `Perplexity-User` are
     * sent when a PERSON asked a question, which is a different actor with
     * different commercial meaning.
     */
    /**
     * Signature => [actor type, label, purpose].
     *
     * PHASE 13: THIS BLOCK IS GENERATED, NOT HAND-MAINTAINED.
     *
     * The canonical list lives in
     * `cloud-core/app/services/actor_signatures.py`. Two runtimes
     * classifying the same traffic from two hand-typed lists is how the
     * edge ends up blocking one thing while the report shows another,
     * and the merchant's access policy silently stops matching. So this
     * block is generated from the canonical list by
     * `scripts/sync-signatures.php`, and `tests/test-signature-parity.php`
     * plus `test_phase13_signature_parity` make any drift a test failure
     * rather than a code-review responsibility.
     *
     * ORDER IS LOAD-BEARING. Matching is first-hit, so `Claude-SearchBot`
     * and `Claude-User` MUST precede `ClaudeBot`: otherwise a customer's
     * live question is classified as a training crawler and a merchant's
     * "block training" rule blocks their own customers.
     */
    private static array $signatures = [
        'Claude-SearchBot' => [self::AI_USER_AGENT, 'Claude-SearchBot (Anthropic)', self::PURPOSE_ANSWERING],
        'Claude-User' => [self::AI_USER_AGENT, 'Claude-User (Anthropic)', self::PURPOSE_ANSWERING],
        'ChatGPT-User' => [self::AI_USER_AGENT, 'ChatGPT-User (OpenAI)', self::PURPOSE_ANSWERING],
        'Perplexity-User' => [self::AI_USER_AGENT, 'Perplexity-User (Perplexity)', self::PURPOSE_ANSWERING],
        'MistralAI-User' => [self::AI_USER_AGENT, 'MistralAI-User (Mistral)', self::PURPOSE_ANSWERING],
        'DuckAssistBot' => [self::AI_USER_AGENT, 'DuckAssistBot (DuckDuckGo)', self::PURPOSE_ANSWERING],
        'OAI-SearchBot' => [self::AI_CRAWLER, 'OAI-SearchBot (OpenAI)', self::PURPOSE_SEARCH_INDEXING],
        'GPTBot' => [self::AI_CRAWLER, 'GPTBot (OpenAI)', self::PURPOSE_TRAINING],
        'ClaudeBot' => [self::AI_CRAWLER, 'ClaudeBot (Anthropic)', self::PURPOSE_TRAINING],
        'anthropic-ai' => [self::AI_CRAWLER, 'anthropic-ai (Anthropic)', self::PURPOSE_TRAINING],
        'PerplexityBot' => [self::AI_CRAWLER, 'PerplexityBot (Perplexity)', self::PURPOSE_SEARCH_INDEXING],
        'Google-Extended' => [self::AI_CRAWLER, 'Google-Extended (Google)', self::PURPOSE_TRAINING],
        'Applebot-Extended' => [self::AI_CRAWLER, 'Applebot-Extended (Apple)', self::PURPOSE_TRAINING],
        'Bytespider' => [self::AI_CRAWLER, 'Bytespider (ByteDance)', self::PURPOSE_TRAINING],
        'CCBot' => [self::AI_CRAWLER, 'CCBot (Common Crawl)', self::PURPOSE_TRAINING],
        'Amazonbot' => [self::AI_CRAWLER, 'Amazonbot (Amazon)', self::PURPOSE_UNKNOWN],
        'meta-externalagent' => [self::AI_CRAWLER, 'meta-externalagent (Meta)', self::PURPOSE_TRAINING],
        'FacebookBot' => [self::AI_CRAWLER, 'FacebookBot (Meta)', self::PURPOSE_TRAINING],
        'Diffbot' => [self::AI_CRAWLER, 'Diffbot (Diffbot)', self::PURPOSE_UNKNOWN],
        'YouBot' => [self::AI_CRAWLER, 'YouBot (You.com)', self::PURPOSE_SEARCH_INDEXING],
        'cohere-ai' => [self::AI_CRAWLER, 'cohere-ai (Cohere)', self::PURPOSE_TRAINING],
        'Timpibot' => [self::AI_CRAWLER, 'Timpibot (Timpi)', self::PURPOSE_TRAINING],
        'omgili' => [self::AI_CRAWLER, 'omgili (Webz.io)', self::PURPOSE_TRAINING],
        'ImagesiftBot' => [self::AI_CRAWLER, 'ImagesiftBot (Hive)', self::PURPOSE_TRAINING],
        'OpenAI-Operator' => [self::AGENT_TOOL, 'OpenAI Operator (OpenAI)', self::PURPOSE_AGENT_ACTION],
        'Claude-Agent' => [self::AGENT_TOOL, 'Claude Agent (Anthropic)', self::PURPOSE_AGENT_ACTION],
        'Googlebot' => [self::SEARCH_CRAWLER, 'Googlebot (Google)', self::PURPOSE_SEARCH_INDEXING],
        'bingbot' => [self::SEARCH_CRAWLER, 'Bingbot (Microsoft)', self::PURPOSE_SEARCH_INDEXING],
        'DuckDuckBot' => [self::SEARCH_CRAWLER, 'DuckDuckBot (DuckDuckGo)', self::PURPOSE_SEARCH_INDEXING],
        'Slurp' => [self::SEARCH_CRAWLER, 'Yahoo Slurp (Yahoo)', self::PURPOSE_SEARCH_INDEXING],
        'YandexBot' => [self::SEARCH_CRAWLER, 'YandexBot (Yandex)', self::PURPOSE_SEARCH_INDEXING],
        'Baiduspider' => [self::SEARCH_CRAWLER, 'Baiduspider (Baidu)', self::PURPOSE_SEARCH_INDEXING],
        'Twitterbot' => [self::SEARCH_CRAWLER, 'Twitterbot (X)', self::PURPOSE_PREVIEW],
        'Slackbot' => [self::SEARCH_CRAWLER, 'Slackbot (Slack)', self::PURPOSE_PREVIEW],
        'WhatsApp' => [self::SEARCH_CRAWLER, 'WhatsApp (Meta)', self::PURPOSE_PREVIEW],
        'TelegramBot' => [self::SEARCH_CRAWLER, 'TelegramBot (Telegram)', self::PURPOSE_PREVIEW],
    ];

    public function register(): void
    {
        if (!self::is_enabled()) {
            return;
        }
        add_action('template_redirect', [$this, 'observe'], 1);
    }

    public static function is_enabled(): bool
    {
        $settings = get_option('aiol_settings', []);
        return !is_array($settings) || ($settings['actor_logging'] ?? true);
    }

    /**
     * Pure classification — no WordPress, no I/O, unit-testable.
     *
     * @return array{type:string,label:string,confidence:string}
     */
    public static function classify(string $user_agent): array
    {
        $ua = trim($user_agent);
        if ($ua === '') {
            return self::actor(self::UNKNOWN, __('No user agent', 'ai-operating-layer'), self::CONF_UNKNOWN);
        }

        foreach (self::$signatures as $needle => [$type, $label]) {
            if (stripos($ua, $needle) !== false) {
                // DETECTED, never VERIFIED: a header is a claim. Verifying
                // it needs reverse DNS or published IP ranges, which this
                // adapter does not do (ADR-046).
                return self::actor($type, $label, self::DETECTED);
            }
        }

        // Weak heuristic, explicitly PROBABLE rather than asserted.
        //
        // NOTE the deliberate asymmetry in these patterns. Crawler names are
        // overwhelmingly written as one concatenated token ("SomeCrawler",
        // "MyScraperAgent"), so requiring a leading word boundary on those
        // would miss most of them. "bot" is different: a leading boundary IS
        // required, because otherwise "robot", "abbot" and several real
        // browser strings would be misclassified. Found by a test that
        // expected SomeRandomCrawler/1.0 to be PROBABLE and got UNKNOWN.
        if (preg_match('/(crawler|spider|scraper)/i', $ua) || preg_match('/\bbot\b|bot\//i', $ua)) {
            return self::actor(self::UNKNOWN, __('Unrecognised automated client', 'ai-operating-layer'), self::PROBABLE);
        }
        if (preg_match('/\b(Mozilla|Safari|Chrome|Firefox|Edg)\b/', $ua)) {
            return self::actor(self::HUMAN, __('Browser', 'ai-operating-layer'), self::PROBABLE);
        }
        return self::actor(self::UNKNOWN, __('Unrecognised client', 'ai-operating-layer'), self::CONF_UNKNOWN);
    }

    public function observe(): void
    {
        $ua = isset($_SERVER['HTTP_USER_AGENT'])
            ? sanitize_text_field(wp_unslash((string) $_SERVER['HTTP_USER_AGENT']))
            : '';
        $actor = self::classify($ua);

        // Humans are not logged. This log exists to understand machine
        // access; logging ordinary visitors would make it a tracking
        // product, which it is not.
        if ($actor['type'] === self::HUMAN) {
            return;
        }

        self::log($actor, $ua);

        /**
         * Future phases (AI visibility, agentic commerce) consume the signal
         * here rather than this class acquiring opinions about it.
         */
        do_action('aiol_actor_observed', $actor, $ua);
    }

    public static function log(array $actor, string $user_agent): void
    {
        $entries = self::entries();
        array_unshift($entries, [
            'time'       => gmdate('c'),
            'type'       => $actor['type'],
            'label'      => $actor['label'],
            'confidence' => $actor['confidence'],
            // PRIVACY: path only. No IP, no query string, no full URL.
            'path'       => self::safe_path(),
            'ua'         => mb_substr($user_agent, 0, 120),
        ]);
        update_option(self::OPTION, array_slice($entries, 0, self::MAX_ENTRIES), false);
    }

    /** Strips the query string, which can carry personal data. */
    public static function safe_path(): string
    {
        $uri = isset($_SERVER['REQUEST_URI']) ? (string) wp_unslash($_SERVER['REQUEST_URI']) : '';
        $path = (string) strtok($uri, '?');
        return mb_substr(sanitize_text_field($path), 0, 180);
    }

    public static function entries(): array
    {
        $entries = get_option(self::OPTION, []);
        return is_array($entries) ? $entries : [];
    }

    /** Counts by actor type, for the admin summary. */
    public static function summary(): array
    {
        $counts = [];
        foreach (self::entries() as $entry) {
            $type = (string) ($entry['type'] ?? self::UNKNOWN);
            $counts[$type] = ($counts[$type] ?? 0) + 1;
        }
        return $counts;
    }

    public static function type_label(string $type): string
    {
        switch ($type) {
            case self::AI_CRAWLER:     return __('AI crawler (indexing)', 'ai-operating-layer');
            case self::AI_USER_AGENT:  return __('AI answering a user', 'ai-operating-layer');
            case self::AGENT_TOOL:     return __('Agent acting for a user', 'ai-operating-layer');
            case self::SEARCH_CRAWLER: return __('Search crawler', 'ai-operating-layer');
            case self::HUMAN:          return __('Human', 'ai-operating-layer');
            default:                   return __('Unknown', 'ai-operating-layer');
        }
    }

    public static function confidence_label(string $confidence): string
    {
        switch ($confidence) {
            case self::DETECTED: return __('Detected (self-reported)', 'ai-operating-layer');
            case self::PROBABLE: return __('Probable', 'ai-operating-layer');
            case self::VERIFIED: return __('Verified', 'ai-operating-layer');
            default:             return __('Unknown', 'ai-operating-layer');
        }
    }

    public static function clear(): void
    {
        delete_option(self::OPTION);
    }

    private static function actor(string $type, string $label, string $confidence): array
    {
        return ['type' => $type, 'label' => $label, 'confidence' => $confidence];
    }

    // --- Phase 13: purpose vocabulary (mirrors AccessPurpose in Core) ---
    public const PURPOSE_TRAINING        = 'training';
    public const PURPOSE_SEARCH_INDEXING = 'search_indexing';
    public const PURPOSE_ANSWERING       = 'answering';
    public const PURPOSE_AGENT_ACTION    = 'agent_action';
    public const PURPOSE_PREVIEW         = 'preview';
    public const PURPOSE_UNKNOWN         = 'unknown';

    /**
     * The purpose an agent's operator has publicly documented, or
     * `unknown`. Phase 13 addition.
     *
     * `unknown` is a real, usable value, not a placeholder: most clients
     * declare no purpose, and a policy can be written against `unknown`
     * perfectly well. Guessing a purpose would manufacture a fact, and
     * this is the field a merchant's "no training, yes answering" rule
     * turns on - the single place where a wrong guess causes the most
     * damage.
     */
    public static function purpose_for(string $type, ?string $signature): string
    {
        if ($signature !== null && isset(self::$signatures[$signature][2])) {
            return (string) self::$signatures[$signature][2];
        }
        return self::PURPOSE_UNKNOWN;
    }

    /** Reverse lookup used by the access gate: label -> signature key. */
    public static function signature_for_label(string $label): ?string
    {
        foreach (self::$signatures as $needle => $row) {
            if (($row[1] ?? null) === $label) {
                return $needle;
            }
        }
        return null;
    }

    /** Signature keys in canonical order. Used by the parity test. */
    public static function signature_keys(): array
    {
        return array_keys(self::$signatures);
    }
}
