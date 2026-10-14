<?php
/**
 * Absorption regression tests.
 *
 * Two jobs, and the second is the unusual one:
 *
 * 1. POSITIVE — every capability the map marks REUSE or REFACTOR still
 *    works, so absorption did not quietly lose functionality.
 *
 * 2. NEGATIVE — every capability marked REPLACE or DEPRECATE is *provably
 *    absent*. A capability map is a claim; these assertions are the
 *    evidence. Without them, "we removed the parallel API" is something a
 *    reviewer has to take on faith.
 */

declare(strict_types=1);

define('ABSPATH', __DIR__);
define('AIOL_VERSION', 'test');
define('AIOL_PLUGIN_DIR', dirname(__DIR__) . '/');

if (!function_exists('__')) { function __(string $t, string $d = ''): string { return $t; } }
if (!function_exists('esc_url_raw')) { function esc_url_raw(string $u): string { return preg_match('#^https?://#i',$u)?$u:''; } }
$GLOBALS['opts'] = [];
if (!function_exists('get_option')) {
    function get_option(string $k, $d = false) { return $GLOBALS['opts'][$k] ?? $d; }
    function update_option(string $k, $v, $a = null): bool { $GLOBALS['opts'][$k] = $v; return true; }
    function delete_option(string $k): bool { unset($GLOBALS['opts'][$k]); return true; }
    function untrailingslashit(string $s): string { return rtrim($s, '/'); }
    function sanitize_text_field(string $s): string { return trim(strip_tags($s)); }
    function wp_unslash($s) { return $s; }
}
class WP_Error {
    private string $code; private string $message;
    public function __construct(string $c='', string $m='', $d=null){ $this->code=$c; $this->message=$m; }
    public function get_error_code(): string { return $this->code; }
    public function get_error_message(): string { return $this->message; }
}
if (!function_exists('is_wp_error')) { function is_wp_error($t): bool { return $t instanceof WP_Error; } }

require_once __DIR__ . '/bootstrap-assert.php';
require_once dirname(__DIR__) . '/includes/class-aiol-credentials.php';
require_once dirname(__DIR__) . '/includes/class-aiol-actors.php';
require_once dirname(__DIR__) . '/includes/class-aiol-representations.php';

// =====================================================================
// NEGATIVE: replaced / deprecated capabilities must be provably gone
// =====================================================================

$plugin_root = dirname(__DIR__);
$php_files = [];
$rii = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($plugin_root));
foreach ($rii as $file) {
    if ($file->isFile() && $file->getExtension() === 'php' && strpos($file->getPathname(), '/tests/') === false) {
        $php_files[] = $file->getPathname();
    }
}
$all_source = '';
foreach ($php_files as $f) { $all_source .= file_get_contents($f); }

T::true(count($php_files) > 10, 'source scan found the plugin files');

// #7 Structured data built from WordPress data — REPLACED by Core-backed schema.
T::is(strpos($all_source, 'AAT_Structured_Data'), false, 'legacy structured-data class is gone');

// #10/#11/#12/#13 The parallel API, its keys, its auth and its rate limiter.
T::is(strpos($all_source, 'AAT_Gateway'), false, 'legacy AI Gateway class is gone');
T::is(strpos($all_source, 'ai-access-toolkit/v1'), false, 'legacy REST namespace is gone');
T::is(strpos($all_source, 'register_rest_route'), false,
    'plugin registers NO REST routes — Cloud Core is the only canonical API');
T::is(strpos($all_source, 'generate_key'), false, 'legacy API-key generation is gone');
T::is(strpos($all_source, 'X-AAT-API-Key'), false, 'legacy API-key header is gone');
T::is(strpos($all_source, 'AAT_RATE_LIMIT'), false, 'legacy per-IP rate limiting is gone');

// #23 The single composite readiness score.
T::is(strpos($all_source, 'AAT_Score_Calculator'), false, 'legacy score calculator is gone');
T::is(strpos($all_source, 'readiness_score'), false, 'no single composite readiness score survives');

// No AAT_* class survives at all.
T::is(preg_match('/\bclass\s+AAT_/', $all_source), 0, 'no legacy AAT_ class was copied in');

// Privacy. Originally "no IP address is read anywhere" (ADR-046). ADR-079
// (ACCEPTED, Phase 13, owner decision P13-REQ-002) supersedes that: the
// visitor IP IS read — by the geo module only — and sent to Cloud Core,
// which truncates it and nulls the full value at its retention date. What
// still holds: the plugin itself never persists an IP. Updated in the final
// existing-owner closure pass (the old assertion contradicted an accepted ADR).
$ip_readers = [];
foreach (new RecursiveIteratorIterator(new RecursiveDirectoryIterator(dirname(__DIR__) . '/includes')) as $f) {
    if (substr((string) $f, -4) === '.php' && strpos(file_get_contents((string) $f), 'REMOTE_ADDR') !== false) {
        $ip_readers[] = basename((string) $f);
    }
}
T::is($ip_readers, ['class-aiol-geo.php'], 'the client IP is read in exactly one place: the geo module (ADR-079)');
$geo_src = file_get_contents(dirname(__DIR__) . '/includes/class-aiol-geo.php');
T::is(preg_match('/update_option|add_option|update_post_meta|add_post_meta|set_transient|\$wpdb/', $geo_src), 0,
    'the geo module never persists an IP inside WordPress');
T::is(strpos(str_replace(file_get_contents(dirname(__DIR__) . '/includes/class-aiol-geo.php'), '', $all_source), 'REMOTE_ADDR'), false,
    'no other file reads REMOTE_ADDR');

// =====================================================================
// POSITIVE: retained capabilities still work
// =====================================================================

// --- #14/#15 actor detection, rebuilt -------------------------------------

$gptbot = AIOL_Actors::classify('Mozilla/5.0 (compatible; GPTBot/1.0; +https://openai.com/gptbot)');
T::is($gptbot['type'], AIOL_Actors::AI_CRAWLER, 'GPTBot classified as an AI crawler');
T::is($gptbot['confidence'], AIOL_Actors::DETECTED,
    'header match is DETECTED, never VERIFIED — a User-Agent is a claim');

$chatgpt_user = AIOL_Actors::classify('Mozilla/5.0 ChatGPT-User/1.0');
T::is($chatgpt_user['type'], AIOL_Actors::AI_USER_AGENT,
    'ChatGPT-User is a user-driven agent, NOT the same actor as a crawler');
T::true($gptbot['type'] !== $chatgpt_user['type'],
    'the legacy "all AI bots" conflation is genuinely fixed');

T::is(AIOL_Actors::classify('Googlebot/2.1')['type'], AIOL_Actors::SEARCH_CRAWLER, 'Googlebot is a search crawler');
T::is(AIOL_Actors::classify('Mozilla/5.0 (Macintosh) Safari/605')['type'], AIOL_Actors::HUMAN, 'browser => human');
T::is(AIOL_Actors::classify('Mozilla/5.0 (Macintosh) Safari/605')['confidence'], AIOL_Actors::PROBABLE,
    'browser detection is PROBABLE, not asserted');
T::is(AIOL_Actors::classify('')['type'], AIOL_Actors::UNKNOWN, 'empty UA => unknown');
T::is(AIOL_Actors::classify('SomeRandomCrawler/1.0')['confidence'], AIOL_Actors::PROBABLE,
    'unknown crawler-ish UA is PROBABLE, not a fabricated identity');

// Nothing is ever VERIFIED, because verification is not implemented.
foreach (['GPTBot', 'ClaudeBot', 'Googlebot', 'Mozilla/5.0'] as $ua) {
    T::true(AIOL_Actors::classify($ua)['confidence'] !== AIOL_Actors::VERIFIED,
        "no actor is claimed VERIFIED without IP/DNS proof ($ua)");
}

// --- #5 llms.txt, retained with an honesty header ---------------------------

$body = AIOL_Representations::llms_txt_body([
    ['title' => 'Taranjabin', 'url' => 'https://x.test/t', 'excerpt' => 'A sweet exudate.'],
    ['title' => '', 'url' => 'https://x.test/skip', 'excerpt' => ''],
], 'My Shop', 'https://x.test');

T::true(strpos($body, '# My Shop') !== false, 'llms.txt carries the site name');
T::true(strpos($body, '[Taranjabin](https://x.test/t)') !== false, 'entries are rendered');
T::is(strpos($body, 'x.test/skip'), false, 'entries without a title are skipped, not rendered broken');
T::true(strpos($body, 'not verified business data') !== false,
    'llms.txt states it is a representation, not Business Truth');
T::is(strpos($body, 'price'), false, 'no price data appears in llms.txt');

// --- #1-4, #8-9, #23 diagnostics: UNKNOWN must exist and behave -------------

require_once dirname(__DIR__) . '/includes/class-aiol-diagnostics.php';

$dims = AIOL_Diagnostics::dimensions([
    'https'   => ['status' => AIOL_Diagnostics::PASS, 'label' => '', 'detail' => ''],
    'robots'  => ['status' => AIOL_Diagnostics::UNKNOWN, 'label' => '', 'detail' => ''],
    'sitemap' => ['status' => AIOL_Diagnostics::PASS, 'label' => '', 'detail' => ''],
]);
T::is($dims['technical_discoverability']['state'], AIOL_Diagnostics::UNKNOWN,
    'an UNKNOWN check must NOT be rounded up to pass');

$dims_fail = AIOL_Diagnostics::dimensions([
    'https'  => ['status' => AIOL_Diagnostics::PASS, 'label' => '', 'detail' => ''],
    'robots' => ['status' => AIOL_Diagnostics::FAIL, 'label' => '', 'detail' => ''],
]);
T::is($dims_fail['technical_discoverability']['state'], AIOL_Diagnostics::FAIL, 'worst result wins');

// Dimensions the adapter genuinely cannot measure must say UNKNOWN, not 0.
foreach (['knowledge_coverage', 'evidence_coverage', 'trust_coverage', 'commerce_readiness', 'ai_visibility'] as $d) {
    T::is($dims[$d]['state'], AIOL_Diagnostics::UNKNOWN, "$d is honestly UNKNOWN, not a fabricated number");
}

// --- HTTPS credential policy (ADR-045) ---------------------------------------

$c = new AIOL_Credentials();
T::true(is_wp_error($c->save('http://core.example.com', 'aiol_a_bcdef')),
    'plain http:// to a remote host is REFUSED — the token would travel in clear text');
T::is($c->save('http://localhost:8000', 'aiol_a_bcdef'), true, 'http://localhost is allowed for local dev');
T::is($c->save('http://127.0.0.1:8000', 'aiol_a_bcdef'), true, 'http://127.0.0.1 is allowed');
T::true(is_wp_error($c->save('http://localhost.attacker.com', 'aiol_a_bcdef')),
    'substring "localhost" does NOT bypass the HTTPS policy');
T::is($c->save('https://core.example.com', 'aiol_a_bcdef'), true, 'https is always allowed');

// =====================================================================
// Phase 9 reconciliation regressions (found by forensic review, not by
// the original test suite - which is the point of recording them here)
// =====================================================================

// R1: `aiol_mapping_changed` was listened for but never fired anywhere.
// ADR-049 claimed a mapping change invalidated representations; it did
// not. This asserts the hook is now genuinely fired, so the claim and
// the code agree.
$admin_src = file_get_contents($plugin_root . '/admin/class-aiol-admin.php');
T::true(strpos($admin_src, "do_action('aiol_mapping_changed'") !== false,
    'R1: aiol_mapping_changed is actually FIRED, not only listened for');
T::true(substr_count($admin_src, "do_action('aiol_mapping_changed'") >= 2,
    'R1: fired on both link-change and unlink paths');

$repr_src = file_get_contents($plugin_root . '/includes/class-aiol-representations.php');
T::true(strpos($repr_src, "add_action('aiol_mapping_changed'") !== false,
    'R1: the listener still exists to receive it');

// R3: instance-to-static call replaced with an explicit static call.
T::is(strpos($admin_src, '$this->cache::flush_all'), false,
    'R3: cache flushing is called statically and unambiguously');

exit(T::report('absorption'));
