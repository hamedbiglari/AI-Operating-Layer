<?php
/**
 * Technical discoverability diagnostics — absorbed from the legacy
 * AI Access Toolkit readiness checks (capability map #1-4, #8-9, #23).
 *
 * TWO CHANGES FROM THE LEGACY BEHAVIOUR, both deliberate:
 *
 * 1. **UNKNOWN is a real result.** The legacy checks had PASS/FAIL only, so
 *    a robots.txt that could not be fetched (timeout, firewall, local dev)
 *    scored as FAIL — reporting a problem that may not exist. A check that
 *    could not run now says so.
 *
 * 2. **There is no single score.** The legacy plugin produced one 0-100
 *    "AI Readiness Score". That number implied an authority it did not
 *    have, and a merchant cannot act on it. Replaced by decomposed
 *    dimensions, each labelled INTERNAL DIAGNOSTIC (ADR-047).
 *
 * These checks are deliberately cheap and deterministic: local option reads
 * and at most one short HTTP HEAD/GET to the site's own URL. No LLM call, no
 * Cloud Core call, no external service. They must remain safe to run on an
 * admin page load.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Diagnostics
{
    public const PASS    = 'pass';
    public const WARNING = 'warning';
    public const FAIL    = 'fail';
    public const UNKNOWN = 'unknown';

    /** Cheap: cached, because an admin page load must not re-fetch robots.txt. */
    private const CACHE_KEY = 'diagnostics';
    private const CACHE_TTL = 900;

    private AIOL_Cache $cache;

    public function __construct(AIOL_Cache $cache)
    {
        $this->cache = $cache;
    }

    /**
     * @return array<string, array{status:string,label:string,detail:string}>
     */
    public function run(bool $use_cache = true): array
    {
        if ($use_cache) {
            $cached = $this->cache->get(self::CACHE_KEY);
            if (is_array($cached)) {
                return $cached;
            }
        }

        $results = [
            'https'            => self::check_https(),
            'robots'           => $this->check_robots(),
            'sitemap'          => $this->check_sitemap(),
            'canonical'        => self::check_canonical(),
            'meta_description' => self::check_meta_description(),
            'llms_txt'         => self::check_llms_txt(),
            'structured_data'  => self::check_structured_data(),
        ];

        $this->cache->set(self::CACHE_KEY, $results, self::CACHE_TTL);
        return $results;
    }

    // ---------------------------------------------------------------- checks

    public static function check_https(): array
    {
        $home = (string) get_option('home', '');
        if ($home === '') {
            return self::result(self::UNKNOWN, __('Site address', 'ai-operating-layer'),
                __('The site address is not set, so HTTPS cannot be checked.', 'ai-operating-layer'));
        }
        if (stripos($home, 'https://') === 0) {
            return self::result(self::PASS, __('HTTPS', 'ai-operating-layer'),
                __('The site is served over HTTPS.', 'ai-operating-layer'));
        }
        if (AIOL_Credentials::is_local_host($home)) {
            return self::result(self::WARNING, __('HTTPS', 'ai-operating-layer'),
                __('This is a local development site, so plain HTTP is expected here. A production site must use HTTPS.', 'ai-operating-layer'));
        }
        return self::result(self::FAIL, __('HTTPS', 'ai-operating-layer'),
            __('The site is served over plain HTTP. Install a TLS certificate — AI clients and search engines de-prioritise insecure sites, and credentials sent from this site are readable in transit.', 'ai-operating-layer'));
    }

    private function check_robots(): array
    {
        $url      = home_url('/robots.txt');
        $response = wp_remote_get($url, ['timeout' => 5, 'redirection' => 2]);

        if (is_wp_error($response)) {
            // Was FAIL in the legacy plugin. It is not: we simply could not
            // look.
            return self::result(self::UNKNOWN, __('robots.txt', 'ai-operating-layer'),
                __('robots.txt could not be fetched from this site, so its contents are unknown. This is common on local or firewalled installs.', 'ai-operating-layer'));
        }
        $code = (int) wp_remote_retrieve_response_code($response);
        if ($code !== 200) {
            return self::result(self::WARNING, __('robots.txt', 'ai-operating-layer'),
                /* translators: %d: HTTP status code */
                sprintf(__('robots.txt returned HTTP %d. Crawlers expect it to exist and return 200.', 'ai-operating-layer'), $code));
        }

        $body = (string) wp_remote_retrieve_body($response);
        if (preg_match('/^\s*Disallow:\s*\/\s*$/mi', $body) && !preg_match('/^\s*Allow:/mi', $body)) {
            return self::result(self::FAIL, __('robots.txt', 'ai-operating-layer'),
                __('robots.txt disallows all crawling. No search engine or AI client will read this site until that rule is removed.', 'ai-operating-layer'));
        }
        return self::result(self::PASS, __('robots.txt', 'ai-operating-layer'),
            __('robots.txt is reachable and does not block all crawling.', 'ai-operating-layer'));
    }

    private function check_sitemap(): array
    {
        foreach (['/wp-sitemap.xml', '/sitemap.xml', '/sitemap_index.xml'] as $path) {
            $response = wp_remote_head(home_url($path), ['timeout' => 5, 'redirection' => 2]);
            if (is_wp_error($response)) {
                continue;
            }
            if ((int) wp_remote_retrieve_response_code($response) === 200) {
                return self::result(self::PASS, __('XML sitemap', 'ai-operating-layer'),
                    /* translators: %s: sitemap path */
                    sprintf(__('A sitemap was found at %s.', 'ai-operating-layer'), $path));
            }
        }
        return self::result(self::WARNING, __('XML sitemap', 'ai-operating-layer'),
            __('No sitemap was found at the usual locations. WordPress generates one at /wp-sitemap.xml unless a plugin or setting disables it.', 'ai-operating-layer'));
    }

    public static function check_canonical(): array
    {
        // rel=canonical is emitted by core since 4.6 via wp_head; a theme
        // that drops wp_head breaks it. We can only check that the hook is
        // present, which is why this is never a hard PASS claim about every
        // page.
        if (has_action('wp_head', 'rel_canonical') !== false) {
            return self::result(self::PASS, __('Canonical URLs', 'ai-operating-layer'),
                __('WordPress is emitting canonical URLs.', 'ai-operating-layer'));
        }
        return self::result(self::WARNING, __('Canonical URLs', 'ai-operating-layer'),
            __('Canonical URL output is not registered. An SEO plugin may be handling it instead — if not, duplicate URLs may be indexed separately.', 'ai-operating-layer'));
    }

    public static function check_meta_description(): array
    {
        $known_seo = ['wordpress-seo/wp-seo.php', 'seo-by-rank-math/rank-math.php', 'all-in-one-seo-pack/all_in_one_seo_pack.php'];
        if (function_exists('is_plugin_active')) {
            foreach ($known_seo as $plugin) {
                if (is_plugin_active($plugin)) {
                    return self::result(self::PASS, __('Meta descriptions', 'ai-operating-layer'),
                        __('An SEO plugin is active and is expected to emit meta descriptions.', 'ai-operating-layer'));
                }
            }
        }
        // Honest: WordPress core does not emit meta descriptions, but a
        // theme might. We cannot know without rendering a page.
        return self::result(self::UNKNOWN, __('Meta descriptions', 'ai-operating-layer'),
            __('No known SEO plugin is active. WordPress does not emit meta descriptions by itself, but your theme might — this cannot be confirmed without inspecting a rendered page.', 'ai-operating-layer'));
    }

    public static function check_llms_txt(): array
    {
        if (AIOL_Representations::is_llms_txt_enabled()) {
            return self::result(self::PASS, __('llms.txt', 'ai-operating-layer'),
                __('An llms.txt representation is being served at /llms.txt.', 'ai-operating-layer'));
        }
        return self::result(self::WARNING, __('llms.txt', 'ai-operating-layer'),
            __('llms.txt is turned off. It is an optional, emerging convention — enabling it costs nothing and gives AI clients a plain-text index of your content.', 'ai-operating-layer'));
    }

    public static function check_structured_data(): array
    {
        if (!(new AIOL_Credentials())->is_configured()) {
            return self::result(self::UNKNOWN, __('Structured data', 'ai-operating-layer'),
                __('Product structured data is generated from Cloud Core, which is not connected yet.', 'ai-operating-layer'));
        }
        return self::result(self::PASS, __('Structured data', 'ai-operating-layer'),
            __('Product structured data is generated from Cloud Core for mapped products.', 'ai-operating-layer'));
    }

    // ------------------------------------------------------------ dimensions

    /**
     * Decomposed dimensions replacing the legacy single score (ADR-047).
     *
     * Each dimension reports the checks that feed it, so a merchant can see
     * WHY it looks the way it does. UNKNOWN checks are counted as unknown —
     * never silently as pass, which is the specific dishonesty the legacy
     * score enabled.
     *
     * @return array<string, array{state:string,detail:string}>
     */
    public static function dimensions(array $results): array
    {
        $technical = self::roll_up($results, ['https', 'robots', 'sitemap', 'canonical', 'meta_description']);
        $machine   = self::roll_up($results, ['llms_txt', 'structured_data']);

        return [
            'technical_discoverability' => $technical,
            'machine_readability'       => $machine,
            // DEFERRED to Phase 12 (AI Visibility) and Phases 7/8 — the
            // adapter cannot measure these and must not pretend to.
            'knowledge_coverage'  => ['state' => self::UNKNOWN, 'detail' => __('Measured in Cloud Core, not by this adapter.', 'ai-operating-layer')],
            'evidence_coverage'   => ['state' => self::UNKNOWN, 'detail' => __('Measured in Cloud Core, not by this adapter.', 'ai-operating-layer')],
            'trust_coverage'      => ['state' => self::UNKNOWN, 'detail' => __('Measured in Cloud Core, not by this adapter.', 'ai-operating-layer')],
            'commerce_readiness'  => ['state' => self::UNKNOWN, 'detail' => __('Measured in Cloud Core, not by this adapter.', 'ai-operating-layer')],
            'ai_visibility'       => ['state' => self::UNKNOWN, 'detail' => __('Planned for a later phase; not measured today.', 'ai-operating-layer')],
        ];
    }

    private static function roll_up(array $results, array $keys): array
    {
        $states = [];
        foreach ($keys as $k) {
            if (isset($results[$k]['status'])) {
                $states[] = $results[$k]['status'];
            }
        }
        if ($states === []) {
            return ['state' => self::UNKNOWN, 'detail' => ''];
        }
        // Worst wins; UNKNOWN never counted as PASS.
        if (in_array(self::FAIL, $states, true)) {
            $state = self::FAIL;
        } elseif (in_array(self::WARNING, $states, true)) {
            $state = self::WARNING;
        } elseif (in_array(self::UNKNOWN, $states, true)) {
            $state = self::UNKNOWN;
        } else {
            $state = self::PASS;
        }
        $counts = array_count_values($states);
        return [
            'state'  => $state,
            'detail' => sprintf(
                /* translators: 1: pass count, 2: total checks */
                __('%1$d of %2$d checks passing.', 'ai-operating-layer'),
                $counts[self::PASS] ?? 0,
                count($states)
            ),
        ];
    }

    private static function result(string $status, string $label, string $detail): array
    {
        return ['status' => $status, 'label' => $label, 'detail' => $detail];
    }

    public function invalidate(): void
    {
        $this->cache->forget(self::CACHE_KEY);
    }
}
