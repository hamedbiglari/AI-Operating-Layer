<?php
/**
 * Transient cache with DELIBERATELY ASYMMETRIC lifetimes.
 *
 * The asymmetry is the entire point (master spec §27's Product/Offer split,
 * carried into the adapter):
 *
 *   Product identity  - what the thing IS      - changes rarely  - 1 hour
 *   Offer / price / stock - what it COSTS now  - changes hourly  - 60 seconds
 *
 * A stale product name is a cosmetic annoyance. A stale price shown to a
 * shopper, or a stale "in stock" on a sold-out item, is commercial
 * misinformation that a merchant can be held to. So offers get a short TTL
 * and are never cached at all when the adapter is rendering a purchase-facing
 * signal it is unsure about.
 *
 * Cached data never overrides Core: on any doubt the cache is bypassed, and
 * a cache miss is always safe because the answer is refetched from Core.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Cache
{
    public const PREFIX = 'aiol_';

    /** Stable: product identity, mapping lists. */
    public const TTL_STABLE = 3600;

    /** Volatile: anything carrying price, stock or availability. */
    public const TTL_VOLATILE = 60;

    private const INDEX_OPTION = 'aiol_cache_keys';

    public function get(string $key)
    {
        return get_transient(self::PREFIX . $key);
    }

    public function set(string $key, $value, int $ttl = self::TTL_STABLE): void
    {
        set_transient(self::PREFIX . $key, $value, $ttl);
        $index = get_option(self::INDEX_OPTION, []);
        if (!is_array($index)) {
            $index = [];
        }
        if (!in_array($key, $index, true)) {
            $index[] = $key;
            update_option(self::INDEX_OPTION, $index, false);
        }
    }

    public function forget(string $key): void
    {
        delete_transient(self::PREFIX . $key);
    }

    /**
     * Tracks its own keys rather than issuing a wildcard DELETE against
     * wp_options - the latter is a common plugin anti-pattern that can
     * remove other plugins' transients on shared prefixes.
     */
    public static function flush_all(): void
    {
        $index = get_option(self::INDEX_OPTION, []);
        if (is_array($index)) {
            foreach ($index as $key) {
                delete_transient(self::PREFIX . $key);
            }
        }
        delete_option(self::INDEX_OPTION);
    }
}
