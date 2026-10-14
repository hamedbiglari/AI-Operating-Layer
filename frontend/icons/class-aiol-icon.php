<?php
/**
 * AI Operating Layer — canonical icon renderer for the WordPress adapter.
 *
 * This deliberately READS `icon-paths.json`, the same file the Web App
 * imports. It does not keep its own copy of the paths. That is what makes
 * "one icon system across both clients" (checkpoint §54, §56) a structural
 * fact rather than a promise: the plugin cannot drift from the Web App
 * without someone editing the shared registry, and the Web App's own
 * renderer throws on a name the registry does not contain.
 *
 * REPLACES the ad-hoc `aiol_icon()` function currently defined inside
 * `admin/view-settings.php`, which holds four hand-written paths in a global
 * function declared in a view file.
 *
 * Accessibility contract is identical to icon.js: decorative by default,
 * role="img" + <title> when a label is given, and an icon-only control
 * cannot be constructed without one.
 *
 * @package ai-operating-layer
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

final class AIOL_Icon
{
    private const REGISTRY_RELATIVE = 'assets/icons/icon-paths.json';

    /** @var array<string,mixed>|null */
    private static ?array $registry = null;

    /** @return array<string,mixed> */
    private static function registry(): array
    {
        if (self::$registry !== null) {
            return self::$registry;
        }
        $path = AIOL_PLUGIN_DIR . self::REGISTRY_RELATIVE;
        $raw  = is_readable($path) ? file_get_contents($path) : '';
        $data = $raw !== '' ? json_decode($raw, true) : null;

        // An unreadable registry is a build error, not a runtime fallback.
        // Returning an empty set makes `render()` emit nothing and log,
        // rather than silently substituting a different glyph.
        self::$registry = is_array($data) ? $data : ['geometry' => [], 'icons' => []];
        return self::$registry;
    }

    /**
     * @param string               $name  key from icon-paths.json
     * @param array<string,string> $args  label, size, class
     */
    public static function render(string $name, array $args = []): string
    {
        $reg  = self::registry();
        $defs = isset($reg['icons']) && is_array($reg['icons']) ? $reg['icons'] : [];

        if (!isset($defs[$name])) {
            if (defined('WP_DEBUG') && WP_DEBUG) {
                // phpcs:ignore WordPress.PHP.DevelopmentFunctions.error_log_error_log
                error_log(sprintf('AIOL_Icon: unknown icon "%s"', $name));
            }
            return '';
        }

        $def  = $defs[$name];
        $geo  = isset($reg['geometry']) && is_array($reg['geometry']) ? $reg['geometry'] : [];
        $size = $args['size'] ?? 'var(--icon-size, 16px)';

        $classes = ['icon'];
        if (!empty($def['mirror'])) {
            $classes[] = 'icon--mirror';
        }
        if (!empty($args['class'])) {
            $classes[] = $args['class'];
        }

        $label = isset($args['label']) && $args['label'] !== '' ? (string) $args['label'] : null;
        $a11y  = $label !== null
            ? sprintf('role="img" aria-label="%s"', esc_attr($label))
            : 'aria-hidden="true" focusable="false"';

        $extra = isset($def['extra']) ? str_replace("'", '"', (string) $def['extra']) : '';

        return sprintf(
            '<svg class="%s" %s viewBox="%s" width="%s" height="%s" fill="none" '
            . 'stroke="currentColor" stroke-width="var(--icon-stroke, %s)" '
            . 'stroke-linecap="round" stroke-linejoin="round">%s<path d="%s"/>%s</svg>',
            esc_attr(implode(' ', $classes)),
            $a11y, // built from escaped parts above
            esc_attr((string) ($geo['viewBox'] ?? '0 0 24 24')),
            esc_attr((string) $size),
            esc_attr((string) $size),
            esc_attr((string) ($geo['strokeWidth'] ?? '1.75')),
            $label !== null ? '<title>' . esc_html($label) . '</title>' : '',
            esc_attr((string) $def['d']),
            $extra // static markup from the versioned registry, not user input
        );
    }

    /**
     * Icon-only control. Cannot be built without an accessible name.
     */
    public static function button(string $name, string $label, array $attrs = []): string
    {
        if ($label === '') {
            if (defined('WP_DEBUG') && WP_DEBUG) {
                // phpcs:ignore WordPress.PHP.DevelopmentFunctions.error_log_error_log
                error_log(sprintf('AIOL_Icon::button("%s") called without a label', $name));
            }
            return '';
        }
        $pairs = '';
        foreach ($attrs as $k => $v) {
            $pairs .= sprintf(' %s="%s"', esc_attr((string) $k), esc_attr((string) $v));
        }
        return sprintf(
            '<button type="button" class="icon-button" aria-label="%1$s" title="%1$s"%2$s>%3$s</button>',
            esc_attr($label),
            $pairs,
            self::render($name)
        );
    }

    /**
     * Domain value -> icon name. Keys are literal cloud-core enum values.
     * An unrecognised value resolves to `status-unknown`, never to a
     * cheerful default — see checkpoint §69.
     */
    public static function for_sync_status(string $status): string
    {
        $map = [
            'pending' => 'status-queued',
            'synced'  => 'status-completed',
            'stale'   => 'status-warning',
            'failed'  => 'status-failed',
        ];
        return $map[$status] ?? 'status-unknown';
    }
}
