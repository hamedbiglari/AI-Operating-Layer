<?php
/**
 * Copies the canonical design system and icon registry into the plugin.
 *
 * WHY A COPY EXISTS AT ALL
 *
 * A WordPress plugin ships as one directory. It cannot `@import` a file
 * that lives outside its own tree at install time, so the tokens and the
 * icon registry have to be inside `wordpress-plugin/` for the admin
 * screens to render at all.
 *
 * A copy that can drift is how a product ends up with two design systems
 * (UX-08 in the pre-Phase-13 checkpoint is exactly this defect, caught
 * one step earlier). So the copy is GENERATED, never edited, and
 * `tests/test-design-system-parity.php` fails if the plugin's copy is not
 * byte-identical to the canonical file. Drift becomes a red test instead
 * of a slow divergence nobody notices until two screens look different.
 *
 * Usage:  php scripts/sync-design-system.php
 */

declare(strict_types=1);

$root = dirname(__DIR__);

$pairs = [
    '/frontend/design-system/tokens.css'     => '/wordpress-plugin/assets/css/tokens.css',
    '/frontend/design-system/components.css' => '/wordpress-plugin/assets/css/components.css',
    '/frontend/icons/icon-paths.json'        => '/wordpress-plugin/assets/icons/icon-paths.json',
    '/frontend/icons/class-aiol-icon.php'    => '/wordpress-plugin/includes/class-aiol-icon.php',
];

$changed = 0;
foreach ($pairs as $from => $to) {
    $source = $root . $from;
    $target = $root . $to;
    if (!is_file($source)) {
        fwrite(STDERR, "MISSING canonical file: {$from}\n");
        exit(1);
    }
    $bytes = file_get_contents($source);
    if (is_file($target) && file_get_contents($target) === $bytes) {
        continue;
    }
    if (!is_dir(dirname($target))) {
        mkdir(dirname($target), 0755, true);
    }
    file_put_contents($target, $bytes);
    echo "synced {$from}\n";
    $changed++;
}

echo $changed === 0 ? "design system already in sync\n" : "{$changed} file(s) synced\n";
