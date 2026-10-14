<?php
/**
 * Status aggregation.
 *
 * The design rule here (master spec §22 of the Phase 9 brief, and plain
 * honesty): DO NOT COLLAPSE EVERYTHING INTO ONE GREEN LIGHT. A single
 * indicator that says "Healthy" while Redis is down and rate limiting is
 * unenforced is a lie of omission that an operator cannot act on.
 *
 * So each dependency reports separately, and the overall state is the WORST
 * of its parts, with the reason named. `degraded` is a first-class state —
 * distinct from both healthy and failed — because Cloud Core's rate limiter
 * fails open by design (ADR-039): the system genuinely is working AND
 * genuinely is missing a protection, and both halves of that need saying.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Status
{
    public const OK           = 'ok';
    public const DEGRADED     = 'degraded';
    public const FAILED       = 'failed';
    public const NOT_CONFIGURED = 'not_configured';

    /**
     * Pure aggregation, static and WordPress-free so it is unit-testable.
     *
     * @param array $checks  ['label' => 'ok'|'degraded'|'failed'|'not_configured']
     */
    public static function overall(array $checks): string
    {
        if ($checks === []) {
            return self::NOT_CONFIGURED;
        }
        $values = array_values($checks);
        if (in_array(self::NOT_CONFIGURED, $values, true)) {
            return self::NOT_CONFIGURED;
        }
        if (in_array(self::FAILED, $values, true)) {
            return self::FAILED;   // worst wins
        }
        if (in_array(self::DEGRADED, $values, true)) {
            return self::DEGRADED; // never rounded up to ok
        }
        return self::OK;
    }

    /**
     * Human-readable label. Every state has BOTH a word and (in the UI) an
     * icon + colour, because colour alone is not an accessible signal.
     */
    public static function label(string $state): string
    {
        switch ($state) {
            case self::OK:             return __('Healthy', 'ai-operating-layer');
            case self::DEGRADED:       return __('Degraded', 'ai-operating-layer');
            case self::FAILED:         return __('Failed', 'ai-operating-layer');
            case self::NOT_CONFIGURED: return __('Not configured', 'ai-operating-layer');
            default:                   return __('Unknown', 'ai-operating-layer');
        }
    }

    /**
     * Maps a Cloud Core /health/ready payload onto adapter-visible checks.
     * Note Redis maps to DEGRADED, not FAILED: Core keeps serving without
     * it, and saying "failed" would overstate the problem just as saying
     * "healthy" would understate it.
     */
    public static function from_core_health(array $health): array
    {
        $checks = [];
        $checks['database'] = ($health['database'] ?? '') === 'ok' ? self::OK : self::FAILED;

        $redis = (string) ($health['redis'] ?? '');
        if ($redis === 'ok') {
            $checks['redis'] = self::OK;
            $checks['rate_limiting'] = self::OK;
        } else {
            $checks['redis'] = self::DEGRADED;
            // Stated explicitly so the merchant sees the consequence, not
            // just the cause.
            $checks['rate_limiting'] = self::DEGRADED;
        }
        return $checks;
    }
}
