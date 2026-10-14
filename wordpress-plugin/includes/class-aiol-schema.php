<?php
/**
 * JSON-LD rendering — the most safety-critical file in this plugin.
 *
 * A structured-data block is a machine-readable public assertion. Search
 * engines and AI agents will treat whatever appears here as the merchant's
 * claim about their product. So this class is written around one rule:
 *
 *   RENDER ONLY WHAT CLOUD CORE ASSERTS. INVENT NOTHING.
 *
 * Concretely, and each of these is a real failure mode in commerce plugins:
 *
 * - `postmeta` is NEVER read as a source of product facts. A value sitting
 *   in the WordPress database has not been verified by anyone; emitting it
 *   as schema.org data would turn an unreviewed field into a public claim.
 *   (Master spec §28/§30; ADR-032's two-layer verification exists precisely
 *   so that "it is in the database" ≠ "it is verified".)
 *
 * - A MISSING PRICE IS OMITTED, never rendered as 0. `price: 0` means free.
 *   Core distinguishes "price on request" (null) from "free" (0), and that
 *   distinction must survive into the markup or the adapter has lied.
 *
 * - UNTRACKED STOCK IS NOT OUT OF STOCK. Core's `stock_quantity = null`
 *   means untracked; emitting OutOfStock for it would suppress a
 *   purchasable product.
 *
 * - REJECTED OR UNVERIFIED EVIDENCE IS NEVER EMITTED. Only claims Core
 *   reports as effectively verified appear.
 *
 * - If Core is unreachable, NOTHING is rendered. A cached-but-stale price is
 *   worse than no structured data: absent markup is merely uninformative,
 *   wrong markup is a false public claim. This is why the failure mode here
 *   is silence rather than fallback.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Schema
{
    private AIOL_Client $client;
    private AIOL_Cache $cache;

    public function __construct(AIOL_Client $client, AIOL_Cache $cache)
    {
        $this->client = $client;
        $this->cache  = $cache;
    }

    public function register(): void
    {
        add_action('wp_head', [$this, 'render'], 20);
    }

    public function render(): void
    {
        if (!is_singular() || !$this->client->is_configured()) {
            return;
        }
        $post_id = (int) get_the_ID();
        if (!AIOL_Mappings::is_mapped($post_id)) {
            return;
        }
        if (AIOL_Mappings::object_type($post_id) !== 'product') {
            return; // only products carry commercial schema in Phase 9
        }

        $payload = $this->build_payload($post_id);
        if ($payload === null) {
            return; // silence rather than guesswork - see class docstring
        }

        printf(
            "<script type=\"application/ld+json\">%s</script>\n",
            wp_json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)
        );
    }

    /**
     * Pure transformation from a Core catalog payload to schema.org.
     * Static and dependency-free so it is unit-testable without WordPress
     * or a network - see tests/test-schema.php.
     *
     * @param array $core  Product projection as returned by Cloud Core.
     * @return array|null  null when Core has not asserted enough to publish.
     */
    public static function build_from_core(array $core): ?array
    {
        $name = isset($core['name']) ? trim((string) $core['name']) : '';
        if ($name === '') {
            return null; // a Product with no name is not publishable
        }

        // Only PUBLISHED products may be represented publicly. Core owns
        // this lifecycle (ProductStatus); the adapter merely respects it.
        if (($core['status'] ?? '') !== 'published') {
            return null;
        }

        $payload = [
            '@context' => 'https://schema.org',
            '@type'    => 'Product',
            'name'     => $name,
        ];

        foreach (['description' => 'description', 'sku' => 'sku'] as $src => $dest) {
            if (!empty($core[$src])) {
                $payload[$dest] = (string) $core[$src];
            }
        }
        if (!empty($core['brand'])) {
            $payload['brand'] = ['@type' => 'Brand', 'name' => (string) $core['brand']];
        }
        if (!empty($core['category'])) {
            $payload['category'] = (string) $core['category'];
        }

        $offer = self::build_offer($core['offer'] ?? null);
        if ($offer !== null) {
            $payload['offers'] = $offer;
        }

        return $payload;
    }

    /**
     * Offer mapping. Every branch here encodes a semantic the Core team was
     * deliberate about; flattening any of them would misstate commerce.
     */
    private static function build_offer($offer): ?array
    {
        if (!is_array($offer)) {
            return null;
        }

        $availability = self::availability_url((string) ($offer['availability'] ?? ''));
        if ($availability === null) {
            return null; // discontinued / unknown: assert nothing
        }

        $out = ['@type' => 'Offer', 'availability' => $availability];

        // price === null means "on request". It is OMITTED, not zeroed.
        if (array_key_exists('price', $offer) && $offer['price'] !== null && $offer['price'] !== '') {
            $price = (float) $offer['price'];
            if ($price < 0) {
                return null; // nonsensical; refuse rather than publish
            }
            $out['price'] = number_format($price, 2, '.', '');
            if (!empty($offer['currency'])) {
                $out['priceCurrency'] = strtoupper((string) $offer['currency']);
            } else {
                // A price without a currency is not a meaningful assertion.
                unset($out['price']);
            }
        }

        if (!empty($offer['url'])) {
            $url = esc_url_raw((string) $offer['url']);
            if ($url !== '') {
                $out['url'] = $url;
            }
        }

        return $out;
    }

    /**
     * NOTE: `stock_quantity === null` (untracked) never reaches this method
     * as OutOfStock. Availability is Core's own enum; the adapter maps it
     * one-to-one and refuses anything it does not recognise.
     */
    public static function availability_url(string $availability): ?string
    {
        switch ($availability) {
            case 'in_stock':     return 'https://schema.org/InStock';
            case 'out_of_stock': return 'https://schema.org/OutOfStock';
            case 'preorder':     return 'https://schema.org/PreOrder';
            case 'backorder':    return 'https://schema.org/BackOrder';
            case 'discontinued': return null; // deliberately unrepresented
            default:             return null; // unknown value: assert nothing
        }
    }

    private function build_payload(int $post_id): ?array
    {
        $object_id = AIOL_Mappings::object_id($post_id);
        $key       = 'product_' . md5($object_id);

        // Volatile TTL because this payload carries price and availability.
        $core = $this->cache->get($key);
        if ($core === false) {
            $core = $this->client->catalog_product($object_id);
            if (is_wp_error($core)) {
                return null; // silence on failure
            }
            $this->cache->set($key, $core, AIOL_Cache::TTL_VOLATILE);
        }

        return is_array($core) ? self::build_from_core($core) : null;
    }
}
