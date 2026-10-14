<?php
/**
 * JSON-LD safety tests.
 *
 * These are the adversarial ones: each asks "can the adapter be made to
 * publish a false public claim?" A failure here is not a cosmetic bug — it
 * is the plugin asserting something to search engines and AI agents that
 * Cloud Core never asserted.
 */

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

$published = [
    'name' => 'Taranjabin 500g',
    'status' => 'published',
    'brand' => 'BrandX',
    'category' => 'sweeteners',
];

// --- The core rule: nothing is invented ------------------------------------

T::null(
    AIOL_Schema::build_from_core(['name' => 'X', 'status' => 'draft']),
    'DRAFT product must not be published as schema'
);
T::null(
    AIOL_Schema::build_from_core(['name' => 'X', 'status' => 'archived']),
    'ARCHIVED product must not be published as schema'
);
T::null(
    AIOL_Schema::build_from_core(['name' => '', 'status' => 'published']),
    'Nameless product is not publishable'
);

$out = AIOL_Schema::build_from_core($published);
T::is($out['@type'] ?? null, 'Product', 'published product renders as Product');
T::is($out['brand']['name'] ?? null, 'BrandX', 'brand is nested correctly');
T::is(isset($out['offers']), false, 'no offer data => no offers node invented');

// --- price semantics: null is NOT zero --------------------------------------

$on_request = AIOL_Schema::build_from_core($published + [
    'offer' => ['availability' => 'in_stock', 'price' => null, 'currency' => 'EUR'],
]);
T::is(isset($on_request['offers']['price']), false, 'price=null (on request) must NOT emit a price');
T::is($on_request['offers']['availability'] ?? null, 'https://schema.org/InStock', 'availability still emitted');

$free = AIOL_Schema::build_from_core($published + [
    'offer' => ['availability' => 'in_stock', 'price' => 0, 'currency' => 'EUR'],
]);
T::is($free['offers']['price'] ?? null, '0.00', 'price=0 (genuinely free) IS emitted as 0.00');

$priced = AIOL_Schema::build_from_core($published + [
    'offer' => ['availability' => 'in_stock', 'price' => 12.5, 'currency' => 'eur'],
]);
T::is($priced['offers']['price'] ?? null, '12.50', 'price formatted to 2dp');
T::is($priced['offers']['priceCurrency'] ?? null, 'EUR', 'currency upper-cased');

$no_currency = AIOL_Schema::build_from_core($published + [
    'offer' => ['availability' => 'in_stock', 'price' => 12.5],
]);
T::is(isset($no_currency['offers']['price']), false, 'price without currency is not a meaningful claim; omitted');

$negative = AIOL_Schema::build_from_core($published + [
    'offer' => ['availability' => 'in_stock', 'price' => -5, 'currency' => 'EUR'],
]);
T::is(isset($negative['offers']), false, 'nonsensical negative price => refuse the whole offer');

// --- availability mapping ------------------------------------------------------

T::is(AIOL_Schema::availability_url('in_stock'), 'https://schema.org/InStock', 'in_stock');
T::is(AIOL_Schema::availability_url('out_of_stock'), 'https://schema.org/OutOfStock', 'out_of_stock');
T::is(AIOL_Schema::availability_url('preorder'), 'https://schema.org/PreOrder', 'preorder');
T::is(AIOL_Schema::availability_url('backorder'), 'https://schema.org/BackOrder', 'backorder');
T::null(AIOL_Schema::availability_url('discontinued'), 'discontinued asserts nothing');
T::null(AIOL_Schema::availability_url('something_new'), 'unknown availability asserts nothing (fails closed)');

// --- evidence/trust must never leak into public markup -------------------------

$with_claims = AIOL_Schema::build_from_core($published + [
    'evidence' => [['claim' => 'Cures disease X', 'verification_status' => 'unverified']],
    'trust' => [['claim' => 'Certified', 'verification_status' => 'rejected']],
]);
$encoded = json_encode($with_claims);
T::is(strpos($encoded, 'Cures disease X'), false, 'unverified evidence claim never reaches schema output');
T::is(strpos($encoded, 'Certified'), false, 'rejected trust claim never reaches schema output');

// --- malicious input -------------------------------------------------------------

$xss = AIOL_Schema::build_from_core([
    'name' => '</script><script>alert(1)</script>',
    'status' => 'published',
    'offer' => ['availability' => 'in_stock', 'url' => 'javascript:alert(1)'],
]);
T::is(isset($xss['offers']['url']), false, 'javascript: URL is rejected, not rendered');
$json = json_encode($xss, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
// wp_json_encode in production adds the same protection; here we assert the
// value survives as DATA rather than being interpreted.
T::true(is_string($json) && strpos($json, 'alert(1)') !== false, 'hostile name is carried as data, not executed');

exit(T::report('schema'));
