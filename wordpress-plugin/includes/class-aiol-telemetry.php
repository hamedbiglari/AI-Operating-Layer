<?php
/**
 * Phase 13 telemetry collector (ADR-078 / ADR-079).
 *
 * WHAT THIS CLASS IS ALLOWED TO DO
 *
 * Observe a request, buffer it, and ship it to Cloud Core. Nothing else.
 * It makes no decision, computes no aggregate and holds no opinion about
 * what the traffic means — Core owns all of that (§52). If this file
 * starts counting things, a second source of truth has been born.
 *
 * WHY IT DOES NOT CALL CORE ON EVERY REQUEST
 *
 * Because it runs on `shutdown`, on an ordinary shared host, on every
 * page load. A synchronous HTTP call there would put Cloud Core's latency
 * on the merchant's critical path and their uptime on Cloud Core's. So
 * observations go into a bounded buffer and a cron slice flushes them —
 * the same "no storm, no silent loss" contract Phase 10 arrived at the
 * hard way (ADR-054).
 *
 * WHAT IT COLLECTS, AND THE HISTORY OF THAT
 *
 * IP address, coarse geography and dwell time — all three of which
 * `AIOL_Actors` deliberately refused to collect (ADR-046), and which the
 * pre-Phase-13 checkpoint (§P.5) explicitly left as an owner decision
 * rather than closing by default. The owner has now decided to collect
 * them. ADR-079 records that; ADR-046 stays on file unedited. The cost is
 * bounded rather than waved away:
 *
 *   - the query string is never stored (inherited from ADR-046);
 *   - Core truncates every address to /24 or /48 on write and destroys
 *     the full address at a retention horizon;
 *   - no cross-session visitor identifier is minted, here or anywhere;
 *   - nothing infers a psychological state or a purchase-readiness
 *     label from any of it — checkpoint §76/§77 stands, unchanged.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Telemetry
{
    public const BUFFER_OPTION = 'aiol_telemetry_buffer';
    public const CRON_HOOK     = 'aiol_telemetry_flush';

    /** Bounded. An adapter buffer that grows without limit is a
     *  denial-of-service against the merchant's own database. */
    public const MAX_BUFFERED = 500;
    public const BATCH_SIZE   = 200;

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
        add_action('template_redirect', [$this, 'observe'], 20);
        add_action('wp_enqueue_scripts', [$this, 'enqueue_beacon']);
        add_action('wp_ajax_nopriv_aiol_dwell', [$this, 'receive_dwell']);
        add_action('wp_ajax_aiol_dwell', [$this, 'receive_dwell']);
        add_action(self::CRON_HOOK, [$this, 'flush']);

        if (!wp_next_scheduled(self::CRON_HOOK)) {
            wp_schedule_event(time() + 60, 'aiol_five_minutes', self::CRON_HOOK);
        }
    }

    public static function is_enabled(): bool
    {
        $settings = get_option('aiol_settings', []);
        return !is_array($settings) || ($settings['telemetry'] ?? true);
    }

    // -----------------------------------------------------------------
    // Observation
    // -----------------------------------------------------------------

    public function observe(): void
    {
        $ua = isset($_SERVER['HTTP_USER_AGENT'])
            ? sanitize_text_field(wp_unslash((string) $_SERVER['HTTP_USER_AGENT']))
            : '';

        $actor = AIOL_Actors::classify($ua);
        $event_key = self::event_key();

        $event = [
            'event_key'   => $event_key,
            'occurred_at' => gmdate('c'),
            // Path only. AIOL_Actors::safe_path() already strips the query
            // string; reusing it rather than re-implementing keeps one
            // definition of "what part of a URL is safe to store".
            'path'        => AIOL_Actors::safe_path(),
            'user_agent'  => mb_substr($ua, 0, 400),
            'status_code' => is_404() ? 404 : 200,
        ];

        $event += self::content_context();
        $event += AIOL_Geo::for_request();

        // Dwell is deliberately absent here. It is not knowable at the
        // moment the page is served, and writing 0 now and correcting it
        // later would mean every crawler view carries a fabricated zero
        // that nothing ever comes back to fix.

        self::buffer($event);

        // The beacon needs the key to attach a dwell measurement to the
        // right observation later.
        $GLOBALS['aiol_current_event_key'] = $event_key;
    }

    /**
     * Title and type of whatever is being viewed, so a report can say
     * "this article" rather than "/?p=1423". Core is told the type as a
     * free-text label and is not asked to understand WordPress routing.
     */
    private static function content_context(): array
    {
        if (is_singular()) {
            $post = get_queried_object();
            if ($post instanceof WP_Post) {
                return [
                    'content_type'  => (string) $post->post_type,
                    'content_title' => mb_substr((string) get_the_title($post), 0, 500),
                ];
            }
        }
        if (is_archive()) {
            return ['content_type' => 'archive'];
        }
        if (is_search()) {
            return ['content_type' => 'search'];
        }
        if (is_front_page()) {
            return ['content_type' => 'front_page'];
        }
        return [];
    }

    private static function event_key(): string
    {
        return bin2hex(random_bytes(16));
    }

    // -----------------------------------------------------------------
    // Dwell beacon
    // -----------------------------------------------------------------

    public function enqueue_beacon(): void
    {
        if (empty($GLOBALS['aiol_current_event_key'])) {
            return;
        }
        wp_enqueue_script(
            'aiol-dwell',
            AIOL_PLUGIN_URL . 'assets/js/aiol-dwell.js',
            [],
            AIOL_VERSION,
            true
        );
        wp_localize_script('aiol-dwell', 'AIOL_DWELL', [
            'ajaxUrl'  => admin_url('admin-ajax.php'),
            'eventKey' => (string) $GLOBALS['aiol_current_event_key'],
            'nonce'    => wp_create_nonce('aiol_dwell'),
        ]);
    }

    /**
     * A visitor's browser reporting how long the page stayed visible.
     *
     * Only ever UPGRADES a buffered event. It cannot create one, so a
     * forged beacon cannot invent traffic, and it cannot lower a value,
     * so a reload cannot shrink a measured visit.
     */
    public function receive_dwell(): void
    {
        check_ajax_referer('aiol_dwell', 'nonce');

        $key = isset($_POST['event_key']) ? sanitize_text_field(wp_unslash((string) $_POST['event_key'])) : '';
        $ms  = isset($_POST['dwell_ms']) ? absint($_POST['dwell_ms']) : 0;
        $complete = !empty($_POST['complete']);

        // 24 hours. Above that the number is a sleeping laptop, not a
        // reader, and storing it would drag every average it touches.
        if ($key === '' || $ms <= 0 || $ms > 86400000) {
            wp_send_json_success(['recorded' => false]);
        }

        $buffer = self::buffered();
        foreach ($buffer as $i => $event) {
            if (($event['event_key'] ?? '') !== $key) {
                continue;
            }
            if (($event['dwell_ms'] ?? 0) < $ms) {
                $buffer[$i]['dwell_ms'] = $ms;
                $buffer[$i]['dwell_is_complete'] = $complete;
                update_option(self::BUFFER_OPTION, $buffer, false);
            }
            wp_send_json_success(['recorded' => true]);
        }
        wp_send_json_success(['recorded' => false]);
    }

    // -----------------------------------------------------------------
    // Buffer and flush
    // -----------------------------------------------------------------

    public static function buffered(): array
    {
        $buffer = get_option(self::BUFFER_OPTION, []);
        return is_array($buffer) ? $buffer : [];
    }

    public static function buffer(array $event): void
    {
        $buffer = self::buffered();
        $buffer[] = $event;

        // Drop the OLDEST when full, not the newest. A full buffer means
        // the flush is failing; in that situation recent traffic is what
        // the operator needs to see, and the loss is recorded rather than
        // silent.
        if (count($buffer) > self::MAX_BUFFERED) {
            $dropped = count($buffer) - self::MAX_BUFFERED;
            $buffer = array_slice($buffer, $dropped);
            update_option('aiol_telemetry_dropped', (int) get_option('aiol_telemetry_dropped', 0) + $dropped, false);
        }
        update_option(self::BUFFER_OPTION, $buffer, false);
    }

    /**
     * Ship one batch. Events are removed from the buffer ONLY after Core
     * has accepted them; a failed flush leaves them in place and the next
     * cron slice retries. Because every event carries a client-minted
     * `event_key` and Core deduplicates on it, a retry that Core already
     * received is counted once, not twice.
     */
    public function flush(): int
    {
        $buffer = self::buffered();
        if ($buffer === []) {
            return 0;
        }

        $batch = array_slice($buffer, 0, self::BATCH_SIZE);
        $response = $this->client->ingest_page_views($batch);

        if (is_wp_error($response)) {
            $this->logger->error(
                'Telemetry batch failed: ' . $response->get_error_message()
                . ' — ' . count($batch) . ' events queued for retry'
            );
            return 0;
        }

        $remaining = array_slice($buffer, count($batch));
        update_option(self::BUFFER_OPTION, $remaining, false);

        $accepted = (int) ($response['accepted'] ?? 0);
        $duplicates = (int) ($response['duplicates'] ?? 0);
        $this->logger->info(
            "Telemetry batch accepted: {$accepted} events, {$duplicates} duplicates"
        );
        return $accepted;
    }

    /**
     * Clears the adapter's own buffer. Deliberately does NOT touch
     * anything in Cloud Core: page views, agents and access decisions are
     * the analytics record, and a "clear log" button that quietly erased
     * them would be a destructive action wearing a harmless label.
     */
    public static function clear_buffer(): void
    {
        delete_option(self::BUFFER_OPTION);
        delete_option('aiol_telemetry_dropped');
    }
}
