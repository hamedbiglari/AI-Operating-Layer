<?php
/**
 * Request geography — pass-through only (ADR-079).
 *
 * THE ONE RULE
 *
 * This class NEVER derives a location. It reads headers that an upstream
 * CDN has already resolved, and if none are present it says so. There is
 * no bundled IP-geolocation database, no lookup call and no heuristic
 * from TLD, language or timezone.
 *
 * That is why `geo_method` is a required field rather than an optional
 * one: a country column with no provenance is indistinguishable from a
 * guess, and a guessed country in an analytics report is worse than an
 * empty one because it cannot be corrected by anyone who spots it.
 *
 * Supported edge headers are limited to the ones a CDN sets itself.
 * A header a *client* can set is not evidence of anything: a crawler
 * that wants to look Iranian can send `CF-IPCountry: IR`, so these are
 * trusted only to the extent the merchant's own edge is trusted, and the
 * report labels the value `Edge header` rather than `Verified`.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Geo
{
    /** Header => field. Order matters: first hit wins. */
    private const COUNTRY_HEADERS = [
        'HTTP_CF_IPCOUNTRY',          // Cloudflare
        'HTTP_CLOUDFRONT_VIEWER_COUNTRY', // AWS CloudFront
        'HTTP_X_VERCEL_IP_COUNTRY',
        'HTTP_X_GEO_COUNTRY',         // generic reverse proxy
    ];

    private const CITY_HEADERS = [
        'HTTP_CF_IPCITY',
        'HTTP_CLOUDFRONT_VIEWER_CITY',
        'HTTP_X_VERCEL_IP_CITY',
        'HTTP_X_GEO_CITY',
    ];

    private const REGION_HEADERS = [
        'HTTP_CLOUDFRONT_VIEWER_COUNTRY_REGION_NAME',
        'HTTP_X_VERCEL_IP_COUNTRY_REGION',
        'HTTP_X_GEO_REGION',
    ];

    /**
     * @return array{ip_address?:string,geo_method:string,geo_country?:string,geo_region?:string,geo_city?:string,geo_timezone?:string}
     */
    public static function for_request(): array
    {
        $out = ['geo_method' => 'none'];

        $ip = self::client_ip();
        if ($ip !== null) {
            $out['ip_address'] = $ip;
        }

        $country = self::first_header(self::COUNTRY_HEADERS);
        if ($country === null || strlen($country) !== 2) {
            // No country means NO geo fields at all. A city without a
            // country is not half an answer, it is an unusable one.
            return $out;
        }

        $out['geo_method']  = 'edge_header';
        $out['geo_country'] = strtoupper($country);

        $city = self::first_header(self::CITY_HEADERS);
        if ($city !== null) {
            $out['geo_city'] = mb_substr($city, 0, 120);
        }
        $region = self::first_header(self::REGION_HEADERS);
        if ($region !== null) {
            $out['geo_region'] = mb_substr($region, 0, 80);
        }

        return $out;
    }

    /**
     * The client address.
     *
     * REMOTE_ADDR only, unless the site has explicitly declared a trusted
     * proxy. `X-Forwarded-For` is client-controllable when nothing
     * strips it, so reading it by default would let any visitor write
     * whatever address they liked into the merchant's analytics — and,
     * worse, into a record the merchant may later rely on.
     */
    public static function client_ip(): ?string
    {
        $settings = get_option('aiol_settings', []);
        $trust_proxy = is_array($settings) && !empty($settings['trust_proxy_headers']);

        if ($trust_proxy && !empty($_SERVER['HTTP_X_FORWARDED_FOR'])) {
            $forwarded = (string) wp_unslash($_SERVER['HTTP_X_FORWARDED_FOR']);
            $first = trim(explode(',', $forwarded)[0]);
            if (filter_var($first, FILTER_VALIDATE_IP)) {
                return $first;
            }
        }

        $remote = isset($_SERVER['REMOTE_ADDR']) ? (string) wp_unslash($_SERVER['REMOTE_ADDR']) : '';
        return filter_var($remote, FILTER_VALIDATE_IP) ? $remote : null;
    }

    private static function first_header(array $keys): ?string
    {
        foreach ($keys as $key) {
            if (!empty($_SERVER[$key])) {
                $value = sanitize_text_field(wp_unslash((string) $_SERVER[$key]));
                // Cloudflare sends XX for "unknown" and T1 for Tor.
                if ($value !== '' && $value !== 'XX' && $value !== 'T1') {
                    return $value;
                }
            }
        }
        return null;
    }
}
