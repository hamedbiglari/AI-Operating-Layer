<?php
/**
 * Parity: the plugin's copy of the design system must be byte-identical
 * to the canonical files under frontend/.
 *
 * UX-08 in the pre-Phase-13 checkpoint recorded the plugin maintaining
 * its own `--aiol-*` token block alongside the canonical tokens.css - two
 * design systems in one product, which is how a plugin and a web app
 * start looking like different software. Phase 13 closes it with a
 * generated copy plus this test, so it cannot silently reopen.
 */

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

$root = dirname(__DIR__, 2);

$pairs = [
    '/frontend/design-system/tokens.css'     => '/wordpress-plugin/assets/css/tokens.css',
    '/frontend/design-system/components.css' => '/wordpress-plugin/assets/css/components.css',
    '/frontend/icons/icon-paths.json'        => '/wordpress-plugin/assets/icons/icon-paths.json',
    '/frontend/icons/class-aiol-icon.php'    => '/wordpress-plugin/includes/class-aiol-icon.php',
];

foreach ($pairs as $canonical => $copy) {
    if (!is_file($root . $canonical)) {
        fwrite(STDERR, "SKIP: canonical file absent in this checkout ({$canonical}) - parity UNVERIFIED\n");
        exit(0);
    }
    T::true(is_file($root . $copy), "plugin copy exists: {$copy}");
    T::is(
        md5_file($root . $copy),
        md5_file($root . $canonical),
        "plugin copy is byte-identical to canonical: {$canonical} (never edit the copy; run php scripts/sync-design-system.php)"
    );
}

exit(T::report('design system parity'));
