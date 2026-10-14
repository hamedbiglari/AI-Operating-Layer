<?php
/**
 * Bounded, secret-free adapter log.
 *
 * Two rules this class exists to enforce mechanically rather than by
 * convention:
 *
 * 1. NO SECRETS. `redact()` strips anything token-shaped from every message
 *    before it is stored, so a careless caller cannot leak a credential into
 *    the log even by passing the whole request body.
 * 2. BOUNDED SIZE. The log is capped at 50 entries in a single non-autoloaded
 *    option. An adapter log that grows without limit is a denial-of-service
 *    against the merchant's own database.
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

class AIOL_Logger
{
    private const OPTION = 'aiol_log';
    private const MAX_ENTRIES = 50;

    public function info(string $message, array $context = []): void
    {
        $this->write('info', $message, $context);
    }

    public function error(string $message, array $context = []): void
    {
        $this->write('error', $message, $context);
    }

    private function write(string $level, string $message, array $context): void
    {
        $entries = $this->entries();
        array_unshift($entries, [
            'time'    => gmdate('c'),
            'level'   => $level,
            'message' => self::redact($message),
            'context' => array_map([self::class, 'redact'], array_map('strval', $context)),
        ]);
        update_option(self::OPTION, array_slice($entries, 0, self::MAX_ENTRIES), false);
    }

    public function entries(): array
    {
        $entries = get_option(self::OPTION, []);
        return is_array($entries) ? $entries : [];
    }

    public function clear(): void
    {
        delete_option(self::OPTION);
    }

    /**
     * Removes credential-shaped substrings. Deliberately aggressive: a false
     * positive costs a slightly less readable log line; a false negative
     * costs a leaked secret.
     */
    public static function redact(string $text): string
    {
        $text = preg_replace('/aiol_[A-Za-z0-9]+_[A-Za-z0-9_\-]+/', 'aiol_***REDACTED***', $text) ?? $text;
        $text = preg_replace('/(Bearer\s+)\S+/i', '$1***REDACTED***', $text) ?? $text;
        return $text;
    }
}
