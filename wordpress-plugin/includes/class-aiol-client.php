<?php
/**
 * HTTP client for Cloud Core — the ONLY place this plugin talks to Core.
 *
 * Everything about error handling here exists because an adapter that
 * surfaces raw failures is useless to a merchant. `AIOL_Client` maps every
 * outcome onto a small, stable set of categories that the UI can explain in
 * plain language:
 *
 *   not_configured  - no endpoint/token yet
 *   unauthorized    - 401: credential wrong, revoked, rotated or expired
 *   forbidden       - 403: authenticated but lacking the scope
 *   not_found       - 404: object missing, or belongs to another tenant
 *                     (Core deliberately does not distinguish these, to avoid
 *                      leaking the existence of other tenants' objects)
 *   conflict        - 409: would change something already established
 *   rate_limited    - 429
 *   unavailable     - network failure or 5xx
 *   invalid         - 422 validation
 *
 * NOTE on tenancy: this client never sends an organization_id. It cannot -
 * there is no parameter for one. Tenant is derived by Core from the
 * credential (ADR-036). That is not an omission; it is the security
 * property.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Client
{
    private const TIMEOUT = 10;

    private AIOL_Credentials $credentials;
    private AIOL_Logger $logger;

    public function __construct(AIOL_Credentials $credentials, AIOL_Logger $logger)
    {
        $this->credentials = $credentials;
        $this->logger      = $logger;
    }

    public function is_configured(): bool
    {
        return $this->credentials->is_configured();
    }

    /** GET /adapter/identity — the connection test. */
    public function identity()
    {
        return $this->request('GET', '/api/v1/adapter/identity');
    }

    /** POST /adapter/mappings — idempotent upsert. */
    public function upsert_mapping(string $object_type, string $object_id, int $post_id, ?string $post_type, ?string $url)
    {
        return $this->request('POST', '/api/v1/adapter/mappings', [
            'object_type'         => $object_type,
            'object_id'           => $object_id,
            'wordpress_post_id'   => $post_id,
            'wordpress_post_type' => $post_type,
            'wordpress_url'       => $url,
        ]);
    }

    /**
     * GET /adapter/catalog/{id} — the read projection used for JSON-LD.
     * Carries product identity and at most one offer; deliberately carries
     * no evidence or trust data (ADR-042).
     */
    public function catalog_product(string $product_id)
    {
        return $this->request('GET', '/api/v1/adapter/catalog/' . rawurlencode($product_id));
    }

    /** POST /adapter/commerce/mappings/{id}/offer - price/stock only. */
    public function sync_offer(
        string $mapping_id,
        ?float $price,
        ?string $currency,
        string $availability,
        ?int $stock_quantity,
        ?string $idempotency_key = null
    ) {
        return $this->request('POST', '/api/v1/adapter/commerce/mappings/' . rawurlencode($mapping_id) . '/offer', [
            'price'           => $price,
            'currency'        => $currency,
            'availability'    => $availability,
            'stock_quantity'  => $stock_quantity,
            'idempotency_key' => $idempotency_key,
        ]);
    }

    /** POST /adapter/commerce/mappings - idempotent upsert. */
    public function upsert_commerce_mapping(string $product_id, int $woo_product_id, ?int $woo_variation_id, ?string $sku)
    {
        return $this->request('POST', '/api/v1/adapter/commerce/mappings', [
            'product_id'       => $product_id,
            'woo_product_id'   => $woo_product_id,
            'woo_variation_id' => $woo_variation_id,
            'sku'              => $sku,
        ]);
    }

    public function list_mappings(int $limit = 50, int $offset = 0)
    {
        return $this->request('GET', sprintf('/api/v1/adapter/mappings?limit=%d&offset=%d', $limit, $offset));
    }

    // ---------------------------------------------------------------
    // Phase 13 — telemetry, AI access, dashboard reads.
    //
    // Each method is typed and documented, same as every method above.
    // A generic get()/post() was deliberately not added: this client's
    // whole point is that every request this plugin can make is named
    // and reviewable in one file, not assembled ad hoc at call sites.
    // ---------------------------------------------------------------

    /**
     * POST /telemetry/ingest/page-views — the adapter's own observations.
     * Idempotent: every event carries a client-minted event_key, so a
     * redelivered batch is safe to resend.
     *
     * @param array<int,array> $events
     * @return array|WP_Error {accepted,duplicates,rejected,agents_discovered,errors}
     */
    public function ingest_page_views(array $events)
    {
        return $this->request('POST', '/api/v1/telemetry/ingest/page-views', ['events' => $events]);
    }

    /** POST /telemetry/ingest/search — on-site and agent-reported searches. */
    public function ingest_search(array $events)
    {
        return $this->request('POST', '/api/v1/telemetry/ingest/search', ['events' => $events]);
    }

    /**
     * GET /telemetry/access-policies — the merchant's free/paid/forbidden
     * rules. Read here and cached by AIOL_Access_Gate; never fetched on
     * the request path that enforces them.
     */
    public function list_access_policies(int $limit = 200, int $offset = 0)
    {
        return $this->request('GET', sprintf('/api/v1/telemetry/access-policies?limit=%d&offset=%d', $limit, $offset));
    }

    /** GET /telemetry/health — the dashboard's connection strip. */
    public function telemetry_health()
    {
        return $this->request('GET', '/api/v1/telemetry/health');
    }

    /**
     * GET /telemetry/content-stats — content ranked by view count.
     * $sort_by must be one of the server's own allowed fields (fetch them
     * from content_stats_sortable_fields() rather than hard-coding a copy
     * that can drift); an unrecognised value is a 422 from Core, not a
     * silently ignored parameter.
     */
    public function content_stats(string $sort_by = 'total_views', string $sort_dir = 'asc', int $limit = 20, int $offset = 0)
    {
        return $this->request('GET', sprintf(
            '/api/v1/telemetry/content-stats?sort_by=%s&sort_dir=%s&limit=%d&offset=%d',
            rawurlencode($sort_by),
            rawurlencode($sort_dir),
            $limit,
            $offset
        ));
    }

    /** GET /telemetry/agents — every automated client ever seen; no filter hides unrecognised ones. */
    public function list_agents(bool $seen_only = true, int $limit = 50, int $offset = 0)
    {
        return $this->request('GET', sprintf(
            '/api/v1/telemetry/agents?seen_only=%s&limit=%d&offset=%d',
            $seen_only ? 'true' : 'false',
            $limit,
            $offset
        ));
    }

    /** GET /telemetry/search-demand/terms — what was searched for, and how often it found nothing. */
    public function search_demand_terms(int $limit = 10, int $offset = 0)
    {
        return $this->request('GET', sprintf('/api/v1/telemetry/search-demand/terms?limit=%d&offset=%d', $limit, $offset));
    }

    /** GET /telemetry/page-views — the individual observations behind every rollup. */
    public function list_page_views(int $limit = 25, int $offset = 0)
    {
        return $this->request('GET', sprintf('/api/v1/telemetry/page-views?limit=%d&offset=%d', $limit, $offset));
    }

    /**
     * @param array|null $body
     * @return array|WP_Error  Decoded body on success; WP_Error with a stable
     *                         category code on any failure.
     */
    private function request(string $method, string $path, ?array $body = null)
    {
        if (!$this->credentials->is_configured()) {
            return new WP_Error('not_configured', __('The plugin is not connected to Cloud Core yet.', 'ai-operating-layer'));
        }

        $url  = $this->credentials->get_endpoint() . $path;
        $args = [
            'method'  => $method,
            'timeout' => self::TIMEOUT,
            'headers' => [
                'Authorization' => 'Bearer ' . $this->credentials->get_token(),
                'Accept'        => 'application/json',
                'User-Agent'    => 'AI-Operating-Layer-WP/' . AIOL_VERSION,
            ],
        ];
        if ($body !== null) {
            $args['headers']['Content-Type'] = 'application/json';
            $args['body'] = wp_json_encode($body);
        }

        $response = wp_remote_request($url, $args);

        if (is_wp_error($response)) {
            // Note the redaction: $url is safe, but the message may not be.
            $this->logger->error('Cloud Core unreachable', ['path' => $path, 'error' => $response->get_error_message()]);
            return new WP_Error(
                'unavailable',
                __('Could not reach Cloud Core. Check the URL and that the server is running.', 'ai-operating-layer')
            );
        }

        $code    = (int) wp_remote_retrieve_response_code($response);
        $raw     = (string) wp_remote_retrieve_body($response);
        $decoded = json_decode($raw, true);
        $detail  = is_array($decoded) && isset($decoded['detail']) ? (string) $decoded['detail'] : '';

        if ($code >= 200 && $code < 300) {
            return is_array($decoded) ? $decoded : [];
        }

        $category = self::category_for($code);
        $this->logger->error('Cloud Core returned an error', [
            'path'   => $path,
            'status' => (string) $code,
            'detail' => $detail,
        ]);

        return new WP_Error($category, self::message_for($category, $detail), ['status' => $code]);
    }

    public static function category_for(int $code): string
    {
        switch ($code) {
            case 401: return 'unauthorized';
            case 403: return 'forbidden';
            case 404: return 'not_found';
            case 409: return 'conflict';
            case 422: return 'invalid';
            case 429: return 'rate_limited';
            default:  return $code >= 500 ? 'unavailable' : 'error';
        }
    }

    /**
     * Every message answers: what failed, and what do I do about it.
     * "Something went wrong" is explicitly not acceptable here.
     */
    public static function message_for(string $category, string $detail = ''): string
    {
        switch ($category) {
            case 'unauthorized':
                return __('Cloud Core rejected this installation token. It may have been revoked or rotated — issue a new one in Cloud Core and paste it here.', 'ai-operating-layer');
            case 'forbidden':
                return __('This token is valid but lacks the permission for that action. Issue a token with the required scopes in Cloud Core.', 'ai-operating-layer');
            case 'not_found':
                return __('Cloud Core has no such object for this installation. It may have been deleted, or it belongs to a different organization.', 'ai-operating-layer');
            case 'conflict':
                return $detail !== ''
                    ? $detail
                    : __('That change conflicts with something already recorded in Cloud Core. Nothing was changed.', 'ai-operating-layer');
            case 'invalid':
                return $detail !== ''
                    ? $detail
                    : __('Cloud Core rejected the request as invalid. Nothing was changed.', 'ai-operating-layer');
            case 'rate_limited':
                return __('Too many requests to Cloud Core. Wait a minute and try again — nothing was lost.', 'ai-operating-layer');
            case 'unavailable':
                return __('Cloud Core is unreachable or returned a server error. Your data is unchanged; retry is safe.', 'ai-operating-layer');
            case 'not_configured':
                return __('The plugin is not connected to Cloud Core yet.', 'ai-operating-layer');
            default:
                return __('Cloud Core returned an unexpected response. Nothing was changed.', 'ai-operating-layer');
        }
    }

    /** Whether retrying the same operation is safe. Drives the UI's retry affordance. */
    public static function is_retry_safe(string $category): bool
    {
        return in_array($category, ['unavailable', 'rate_limited'], true);
    }
}
