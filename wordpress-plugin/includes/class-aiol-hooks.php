<?php
/**
 * WordPress event hooks — the sync trigger surface.
 *
 * THREE SAFETY MECHANISMS, each guarding a failure mode that is easy to
 * create accidentally in WordPress and expensive in production:
 *
 * 1. RECURSION GUARD (`self::$syncing`). `save_post` can fire again while a
 *    handler is running (any call that touches the post re-enters). Without
 *    a guard this becomes an infinite loop that hammers Cloud Core.
 *
 * 2. PER-REQUEST DEDUPLICATION (`self::$synced_this_request`). WordPress
 *    fires `save_post` more than once for a single editor action (autosave,
 *    revision, meta box save). Syncing each one would multiply every edit
 *    into several identical Core calls.
 *
 * 3. RELEVANCE FILTER. Autosaves, revisions, and unmapped posts return
 *    early *before* any HTTP work. This is the "cheap -> filter -> expensive
 *    only if necessary" resource rule applied at the adapter edge: the
 *    overwhelming majority of save_post firings cost zero network calls.
 *
 * Idempotency at the far end is Core's (unique constraints), so even if all
 * three of these failed, duplicates would still not be created. They exist
 * to avoid the *load*, not to be the correctness mechanism.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Hooks
{
    private static bool $syncing = false;
    private static array $synced_this_request = [];

    private AIOL_Client $client;
    private AIOL_Logger $logger;

    public function __construct(AIOL_Client $client, AIOL_Logger $logger)
    {
        $this->client = $client;
        $this->logger = $logger;
    }

    public function register(): void
    {
        add_action('save_post', [$this, 'on_save_post'], 20, 3);
        add_action('transition_post_status', [$this, 'on_status_change'], 10, 3);

        // WooCommerce BOUNDARY (master spec §40 assigns WooCommerce commerce
        // integration to Phase 10). What is registered here is deliberately
        // ONLY the product-identity projection: a Woo product is a post, and
        // saving it may refresh its mapping. No price, stock, order, cart or
        // checkout behaviour is touched. See ADR-041.
        add_action('woocommerce_update_product', [$this, 'on_woocommerce_product_saved'], 20, 1);
    }

    public function on_save_post($post_id, $post = null, $update = null): void
    {
        $post_id = (int) $post_id;

        if (self::$syncing) {
            return; // guard 1
        }
        if (isset(self::$synced_this_request[$post_id])) {
            return; // guard 2
        }
        if (!$this->should_sync($post_id)) {
            return; // guard 3 - no HTTP performed
        }

        self::$synced_this_request[$post_id] = true;
        $this->sync_post($post_id);
    }

    public function on_woocommerce_product_saved($product_id): void
    {
        $this->on_save_post((int) $product_id);
    }

    /**
     * Status changes matter because an unpublished post should not keep
     * claiming a live URL in Core's mapping. Note the adapter reports the
     * change; it does not decide what Core does about it.
     */
    public function on_status_change($new_status, $old_status, $post): void
    {
        if (!$post instanceof WP_Post || $new_status === $old_status) {
            return;
        }
        if (!AIOL_Mappings::is_mapped((int) $post->ID)) {
            return;
        }
        if ($new_status === 'publish' || $old_status === 'publish') {
            $this->on_save_post((int) $post->ID);
        }
    }

    private function should_sync(int $post_id): bool
    {
        if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) {
            return false;
        }
        if (wp_is_post_revision($post_id) || wp_is_post_autosave($post_id)) {
            return false;
        }
        if (!AIOL_Mappings::is_mapped($post_id)) {
            return false;
        }
        if (!$this->client->is_configured()) {
            return false;
        }
        return true;
    }

    private function sync_post(int $post_id): void
    {
        self::$syncing = true;
        try {
            $object_id   = AIOL_Mappings::object_id($post_id);
            $object_type = AIOL_Mappings::object_type($post_id);
            $post        = get_post($post_id);

            $result = $this->client->upsert_mapping(
                $object_type,
                $object_id,
                $post_id,
                $post ? $post->post_type : null,
                get_permalink($post_id) ?: null
            );

            if (is_wp_error($result)) {
                AIOL_Mappings::set_state($post_id, 'failed', $result->get_error_message());
                $this->logger->error('Mapping sync failed', [
                    'post_id' => (string) $post_id,
                    'code'    => $result->get_error_code(),
                ]);
                return;
            }

            AIOL_Mappings::set_state($post_id, 'synced');
            update_option('aiol_last_sync', gmdate('c'), false);
            $this->logger->info('Mapping synced', ['post_id' => (string) $post_id]);
        } finally {
            self::$syncing = false; // released even if Core throws
        }
    }

    /** Test seam: lets the guards be exercised without WordPress. */
    public static function reset_request_state(): void
    {
        self::$syncing = false;
        self::$synced_this_request = [];
    }
}
