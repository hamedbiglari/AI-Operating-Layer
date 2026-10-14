<?php
/**
 * WooCommerce CONTRACT test.
 *
 * `map_offer_state()` is already unit-tested against synthesised arrays.
 * That proves the mapping logic, but not the thing R1 taught us to worry
 * about: the **wiring** between WooCommerce's object API and our reader.
 * A typo'd method name (`get_stock_quanity()`) would pass every array-based
 * test and fail silently in production.
 *
 * So this file drives the adapter's real read path through a fake product
 * that implements the WooCommerce `WC_Product` surface we depend on. It is
 * not a substitute for a real WooCommerce install — that remains
 * ENVIRONMENT BLOCKED — but it does verify that the methods we call exist
 * with the names and return shapes WooCommerce documents.
 *
 * The fake deliberately returns WooCommerce's REAL types, including the
 * awkward ones: `get_price()` returns a STRING (often ''), and
 * `get_stock_quantity()` returns `null` when stock is unmanaged. Those two
 * are exactly where a naive implementation coerces '' to 0.0 and null to 0.
 */

declare(strict_types=1);

define('ABSPATH', __DIR__);
if (!function_exists('__')) { function __(string $t, string $d = ''): string { return $t; } }

require_once __DIR__ . '/bootstrap-assert.php';
require_once dirname(__DIR__) . '/includes/class-aiol-woocommerce.php';

/**
 * Minimal stand-in for WC_Product, returning WooCommerce's documented
 * return types rather than convenient ones.
 */
class Fake_WC_Product
{
    private array $data;

    public function __construct(array $data = [])
    {
        $this->data = $data + [
            'id' => 101,
            'stock_status' => 'instock',
            'manage_stock' => false,
            'stock_quantity' => null,   // null when unmanaged - WooCommerce's real behaviour
            'price' => '25.00',         // STRING, and '' when unset
            'backorders_allowed' => false,
            'date_modified' => '2026-01-01 10:00:00',
        ];
    }

    public function get_id(): int { return (int) $this->data['id']; }
    public function get_stock_status(): string { return (string) $this->data['stock_status']; }
    public function get_manage_stock(): bool { return (bool) $this->data['manage_stock']; }
    public function get_stock_quantity() { return $this->data['stock_quantity']; }
    public function get_price() { return $this->data['price']; }
    public function backorders_allowed(): bool { return (bool) $this->data['backorders_allowed']; }
    public function get_date_modified() { return $this->data['date_modified']; }
}

/**
 * Mirrors exactly how AIOL_WooCommerce::sync() reads the product. If the
 * adapter's field names drift from WooCommerce's API, this breaks — which
 * is the point.
 */
function aiol_read_product(Fake_WC_Product $product): array
{
    return AIOL_WooCommerce::map_offer_state([
        'stock_status'       => (string) $product->get_stock_status(),
        'manage_stock'       => (bool) $product->get_manage_stock(),
        'stock_quantity'     => $product->get_stock_quantity(),
        'price'              => $product->get_price(),
        'backorders_allowed' => (bool) $product->backorders_allowed(),
    ]);
}

// --- the methods we depend on must exist with these exact names -------------

foreach ([
    'get_id', 'get_stock_status', 'get_manage_stock', 'get_stock_quantity',
    'get_price', 'backorders_allowed', 'get_date_modified',
] as $method) {
    T::true(method_exists('Fake_WC_Product', $method),
        "the adapter's read path depends on WC_Product::$method() — name pinned by contract");
}

// --- simple product, unmanaged stock, real WooCommerce types ------------------

$simple = aiol_read_product(new Fake_WC_Product());
T::is($simple['stock_quantity'], null,
    'get_stock_quantity() returning null stays UNTRACKED — not coerced to 0');
T::is($simple['price'], 25.0, 'a string price from WooCommerce becomes a float');
T::is($simple['availability'], 'in_stock', 'instock maps through the real object API');

// --- the '' price trap --------------------------------------------------------
//
// WooCommerce returns '' for a product with no price set. `(float) ''` is
// 0.0 in PHP, which would publish "free". This is the single most dangerous
// coercion in the whole adapter.

$no_price = aiol_read_product(new Fake_WC_Product(['price' => '']));
T::is($no_price['price'], null,
    "WooCommerce's empty-string price becomes NULL (on request), never 0.0 (free)");

$zero_price = aiol_read_product(new Fake_WC_Product(['price' => '0']));
T::is($zero_price['price'], 0.0, "an explicit '0' is a real price and is preserved");

// --- managed stock, including the zero-with-backorders case ---------------------

$managed = aiol_read_product(new Fake_WC_Product(['manage_stock' => true, 'stock_quantity' => 4]));
T::is($managed['stock_quantity'], 4, 'a managed quantity survives the object read');

$sold_out = aiol_read_product(new Fake_WC_Product([
    'manage_stock' => true, 'stock_quantity' => 0, 'backorders_allowed' => false,
]));
T::is($sold_out['availability'], 'out_of_stock', 'managed 0 without backorders => out_of_stock');

$backorderable = aiol_read_product(new Fake_WC_Product([
    'manage_stock' => true, 'stock_quantity' => 0, 'backorders_allowed' => true,
]));
T::is($backorderable['availability'], 'backorder',
    'managed 0 WITH backorders is still sellable — the merchant loses a sale if we say out_of_stock');

// --- WooCommerce stock_status vocabulary -----------------------------------------

T::is(aiol_read_product(new Fake_WC_Product(['stock_status' => 'outofstock']))['availability'], 'out_of_stock', 'outofstock');
T::is(aiol_read_product(new Fake_WC_Product(['stock_status' => 'onbackorder']))['availability'], 'backorder', 'onbackorder');

// --- idempotency key shape -------------------------------------------------------
//
// The key is woo-{id}-{date_modified}. Two hook firings for ONE save share a
// date_modified and therefore dedupe; a genuine later edit produces a new
// key and a new job. Both halves matter.

$p = new Fake_WC_Product();
$key_a = sprintf('woo-%d-%s', $p->get_id(), (string) $p->get_date_modified());
$key_b = sprintf('woo-%d-%s', $p->get_id(), (string) $p->get_date_modified());
T::is($key_a, $key_b, 'two hook firings for the same save produce the SAME idempotency key');

$edited = new Fake_WC_Product(['date_modified' => '2026-01-02 11:00:00']);
$key_c = sprintf('woo-%d-%s', $edited->get_id(), (string) $edited->get_date_modified());
T::true($key_a !== $key_c, 'a genuine later edit produces a DIFFERENT key, so it is not swallowed');

// --- the adapter never reads anything it should not -------------------------------
//
// If a future change makes the adapter read product name/description/status
// from WooCommerce, that is Core's data and the directional rule (ADR-050)
// is broken. Executable code only, per the test-woocommerce.php lesson.

function aiol_code(string $path): string
{
    $out = '';
    foreach (token_get_all(file_get_contents($path)) as $t) {
        if (is_array($t)) {
            if (in_array($t[0], [T_COMMENT, T_DOC_COMMENT], true)) { continue; }
            $out .= $t[1];
        } else { $out .= $t; }
    }
    return $out;
}
$woo_code = aiol_code(dirname(__DIR__) . '/includes/class-aiol-woocommerce.php');
foreach (['get_name', 'get_description', 'get_short_description', 'get_status', 'get_categories'] as $forbidden) {
    T::is(strpos($woo_code, $forbidden), false,
        "the adapter never reads WC_Product::$forbidden() — that is Core's data (ADR-050)");
}

exit(T::report('woocommerce-contract'));
