<?php
/**
 * Bulk-sync guard (ADR-054).
 *
 * The failure this prevents: offer sync is an HTTP call, so a 5,000-product
 * CSV import or a 200-row bulk edit would issue one synchronous request per
 * product inside a single PHP request — timeout, half-synced catalogue,
 * retry storm against Cloud Core.
 *
 * The guard must satisfy two properties that pull against each other:
 *   1. it must STOP calling Core past a threshold, and
 *   2. it must NOT LOSE the work it stopped doing.
 *
 * A guard that only did (1) would silently drop syncs, which is worse than
 * being slow.
 */

declare(strict_types=1);

define('ABSPATH', __DIR__);
if (!function_exists('__')) { function __(string $t, string $d = ''): string { return $t; } }

$GLOBALS['opts'] = [];
$GLOBALS['scheduled'] = [];
if (!function_exists('get_option')) {
    function get_option(string $k, $d = false) { return $GLOBALS['opts'][$k] ?? $d; }
    function update_option(string $k, $v, $a = null): bool { $GLOBALS['opts'][$k] = $v; return true; }
    function delete_option(string $k): bool { unset($GLOBALS['opts'][$k]); return true; }
}
if (!function_exists('wp_next_scheduled')) {
    function wp_next_scheduled(string $hook) { return $GLOBALS['scheduled'][$hook] ?? false; }
    function wp_schedule_single_event(int $ts, string $hook): bool { $GLOBALS['scheduled'][$hook] = $ts; return true; }
}

require_once __DIR__ . '/bootstrap-assert.php';
require_once dirname(__DIR__) . '/includes/class-aiol-woocommerce.php';

// --- property 1: the guard actually stops -----------------------------------

T::is(AIOL_WooCommerce::should_defer(0), false, 'the first sync in a request proceeds');
T::is(AIOL_WooCommerce::should_defer(19), false, 'sync 20 of 20 still proceeds');
T::is(AIOL_WooCommerce::should_defer(20), true, 'sync 21 is deferred — the budget is spent');
T::is(AIOL_WooCommerce::should_defer(5000), true, 'a bulk import is deferred, not attempted inline');

// The threshold is a parameter, so the guard is testable and tunable
// without editing the class.
T::is(AIOL_WooCommerce::should_defer(3, 3), true, 'the threshold is honoured when injected');
T::is(AIOL_WooCommerce::should_defer(2, 3), false, 'below an injected threshold, work proceeds');

// --- property 2: deferred work is PERSISTED, not dropped ----------------------

$GLOBALS['opts'] = [];
$GLOBALS['scheduled'] = [];

AIOL_WooCommerce::defer(101);
AIOL_WooCommerce::defer(102);
AIOL_WooCommerce::defer(103);

$queue = AIOL_WooCommerce::deferred_queue();
T::is(count($queue), 3, 'deferred product ids are persisted, so a timeout does not lose them');
T::true(in_array(102, $queue, true), 'the right ids are queued');

// Deferral must be idempotent: a product hit twice in one bulk run must not
// be drained twice.
AIOL_WooCommerce::defer(102);
T::is(count(AIOL_WooCommerce::deferred_queue()), 3, 'deferring the same product twice does not duplicate it');

// --- the drain must be scheduled, or the queue never empties -------------------

T::true(wp_next_scheduled(AIOL_WooCommerce::CRON_HOOK) !== false,
    'a drain event is scheduled — a persisted queue with no drain is just a leak');

// Scheduling is not duplicated on every deferral.
$first = wp_next_scheduled(AIOL_WooCommerce::CRON_HOOK);
AIOL_WooCommerce::defer(104);
T::is(wp_next_scheduled(AIOL_WooCommerce::CRON_HOOK), $first,
    'an already-scheduled drain is not rescheduled on every deferral');

// --- the queue survives across requests ---------------------------------------

$persisted = $GLOBALS['opts']['aiol_deferred_offer_sync'] ?? null;
T::true(is_array($persisted) && count($persisted) === 4,
    'the queue lives in an option, so it survives the request that created it');

// --- uninstall must not leave the queue behind ---------------------------------

$uninstall = file_get_contents(dirname(__DIR__) . '/uninstall.php');
T::true(strpos($uninstall, 'aiol_deferred_offer_sync') !== false,
    'uninstall removes the deferral queue');

$bootstrap = file_get_contents(dirname(__DIR__) . '/ai-operating-layer.php');
T::true(strpos($bootstrap, 'wp_clear_scheduled_hook') !== false,
    'deactivation clears the cron event, leaving no orphaned schedule');

// --- the guard is actually WIRED into the sync path ----------------------------
//
// The R1 lesson: a guard that exists but is never called is not a guard.
// Assert against executable code only, per the test-wiring.php lesson.

function aiol_bulk_code(string $path): string
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
$code = aiol_bulk_code(dirname(__DIR__) . '/includes/class-aiol-woocommerce.php');
T::true(strpos($code, 'self::should_defer(') !== false,
    'should_defer() is CALLED in the sync path, not merely defined');
T::true(strpos($code, 'self::defer(') !== false, 'defer() is called when the budget is spent');
T::true(strpos($code, "add_action(self::CRON_HOOK") !== false,
    'the drain handler is registered for the cron hook');

exit(T::report('bulk-guard'));
