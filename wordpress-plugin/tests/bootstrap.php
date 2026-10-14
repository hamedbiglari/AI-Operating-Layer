<?php
/**
 * Minimal harness for testing the plugin's PURE logic without WordPress.
 *
 * SCOPE, stated honestly: this covers the classes/methods that contain real
 * decisions and no WordPress dependency — schema mapping, status
 * aggregation, credential shape validation, error categorisation, log
 * redaction. It does NOT and cannot cover hooks, admin rendering, nonce
 * checks or HTTP, all of which need a live WordPress. Those are marked
 * ENVIRONMENT BLOCKED in the Phase 9 report with a manual QA procedure.
 *
 * A small number of WordPress functions are shimmed below purely so the
 * files can be loaded. The shims are trivial and are NOT used to simulate
 * WordPress behaviour in any assertion.
 */

declare(strict_types=1);

define('ABSPATH', __DIR__);
define('AIOL_VERSION', 'test');
define('AIOL_PLUGIN_DIR', dirname(__DIR__) . '/');
define('AIOL_PLUGIN_URL', 'http://example.test/');

if (!function_exists('__')) {
    function __(string $text, string $domain = ''): string { return $text; }
}
if (!function_exists('esc_url_raw')) {
    function esc_url_raw(string $url): string {
        return preg_match('#^https?://#i', $url) ? $url : '';
    }
}

require_once dirname(__DIR__) . '/includes/class-aiol-schema.php';
require_once dirname(__DIR__) . '/includes/class-aiol-status.php';
// Phase 13
require_once dirname(__DIR__) . '/includes/class-aiol-actors.php';
require_once dirname(__DIR__) . '/includes/class-aiol-access-gate.php';

require_once __DIR__ . '/bootstrap-assert.php';
