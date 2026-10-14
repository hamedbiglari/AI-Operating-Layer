<?php
/**
 * WooCommerce adapter (Phase 10; master spec §40).
 *
 * THE DIRECTIONAL RULE, which this class exists to obey (ADR-050):
 *
 *   WooCommerce owns : its own post IDs, and the merchant's operational
 *                      price and stock
 *   Cloud Core owns  : what the product IS, whether it may be recommended,
 *                      its evidence and its trust
 *
 * So this class pushes price/stock/availability to Core, and pushes nothing
 * else. It cannot publish a product, verify evidence, or change a
 * recommendation — the Core endpoints to do so are not on the adapter
 * surface at all, and the credential has no scope for them.
 *
 * It also never reads Core in order to change WooCommerce. A merchant's
 * store stays theirs; Core does not reach in and rewrite their prices.
 *
 * DEGRADATION: if Core is unreachable, WooCommerce keeps working normally.
 * The sync is best-effort and its failure is recorded on the product for
 * the merchant to see, never surfaced as a checkout error. A shop that
 * cannot sell because a knowledge service is down would be a catastrophic
 * coupling.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_WooCommerce
{
    public const META_MAPPING_ID = '_aiol_commerce_mapping_id';
    public const META_SYNC_STATE = '_aiol_commerce_sync_state';
    public const META_SYNC_ERROR = '_aiol_commerce_sync_error';

    private static bool $syncing = false;
    private static array $synced_this_request = [];

    /**
     * BULK GUARD (ADR-054).
     *
     * Offer sync is an HTTP call. That is fine for one price edit and
     * catastrophic for a bulk operation: a 5,000-product CSV import, a
     * WP-CLI run, or a "bulk edit -> set sale price" on 200 rows would
     * issue one synchronous request per product inside a single PHP
     * request. The result is a timeout, a half-synced catalogue, and a
     * retry storm against Cloud Core.
     *
     * So the adapter counts what it has already sent in this request. Past
     * the threshold it stops calling Core and DEFERS the remainder to a
     * WordPress cron event, which drains the queue a slice at a time.
     *
     * Deferral is not "dropping": the product IDs are persisted, so a
     * timeout or fatal error after the threshold still leaves the work
     * recorded. Losing sync silently would be worse than being slow.
     */
    private const MAX_SYNCS_PER_REQUEST = 20;
    private const DEFERRED_OPTION = 'aiol_deferred_offer_sync';
    private const DRAIN_BATCH = 20;
    public const CRON_HOOK = 'aiol_drain_offer_sync';

    private static int $synced_count = 0;

    private AIOL_Client $client;
    private AIOL_Logger $logger;

    public function __construct(AIOL_Client $client, AIOL_Logger $logger)
    {
        $this->client = $client;
        $this->logger = $logger;
    }

    public function register(): void
    {
        // Registered only when WooCommerce is actually present. Hooking
        // unconditionally would fire on sites that have no commerce at all.
        if (!self::is_woocommerce_active()) {
            return;
        }
        add_action('woocommerce_update_product', [$this, 'on_product_changed'], 20, 1);
        add_action('woocommerce_product_set_stock', [$this, 'on_stock_changed'], 20, 1);
        add_action('woocommerce_variation_set_stock', [$this, 'on_stock_changed'], 20, 1);

        // Drains whatever the bulk guard deferred. Registered
        // unconditionally so a queue left by a previous request is still
        // drained even if no product changes in this one.
        add_action(self::CRON_HOOK, [$this, 'drain_deferred']);
    }

    public static function is_woocommerce_active(): bool
    {
        return class_exists('WooCommerce') || function_exists('wc_get_product');
    }

    public function on_product_changed($product_id): void
    {
        $this->sync((int) $product_id);
    }

    public function on_stock_changed($product): void
    {
        $id = is_object($product) && method_exists($product, 'get_id') ? (int) $product->get_id() : (int) $product;
        $this->sync($id);
    }

    /**
     * Pure mapping from a WooCommerce stock/price state to Core's Offer
     * vocabulary. Static and WooCommerce-free so it is unit-testable.
     *
     * Two semantics are preserved deliberately, because collapsing either
     * would corrupt data three phases have been careful about:
     *
     *  - `manage_stock = false` means the merchant does NOT track quantity.
     *    That maps to stock_quantity = null ("untracked"), never 0, because
     *    0 reads as out-of-stock everywhere downstream.
     *  - an empty price means "price on request", never 0, because 0 means
     *    free.
     *
     * @param array{stock_status?:string,manage_stock?:bool,stock_quantity?:mixed,price?:mixed,backorders_allowed?:bool} $state
     * @return array{availability:string,stock_quantity:int|null,price:float|null}
     */
    public static function map_offer_state(array $state): array
    {
        $stock_status = (string) ($state['stock_status'] ?? 'instock');
        $manage_stock = (bool) ($state['manage_stock'] ?? false);
        $backorders   = (bool) ($state['backorders_allowed'] ?? false);

        switch ($stock_status) {
            case 'outofstock':
                $availability = 'out_of_stock';
                break;
            case 'onbackorder':
                $availability = 'backorder';
                break;
            default:
                $availability = 'in_stock';
        }

        // A managed quantity of 0 with backorders allowed is genuinely
        // "backorder", not "out of stock" - the merchant will still sell it.
        $quantity = null;
        if ($manage_stock && $state['stock_quantity'] !== null && $state['stock_quantity'] !== '') {
            $quantity = (int) $state['stock_quantity'];
            if ($quantity <= 0) {
                $availability = $backorders ? 'backorder' : 'out_of_stock';
            }
        }

        $raw_price = $state['price'] ?? '';
        // '' / null => price on request. '0' is a real, deliberate price.
        $price = ($raw_price === '' || $raw_price === null) ? null : (float) $raw_price;
        if ($price !== null && $price < 0) {
            $price = null; // nonsensical; refuse rather than publish
        }

        return ['availability' => $availability, 'stock_quantity' => $quantity, 'price' => $price];
    }

    private function sync(int $product_id): void
    {
        if (self::$syncing || isset(self::$synced_this_request[$product_id])) {
            return; // recursion + per-request dedup, as in AIOL_Hooks
        }
        if (!$this->client->is_configured() || !function_exists('wc_get_product')) {
            return;
        }
        $mapping_id = (string) get_post_meta($product_id, self::META_MAPPING_ID, true);
        if ($mapping_id === '') {
            return; // unmapped products cost zero network calls
        }

        self::$synced_this_request[$product_id] = true;

        // Bulk guard. Checked AFTER the cheap filters above, so an import of
        // unmapped products never consumes budget it does not need.
        if (self::should_defer(self::$synced_count)) {
            self::defer($product_id);
            update_post_meta($product_id, self::META_SYNC_STATE, 'deferred');
            return;
        }
        self::$synced_count++;
        self::$syncing = true;
        try {
            $product = wc_get_product($product_id);
            if (!$product) {
                return;
            }
            $state = self::map_offer_state([
                'stock_status'       => (string) $product->get_stock_status(),
                'manage_stock'       => (bool) $product->get_manage_stock(),
                'stock_quantity'     => $product->get_stock_quantity(),
                'price'              => $product->get_price(),
                'backorders_allowed' => (bool) $product->backorders_allowed(),
            ]);

            $result = $this->client->sync_offer(
                $mapping_id,
                $state['price'],
                get_woocommerce_currency(),
                $state['availability'],
                $state['stock_quantity'],
                // Idempotency key includes the modified timestamp, so a
                // repeated hook for an unchanged product is a no-op at Core.
                sprintf('woo-%d-%s', $product_id, (string) $product->get_date_modified())
            );

            if (is_wp_error($result)) {
                update_post_meta($product_id, self::META_SYNC_STATE, 'failed');
                update_post_meta($product_id, self::META_SYNC_ERROR, $result->get_error_message());
                $this->logger->error('Commerce sync failed', [
                    'product_id' => (string) $product_id,
                    'code'       => $result->get_error_code(),
                ]);
                return; // WooCommerce continues working regardless
            }

            update_post_meta($product_id, self::META_SYNC_STATE, 'synced');
            delete_post_meta($product_id, self::META_SYNC_ERROR);
            $this->logger->info('Commerce offer synced', ['product_id' => (string) $product_id]);
        } finally {
            self::$syncing = false;
        }
    }

    /**
     * Pure predicate so the threshold is testable without WordPress, and so
     * a mutation test can prove the guard is load-bearing.
     */
    public static function should_defer(int $already_synced, int $max = self::MAX_SYNCS_PER_REQUEST): bool
    {
        return $already_synced >= $max;
    }

    /** Persists a product id for later draining and schedules the drain. */
    public static function defer(int $product_id): void
    {
        $queue = get_option(self::DEFERRED_OPTION, []);
        if (!is_array($queue)) {
            $queue = [];
        }
        if (!in_array($product_id, $queue, true)) {
            $queue[] = $product_id;
            update_option(self::DEFERRED_OPTION, $queue, false);
        }
        if (function_exists('wp_next_scheduled') && !wp_next_scheduled(self::CRON_HOOK)) {
            wp_schedule_single_event(time() + 60, self::CRON_HOOK);
        }
    }

    public static function deferred_queue(): array
    {
        $queue = get_option(self::DEFERRED_OPTION, []);
        return is_array($queue) ? $queue : [];
    }

    /**
     * Drains a slice of the queue. Re-schedules itself while work remains,
     * so a 5,000-product import completes across many short cron runs
     * rather than one request that times out.
     */
    public function drain_deferred(): void
    {
        $queue = self::deferred_queue();
        if ($queue === []) {
            return;
        }
        $batch     = array_slice($queue, 0, self::DRAIN_BATCH);
        $remaining = array_slice($queue, self::DRAIN_BATCH);
        update_option(self::DEFERRED_OPTION, $remaining, false);

        // The drain runs in its own request, so the per-request budget
        // starts fresh - that is the point of deferring.
        self::$synced_count = 0;
        self::$synced_this_request = [];
        foreach ($batch as $product_id) {
            $this->sync((int) $product_id);
        }

        if ($remaining !== [] && function_exists('wp_schedule_single_event')) {
            wp_schedule_single_event(time() + 60, self::CRON_HOOK);
        }
    }

    public static function reset_request_state(): void
    {
        self::$syncing = false;
        self::$synced_this_request = [];
        self::$synced_count = 0;
    }
}
