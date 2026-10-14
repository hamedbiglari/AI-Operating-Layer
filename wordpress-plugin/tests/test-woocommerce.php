<?php
/**
 * WooCommerce offer-state mapping tests.
 *
 * `map_offer_state()` is where three phases' worth of careful semantics
 * either survive or get quietly destroyed. Each assertion below corresponds
 * to a distinction that reads correctly only if it is preserved end to end:
 * Phase 7 stored it, Phase 8 scored on it, Phase 9 rendered it publicly.
 */

declare(strict_types=1);

define('ABSPATH', __DIR__);
if (!function_exists('__')) { function __(string $t, string $d = ''): string { return $t; } }

require_once __DIR__ . '/bootstrap-assert.php';
require_once dirname(__DIR__) . '/includes/class-aiol-woocommerce.php';

// --- untracked stock is NOT zero -------------------------------------------

$untracked = AIOL_WooCommerce::map_offer_state([
    'stock_status' => 'instock', 'manage_stock' => false, 'stock_quantity' => null, 'price' => '25.00',
]);
T::is($untracked['stock_quantity'], null,
    'manage_stock=false maps to UNTRACKED (null), never 0 - 0 reads as out-of-stock downstream');
T::is($untracked['availability'], 'in_stock', 'untracked but in stock stays in_stock');

$tracked = AIOL_WooCommerce::map_offer_state([
    'stock_status' => 'instock', 'manage_stock' => true, 'stock_quantity' => 7, 'price' => '25.00',
]);
T::is($tracked['stock_quantity'], 7, 'a tracked quantity is carried through');

// --- zero stock: backorders change the meaning -------------------------------

$zero_no_backorder = AIOL_WooCommerce::map_offer_state([
    'stock_status' => 'instock', 'manage_stock' => true, 'stock_quantity' => 0,
    'price' => '10', 'backorders_allowed' => false,
]);
T::is($zero_no_backorder['availability'], 'out_of_stock', 'managed 0 with no backorders => out_of_stock');

$zero_with_backorder = AIOL_WooCommerce::map_offer_state([
    'stock_status' => 'instock', 'manage_stock' => true, 'stock_quantity' => 0,
    'price' => '10', 'backorders_allowed' => true,
]);
T::is($zero_with_backorder['availability'], 'backorder',
    'managed 0 WITH backorders is still sellable - backorder, not out_of_stock');

// --- price: empty is "on request", 0 is free -------------------------------------

$on_request = AIOL_WooCommerce::map_offer_state([
    'stock_status' => 'instock', 'manage_stock' => false, 'price' => '',
]);
T::is($on_request['price'], null, 'empty price means ON REQUEST (null), never 0');

$free = AIOL_WooCommerce::map_offer_state([
    'stock_status' => 'instock', 'manage_stock' => false, 'price' => '0',
]);
T::is($free['price'], 0.0, 'an explicit 0 is a real price (free) and is preserved');

$null_price = AIOL_WooCommerce::map_offer_state([
    'stock_status' => 'instock', 'manage_stock' => false, 'price' => null,
]);
T::is($null_price['price'], null, 'null price means on request');

$negative = AIOL_WooCommerce::map_offer_state([
    'stock_status' => 'instock', 'manage_stock' => false, 'price' => '-5',
]);
T::is($negative['price'], null, 'a negative price is nonsensical and is refused, not published');

$decimal = AIOL_WooCommerce::map_offer_state([
    'stock_status' => 'instock', 'manage_stock' => false, 'price' => '12.50',
]);
T::is($decimal['price'], 12.5, 'decimal prices survive');

// --- availability vocabulary ------------------------------------------------------

T::is(AIOL_WooCommerce::map_offer_state(['stock_status' => 'outofstock'])['availability'],
    'out_of_stock', 'outofstock maps to out_of_stock');
T::is(AIOL_WooCommerce::map_offer_state(['stock_status' => 'onbackorder'])['availability'],
    'backorder', 'onbackorder maps to backorder');
T::is(AIOL_WooCommerce::map_offer_state(['stock_status' => 'instock'])['availability'],
    'in_stock', 'instock maps to in_stock');
T::is(AIOL_WooCommerce::map_offer_state([])['availability'],
    'in_stock', 'a missing stock_status defaults to in_stock, matching WooCommerce');

// Every produced availability must be a value Core actually accepts.
$valid = ['in_stock', 'out_of_stock', 'preorder', 'backorder', 'discontinued'];
foreach ([['stock_status'=>'instock'],['stock_status'=>'outofstock'],['stock_status'=>'onbackorder'],
          ['stock_status'=>'weird_future_value'],[]] as $case) {
    T::true(in_array(AIOL_WooCommerce::map_offer_state($case)['availability'], $valid, true),
        'produced availability is always a value Cloud Core accepts');
}

// --- the boundary: nothing about product identity is ever produced -----------------

$out = AIOL_WooCommerce::map_offer_state([
    'stock_status' => 'instock', 'manage_stock' => true, 'stock_quantity' => 3, 'price' => '9.99',
]);
T::is(array_keys($out), ['availability', 'stock_quantity', 'price'],
    'the mapper produces ONLY offer fields - no name, status, description or evidence');

// --- negative: the plugin cannot reach Core decision endpoints ---------------------

$client_src = file_get_contents(dirname(__DIR__) . '/includes/class-aiol-client.php');
foreach (['/evidence/', '/trust-records', '/products/', '/recommendations'] as $forbidden) {
    T::is(strpos($client_src, "'POST', '/api/v1" . $forbidden), false,
        "the HTTP client has no POST path to $forbidden");
}
T::true(strpos($client_src, '/adapter/commerce/mappings') !== false,
    'the client does have the commerce sync path');

/**
 * Strips comments and docblocks before asserting on source, using PHP's own
 * tokenizer. The first draft of this test grepped raw source for "verify"
 * and failed on the class docstring that EXPLAINS the adapter cannot
 * verify - a false positive. Asserting on executable code only is the
 * rigorous version.
 */
function aiol_code_only(string $path): string
{
    $out = '';
    foreach (token_get_all(file_get_contents($path)) as $token) {
        if (is_array($token)) {
            if (in_array($token[0], [T_COMMENT, T_DOC_COMMENT], true)) {
                continue;
            }
            $out .= $token[1];
        } else {
            $out .= $token;
        }
    }
    return $out;
}

$woo_code = aiol_code_only(dirname(__DIR__) . '/includes/class-aiol-woocommerce.php');
T::is(stripos($woo_code, 'verify'), false,
    'no executable code in the WooCommerce adapter performs verification');
T::is(strpos($woo_code, "'product_status'"), false,
    'the WooCommerce adapter never sends a product status');
T::is(stripos($woo_code, 'evidence'), false,
    'no executable code in the WooCommerce adapter touches evidence');
T::is(stripos($woo_code, 'trust'), false,
    'no executable code in the WooCommerce adapter touches trust');
T::true(strpos($woo_code, 'sync_offer') !== false,
    'it does call the one permitted write: offer sync');

exit(T::report('woocommerce'));
