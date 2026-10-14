<?php
/**
 * Credential storage for the machine identity issued by Cloud Core.
 *
 * SECURITY POSTURE, stated plainly because it matters more than the code:
 * WordPress has no secret store. `wp_options` is the only durable place a
 * plugin can put a credential, and any administrator with database or
 * filesystem access can read it. This plugin therefore does NOT pretend to
 * protect the secret from a compromised WordPress install - that is not
 * achievable. What it does is limit the blast radius:
 *
 *   - autoload=false, so the secret is not loaded into every page request
 *   - never printed, never logged, never returned by any admin screen
 *   - masked everywhere it is displayed (last 4 characters only)
 *   - revocable and rotatable from Core, so a leaked credential is a
 *     recoverable incident rather than a permanent one
 *
 * The real containment is on Core's side: the credential grants four narrow
 * scopes and cannot verify evidence, publish products, or read another
 * tenant.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Credentials
{
    public const OPTION_ENDPOINT = 'aiol_core_endpoint';
    public const OPTION_TOKEN    = 'aiol_core_token';
    public const OPTION_IDENTITY = 'aiol_core_identity';

    public function get_endpoint(): string
    {
        return (string) get_option(self::OPTION_ENDPOINT, '');
    }

    public function get_token(): string
    {
        return (string) get_option(self::OPTION_TOKEN, '');
    }

    public function is_configured(): bool
    {
        return $this->get_endpoint() !== '' && $this->get_token() !== '';
    }

    /**
     * Stores connection settings. The endpoint is validated as an absolute
     * http(s) URL: a relative or javascript: value here would be an SSRF /
     * injection vector, since the plugin will later issue requests to it.
     *
     * @return true|WP_Error
     */
    public function save(string $endpoint, string $token)
    {
        $endpoint = trim($endpoint);
        $token    = trim($token);

        if ($endpoint === '') {
            return new WP_Error('aiol_endpoint_empty', __('Cloud Core URL is required.', 'ai-operating-layer'));
        }
        if (!preg_match('#^https?://#i', $endpoint)) {
            return new WP_Error(
                'aiol_endpoint_scheme',
                __('Cloud Core URL must start with http:// or https://', 'ai-operating-layer')
            );
        }
        // HTTPS POLICY (ADR-045). An installation token is a bearer
        // credential: over plaintext HTTP it is readable by anything on the
        // path, and replayable. Permitting http:// "for convenience" is how
        // a development shortcut reaches production.
        //
        // The ONLY exception is an unambiguously local host, where there is
        // no network to intercept. The check is on the parsed host, not a
        // substring, so `https://evil.com/?x=localhost` and
        // `http://localhost.attacker.com` do not qualify.
        if (stripos($endpoint, 'http://') === 0 && !self::is_local_host($endpoint)) {
            return new WP_Error(
                'aiol_endpoint_insecure',
                __('Cloud Core must be reached over HTTPS. Plain http:// is only allowed for local development (localhost or 127.0.0.1), because the installation token would otherwise be sent in clear text.', 'ai-operating-layer')
            );
        }
        if (!filter_var($endpoint, FILTER_VALIDATE_URL)) {
            return new WP_Error('aiol_endpoint_invalid', __('Cloud Core URL is not a valid URL.', 'ai-operating-layer'));
        }
        if ($token === '') {
            return new WP_Error('aiol_token_empty', __('Installation token is required.', 'ai-operating-layer'));
        }
        if (!self::looks_like_token($token)) {
            return new WP_Error(
                'aiol_token_shape',
                __('That does not look like an installation token. Tokens begin with "aiol_".', 'ai-operating-layer')
            );
        }

        update_option(self::OPTION_ENDPOINT, untrailingslashit($endpoint), false);
        update_option(self::OPTION_TOKEN, $token, false);
        return true;
    }

    /**
     * True only for unambiguously local hosts. Compares the PARSED host
     * exactly - never a substring match, which `localhost.attacker.com`
     * would defeat.
     */
    public static function is_local_host(string $url): bool
    {
        $host = parse_url($url, PHP_URL_HOST);
        if (!is_string($host) || $host === '') {
            return false;
        }
        $host = strtolower($host);
        return in_array($host, ['localhost', '127.0.0.1', '::1', '[::1]'], true);
    }

    /**
     * Shape check only - never a claim of validity. Whether a token actually
     * authenticates is Core's decision, made on the next request. This exists
     * purely to catch an obvious paste error before a round trip.
     */
    public static function looks_like_token(string $token): bool
    {
        return (bool) preg_match('/^aiol_[A-Za-z0-9]+_[A-Za-z0-9_\-]+$/', $token);
    }

    /**
     * What may be shown in the UI. Never the secret.
     */
    public function masked_token(): string
    {
        $token = $this->get_token();
        if ($token === '') {
            return '';
        }
        $parts = explode('_', $token);
        $key_id = $parts[1] ?? '';
        return sprintf('aiol_%s_%s%s', $key_id, str_repeat('•', 8), substr($token, -4));
    }

    public function forget(): void
    {
        delete_option(self::OPTION_TOKEN);
        delete_option(self::OPTION_IDENTITY);
    }

    /** Cached identity echoed by Core; informational only, never authoritative. */
    public function get_identity(): array
    {
        $identity = get_option(self::OPTION_IDENTITY, []);
        return is_array($identity) ? $identity : [];
    }

    public function set_identity(array $identity): void
    {
        update_option(self::OPTION_IDENTITY, $identity, false);
    }
}
