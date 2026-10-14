<?php
/**
 * Status aggregation tests — the "no misleading green light" rule.
 */

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

T::is(AIOL_Status::overall([]), AIOL_Status::NOT_CONFIGURED, 'no checks => not configured');
T::is(
    AIOL_Status::overall(['a' => AIOL_Status::OK, 'b' => AIOL_Status::OK]),
    AIOL_Status::OK,
    'all ok => ok'
);
T::is(
    AIOL_Status::overall(['a' => AIOL_Status::OK, 'b' => AIOL_Status::DEGRADED]),
    AIOL_Status::DEGRADED,
    'any degraded must NOT be rounded up to healthy'
);
T::is(
    AIOL_Status::overall(['a' => AIOL_Status::DEGRADED, 'b' => AIOL_Status::FAILED]),
    AIOL_Status::FAILED,
    'failed outranks degraded (worst wins)'
);
T::is(
    AIOL_Status::overall(['a' => AIOL_Status::OK, 'b' => AIOL_Status::NOT_CONFIGURED]),
    AIOL_Status::NOT_CONFIGURED,
    'unconfigured dependency is surfaced, not hidden behind an ok'
);

// Redis-down mapping: the exact scenario ADR-039 documents.
$down = AIOL_Status::from_core_health(['database' => 'ok', 'redis' => 'degraded: ConnectionError']);
T::is($down['database'], AIOL_Status::OK, 'database still ok');
T::is($down['redis'], AIOL_Status::DEGRADED, 'redis reported degraded, not failed');
T::is($down['rate_limiting'], AIOL_Status::DEGRADED, 'the CONSEQUENCE of redis loss is surfaced too');
T::is(AIOL_Status::overall($down), AIOL_Status::DEGRADED, 'overall is degraded, never a green light');

$healthy = AIOL_Status::from_core_health(['database' => 'ok', 'redis' => 'ok']);
T::is(AIOL_Status::overall($healthy), AIOL_Status::OK, 'fully healthy reports ok');

$db_down = AIOL_Status::from_core_health(['database' => 'error: OperationalError', 'redis' => 'ok']);
T::is($db_down['database'], AIOL_Status::FAILED, 'database failure is FAILED, not degraded');

// Every state has a distinct human label (never colour-only in the UI).
$labels = array_map([AIOL_Status::class, 'label'], [
    AIOL_Status::OK, AIOL_Status::DEGRADED, AIOL_Status::FAILED, AIOL_Status::NOT_CONFIGURED,
]);
T::is(count(array_unique($labels)), 4, 'each state has its own word, so colour is never the only signal');

exit(T::report('status'));
