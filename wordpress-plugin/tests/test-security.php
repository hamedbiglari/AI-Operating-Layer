<?php
/**
 * Security-oriented unit tests: secret redaction, token shape, error
 * categorisation, and masking. These are the pure-logic half of the
 * security surface; capability/nonce/CSRF enforcement lives in WordPress
 * code paths and is ENVIRONMENT BLOCKED here (see manual QA procedure).
 */

declare(strict_types=1);

define('ABSPATH', __DIR__);
define('AIOL_VERSION', 'test');

if (!function_exists('__')) { function __(string $t, string $d = ''): string { return $t; } }

// Minimal option store so Credentials/Logger can be exercised.
$GLOBALS['opts'] = [];
if (!function_exists('get_option')) {
    function get_option(string $k, $default = false) { return $GLOBALS['opts'][$k] ?? $default; }
    function update_option(string $k, $v, $autoload = null): bool { $GLOBALS['opts'][$k] = $v; return true; }
    function delete_option(string $k): bool { unset($GLOBALS['opts'][$k]); return true; }
    function add_option(string $k, $v, $x = '', $autoload = null): bool { $GLOBALS['opts'][$k] = $v; return true; }
    function untrailingslashit(string $s): string { return rtrim($s, '/'); }
}
class WP_Error {
    private string $code; private string $message;
    public function __construct(string $code = '', string $message = '', $data = null) { $this->code = $code; $this->message = $message; }
    public function get_error_code(): string { return $this->code; }
    public function get_error_message(): string { return $this->message; }
}
if (!function_exists('is_wp_error')) {
    function is_wp_error($t): bool { return $t instanceof WP_Error; }
}

require_once dirname(__DIR__) . '/includes/class-aiol-credentials.php';
require_once dirname(__DIR__) . '/includes/class-aiol-logger.php';
require_once dirname(__DIR__) . '/includes/class-aiol-client.php';
require_once __DIR__ . '/bootstrap-assert.php';

$c = new AIOL_Credentials();

// --- endpoint validation blocks SSRF-ish / nonsense input ---------------------

T::true(is_wp_error($c->save('', 'aiol_a_b')), 'empty endpoint rejected');
T::true(is_wp_error($c->save('javascript:alert(1)', 'aiol_a_b')), 'javascript: scheme rejected');
T::true(is_wp_error($c->save('/relative/path', 'aiol_a_b')), 'relative URL rejected');
T::true(is_wp_error($c->save('ftp://example.com', 'aiol_a_b')), 'non-http scheme rejected');
T::true(is_wp_error($c->save('https://core.example.com', '')), 'empty token rejected');
T::true(is_wp_error($c->save('https://core.example.com', 'not-a-token')), 'malformed token rejected early');
T::is($c->save('https://core.example.com/', 'aiol_abc123_secretvalue'), true, 'valid pair accepted');
T::is($c->get_endpoint(), 'https://core.example.com', 'trailing slash normalised');

// --- the secret is never exposed ------------------------------------------------

$masked = $c->masked_token();
T::is(strpos($masked, 'secretvalue'), false, 'masked token does not contain the secret');
T::true(strpos($masked, 'abc123') !== false, 'masked token keeps the non-secret key_id for support');

// --- logger redaction ------------------------------------------------------------

T::is(
    AIOL_Logger::redact('failed with aiol_abc123_supersecretvalue here'),
    'failed with aiol_***REDACTED*** here',
    'token-shaped strings are redacted from logs'
);
T::is(
    AIOL_Logger::redact('Authorization: Bearer aiol_x_y'),
    'Authorization: Bearer ***REDACTED***',
    'bearer headers are redacted'
);
T::is(
    strpos(AIOL_Logger::redact('Bearer eyJhbGciOi.JWTPAYLOAD.sig'), 'JWTPAYLOAD'),
    false,
    'non-aiol bearer tokens (e.g. a user JWT) are redacted too'
);

// --- error categories are stable and actionable ------------------------------------

T::is(AIOL_Client::category_for(401), 'unauthorized', '401');
T::is(AIOL_Client::category_for(403), 'forbidden', '403');
T::is(AIOL_Client::category_for(404), 'not_found', '404');
T::is(AIOL_Client::category_for(409), 'conflict', '409');
T::is(AIOL_Client::category_for(422), 'invalid', '422');
T::is(AIOL_Client::category_for(429), 'rate_limited', '429');
T::is(AIOL_Client::category_for(503), 'unavailable', '5xx');

// Retry guidance must be correct: retrying a 409 would be wrong.
T::true(AIOL_Client::is_retry_safe('unavailable'), 'network failure is retry-safe');
T::true(AIOL_Client::is_retry_safe('rate_limited'), 'rate limit is retry-safe');
T::is(AIOL_Client::is_retry_safe('conflict'), false, 'conflict is NOT retry-safe');
T::is(AIOL_Client::is_retry_safe('unauthorized'), false, 'bad credential is NOT fixed by retrying');
T::is(AIOL_Client::is_retry_safe('invalid'), false, 'validation failure is NOT retry-safe');

// No message may be the useless kind.
foreach (['unauthorized','forbidden','not_found','conflict','invalid','rate_limited','unavailable','not_configured'] as $cat) {
    $msg = AIOL_Client::message_for($cat);
    T::true(strlen($msg) > 30, "message for '$cat' is substantive, not 'something went wrong'");
}

exit(T::report('security'));
