<?php
/**
 * WordPress admin screens.
 *
 * SURFACE ANALYSIS (who/what/why), because the UI follows from it:
 *
 *   User:      a merchant or their developer, non-expert in this system.
 *   Frequency: connection screen once; status screen when something looks
 *              wrong. Both are low-frequency, high-stakes.
 *   Goal:      "is this working, and if not, what do I do?"
 *   Failure:   misreporting health is worse than showing no health at all —
 *              a merchant who trusts a false green light stops looking.
 *
 * That analysis drives three choices: status is broken out per dependency
 * rather than summarised; every error says what to do next, not just what
 * broke; and the primary action on an unconfigured install is the ONLY
 * prominent control, because nothing else is useful yet.
 *
 * SECURITY: every write goes through capability check + nonce. Every value
 * echoed is escaped at the point of output. The token is never rendered.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Admin
{
    private const CAPABILITY = 'manage_options';
    private const NONCE      = 'aiol_settings';

    private AIOL_Client $client;
    private AIOL_Credentials $credentials;
    private AIOL_Cache $cache;
    private AIOL_Logger $logger;
    private ?AIOL_Diagnostics $diagnostics;
    private ?AIOL_Access_Gate $access_gate;
    private ?AIOL_Telemetry $telemetry;

    public function __construct(
        AIOL_Client $client,
        AIOL_Credentials $credentials,
        AIOL_Cache $cache,
        AIOL_Logger $logger,
        ?AIOL_Diagnostics $diagnostics = null,
        ?AIOL_Access_Gate $access_gate = null,
        ?AIOL_Telemetry $telemetry = null
    ) {
        $this->client      = $client;
        $this->credentials = $credentials;
        $this->cache       = $cache;
        $this->logger      = $logger;
        $this->diagnostics = $diagnostics;
        // Phase 13. Optional (nullable) so this constructor remains
        // callable exactly as it was before Phase 13 — no existing call
        // site, test, or fixture breaks by omitting them.
        $this->access_gate = $access_gate;
        $this->telemetry   = $telemetry;
    }

    public function diagnostics(): ?AIOL_Diagnostics
    {
        return $this->diagnostics;
    }

    public function register(): void
    {
        add_action('admin_menu', [$this, 'add_menu']);
        add_action('admin_enqueue_scripts', [$this, 'enqueue']);
        add_action('admin_post_aiol_save_connection', [$this, 'handle_save_connection']);
        add_action('admin_post_aiol_disconnect', [$this, 'handle_disconnect']);
        add_action('add_meta_boxes', [$this, 'add_meta_box']);
        add_action('save_post', [$this, 'handle_meta_box_save'], 10, 1);
        add_action('admin_post_aiol_clear_log', [$this, 'handle_clear_log']);
    }

    public function add_menu(): void
    {
        add_menu_page(
            __('AI Operating Layer', 'ai-operating-layer'),
            __('AI Operating Layer', 'ai-operating-layer'),
            self::CAPABILITY,
            'ai-operating-layer',
            [$this, 'render_page'],
            'dashicons-networking',
            58
        );
        // Phase 13. A submenu, not a replacement for the connection
        // screen — a merchant configures the connection once and reads
        // the dashboard often; conflating them would bury the low-
        // frequency, high-stakes connection form under daily traffic.
        add_submenu_page(
            'ai-operating-layer',
            __('Dashboard', 'ai-operating-layer'),
            __('Dashboard', 'ai-operating-layer'),
            self::CAPABILITY,
            'ai-operating-layer-dashboard',
            [$this, 'render_dashboard']
        );
    }

    public function enqueue(string $hook): void
    {
        // Loaded only on this plugin's own screen — no global CSS cost.
        if (strpos($hook, 'ai-operating-layer') === false) {
            return;
        }
        wp_enqueue_style(
            'aiol-admin',
            AIOL_PLUGIN_URL . 'assets/css/admin.css',
            [],
            AIOL_VERSION
        );
    }

    // ---------------------------------------------------------------- writes

    public function handle_save_connection(): void
    {
        if (!current_user_can(self::CAPABILITY)) {
            wp_die(esc_html__('You do not have permission to change these settings.', 'ai-operating-layer'), '', ['response' => 403]);
        }
        check_admin_referer(self::NONCE);

        $endpoint = isset($_POST['aiol_endpoint']) ? sanitize_text_field(wp_unslash($_POST['aiol_endpoint'])) : '';
        // Token is intentionally NOT sanitize_text_field'd into lossy form;
        // it is validated by shape and stored verbatim, never echoed.
        $token = isset($_POST['aiol_token']) ? trim((string) wp_unslash($_POST['aiol_token'])) : '';

        $saved = $this->credentials->save($endpoint, $token);
        if (is_wp_error($saved)) {
            // User input is preserved via a transient so a validation error
            // does not make them retype the URL. The token is deliberately
            // NOT preserved — re-pasting a secret is cheaper than storing it
            // somewhere extra.
            set_transient('aiol_form_error', [
                'code'     => $saved->get_error_code(),
                'message'  => $saved->get_error_message(),
                'endpoint' => $endpoint,
            ], 60);
            $this->redirect_back('error');
        }

        // Verify immediately: a "saved" message for a credential that cannot
        // authenticate would be a misleading success state.
        $identity = $this->client->identity();
        if (is_wp_error($identity)) {
            set_transient('aiol_form_error', [
                'code'     => $identity->get_error_code(),
                'message'  => $identity->get_error_message(),
                'endpoint' => $endpoint,
            ], 60);
            $this->redirect_back('unverified');
        }

        $this->credentials->set_identity(is_array($identity) ? $identity : []);
        AIOL_Cache::flush_all();
        $this->logger->info('Connected to Cloud Core');
        $this->redirect_back('connected');
    }

    public function handle_disconnect(): void
    {
        if (!current_user_can(self::CAPABILITY)) {
            wp_die(esc_html__('You do not have permission to change these settings.', 'ai-operating-layer'), '', ['response' => 403]);
        }
        check_admin_referer(self::NONCE);

        $this->credentials->forget();
        AIOL_Cache::flush_all();
        $this->logger->info('Disconnected from Cloud Core');
        $this->redirect_back('disconnected');
    }

    private function redirect_back(string $status): void
    {
        wp_safe_redirect(add_query_arg(
            ['page' => 'ai-operating-layer', 'aiol_status' => $status],
            admin_url('admin.php')
        ));
        exit;
    }

    // ---------------------------------------------------------------- render

    public function render_page(): void
    {
        if (!current_user_can(self::CAPABILITY)) {
            wp_die(esc_html__('You do not have permission to view this page.', 'ai-operating-layer'), '', ['response' => 403]);
        }
        require AIOL_PLUGIN_DIR . 'admin/view-settings.php';
    }

    /**
     * Phase 13 dashboard: analytics, AI agents/access, search demand,
     * connection status and the adapter log — all read live from Cloud
     * Core through the typed AIOL_Client methods, nothing computed here.
     *
     * Each read is independent and each failure is independent: one
     * endpoint being unreachable must not blank the whole page (§33 —
     * PARTIAL is a real state, not a synonym for ERROR). Every WP_Error
     * is collected into $errors and shown as a dismissible notice; the
     * corresponding section renders its own empty state rather than
     * silently showing stale or fabricated numbers.
     */
    public function render_dashboard(): void
    {
        if (!current_user_can(self::CAPABILITY)) {
            wp_die(esc_html__('You do not have permission to view this page.', 'ai-operating-layer'), '', ['response' => 403]);
        }

        if (!$this->credentials->is_configured()) {
            require AIOL_PLUGIN_DIR . 'admin/view-dashboard-not-connected.php';
            return;
        }

        $sort_by  = isset($_GET['sort_by']) ? sanitize_key((string) wp_unslash($_GET['sort_by'])) : 'total_views';
        $sort_dir = isset($_GET['sort_dir']) && $_GET['sort_dir'] === 'asc' ? 'asc' : 'desc';

        $errors = [];

        $health = $this->client->telemetry_health();
        if (is_wp_error($health)) {
            $errors[] = $health->get_error_message();
            $health = ['overall' => 'unknown', 'core_reachable' => false];
        }

        $content = $this->client->content_stats($sort_by, $sort_dir, 20);
        if (is_wp_error($content)) {
            $errors[]      = $content->get_error_message();
            $content_stats = [];
        } else {
            $content_stats = $content['items'] ?? [];
        }

        $agent_response = $this->client->list_agents(true, 50);
        if (is_wp_error($agent_response)) {
            $errors[] = $agent_response->get_error_message();
            $agents   = [];
        } else {
            $agents = $agent_response['items'] ?? [];
        }
        // The agent list carries no access tier of its own (that lives on
        // AccessPolicy); resolve each agent's effective decision from the
        // cached, already-enforced policy table so the dashboard shows
        // exactly what the edge is actually doing, not a second guess.
        $policies = AIOL_Access_Gate::policies();
        foreach ($agents as &$agent) {
            $decision      = AIOL_Access_Gate::evaluate(
                [
                    'type'      => (string) ($agent['actor_type'] ?? 'unknown'),
                    // The direct path (see the docblock on evaluate()) —
                    // a renamed agent must still match its policy row.
                    'signature' => $agent['signature'] ?? null,
                ],
                $policies
            );
            $agent['tier'] = $decision['tier'];
        }
        unset($agent);

        $search_response = $this->client->search_demand_terms(10);
        if (is_wp_error($search_response)) {
            $errors[]      = $search_response->get_error_message();
            $search_terms  = [];
        } else {
            $search_terms = $search_response['items'] ?? [];
        }

        $views_response = $this->client->list_page_views(25);
        if (is_wp_error($views_response)) {
            $errors[]    = $views_response->get_error_message();
            $page_views  = [];
        } else {
            $page_views = $views_response['items'] ?? [];
        }

        $log_entries = $this->logger->entries();
        $buffered    = count(AIOL_Telemetry::buffered());

        require AIOL_PLUGIN_DIR . 'admin/view-dashboard.php';
    }

    /**
     * Clears this site's own adapter log and its unsent telemetry buffer.
     * Deliberately does NOT touch anything in Cloud Core — see the
     * docblock on AIOL_Telemetry::clear_buffer() for why that boundary is
     * load-bearing, not incidental.
     */
    public function handle_clear_log(): void
    {
        if (!current_user_can(self::CAPABILITY)) {
            wp_die(esc_html__('You do not have permission to do that.', 'ai-operating-layer'), '', ['response' => 403]);
        }
        check_admin_referer('aiol_clear_log');

        $this->logger->clear();
        AIOL_Telemetry::clear_buffer();
        $this->logger->info('Log history cleared by ' . wp_get_current_user()->user_login);

        wp_safe_redirect(add_query_arg(
            ['page' => 'ai-operating-layer-dashboard', 'aiol_status' => 'log_cleared'],
            admin_url('admin.php')
        ));
        exit;
    }

    public function connection_state(): array
    {
        if (!$this->credentials->is_configured()) {
            return ['state' => AIOL_Status::NOT_CONFIGURED, 'identity' => [], 'checks' => []];
        }
        $identity = $this->client->identity();
        if (is_wp_error($identity)) {
            return [
                'state'   => AIOL_Status::FAILED,
                'identity' => $this->credentials->get_identity(),
                'checks'  => ['cloud_core' => AIOL_Status::FAILED],
                'error'   => $identity->get_error_message(),
                'retry_safe' => AIOL_Client::is_retry_safe((string) $identity->get_error_code()),
            ];
        }
        return [
            'state'    => AIOL_Status::OK,
            'identity' => is_array($identity) ? $identity : [],
            'checks'   => ['cloud_core' => AIOL_Status::OK, 'authentication' => AIOL_Status::OK],
        ];
    }

    /**
     * Fetches mappings for the list view. Returns a triple so the view can
     * distinguish "empty" from "failed" - collapsing them would show an
     * encouraging empty state during an outage, which is misleading.
     *
     * @return array{0: array, 1: string, 2: string} rows, error message, error code
     */
    public function fetch_mappings(): array
    {
        if (!$this->client->is_configured()) {
            return [[], '', ''];
        }
        $result = $this->client->list_mappings();
        if (is_wp_error($result)) {
            return [[], $result->get_error_message(), (string) $result->get_error_code()];
        }
        $items = is_array($result) && isset($result['items']) && is_array($result['items'])
            ? $result['items']
            : [];
        return [$items, '', ''];
    }

    // ------------------------------------------------------------- meta box

    public function add_meta_box(): void
    {
        foreach (['post', 'page', 'product'] as $screen) {
            add_meta_box(
                'aiol_mapping',
                __('AI Operating Layer', 'ai-operating-layer'),
                [$this, 'render_meta_box'],
                $screen,
                'side',
                'default'
            );
        }
    }

    public function render_meta_box(WP_Post $post): void
    {
        wp_nonce_field('aiol_mapping_save', 'aiol_mapping_nonce');
        require AIOL_PLUGIN_DIR . 'admin/view-meta-box.php';
    }

    public function handle_meta_box_save($post_id): void
    {
        $post_id = (int) $post_id;

        if (!isset($_POST['aiol_mapping_nonce'])
            || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['aiol_mapping_nonce'])), 'aiol_mapping_save')) {
            return;
        }
        if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) {
            return;
        }
        if (!current_user_can('edit_post', $post_id)) {
            return;
        }

        $object_id = isset($_POST['aiol_object_id'])
            ? sanitize_text_field(wp_unslash($_POST['aiol_object_id']))
            : '';
        $object_type = isset($_POST['aiol_object_type'])
            ? sanitize_key(wp_unslash($_POST['aiol_object_type']))
            : 'knowledge_object';

        if (!in_array($object_type, AIOL_Mappings::allowed_object_types(), true)) {
            $object_type = 'knowledge_object';
        }

        $previous_id   = AIOL_Mappings::object_id($post_id);
        $previous_type = AIOL_Mappings::object_type($post_id);

        if ($object_id === '') {
            delete_post_meta($post_id, AIOL_Mappings::META_OBJECT_ID);
            delete_post_meta($post_id, AIOL_Mappings::META_OBJECT_TYPE);
            AIOL_Mappings::set_state($post_id, 'not_configured');
            if ($previous_id !== '') {
                // R1 (Phase 9 reconciliation): this hook was listened for by
                // AIOL_Representations but never fired by anything, so
                // unlinking a post left stale llms.txt output until the TTL
                // expired. ADR-049 claimed this worked; it did not.
                do_action('aiol_mapping_changed', $post_id, '', $previous_id);
            }
            return;
        }
        if (!AIOL_Mappings::looks_like_uuid($object_id)) {
            AIOL_Mappings::set_state(
                $post_id,
                'failed',
                __('That is not a valid Cloud Core object ID. It should look like 123e4567-e89b-12d3-a456-426614174000.', 'ai-operating-layer')
            );
            return;
        }

        update_post_meta($post_id, AIOL_Mappings::META_OBJECT_ID, $object_id);
        update_post_meta($post_id, AIOL_Mappings::META_OBJECT_TYPE, $object_type);
        AIOL_Mappings::set_state($post_id, 'pending');

        if ($object_id !== $previous_id || $object_type !== $previous_type) {
            do_action('aiol_mapping_changed', $post_id, $object_id, $previous_id);
        }
    }
}
