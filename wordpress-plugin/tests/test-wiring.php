<?php
/**
 * HOOK WIRING INTEGRITY.
 *
 * This file exists because of R1. `aiol_mapping_changed` had a registered
 * listener and no publisher — a dead hook that 110 passing tests did not
 * catch, because every test asserted that a listener *existed*, and none
 * asserted that anything *fired* it.
 *
 * The fix for one dead hook is a one-line `do_action`. The fix for the
 * CLASS of bug is this: scan the whole plugin and require that every custom
 * `aiol_*` hook has both ends. A future dead hook fails here automatically,
 * without anyone remembering to write a test for it.
 *
 * It also checks the inverse — a `do_action` nobody listens to — which is a
 * weaker smell but still worth surfacing: it usually means a feature was
 * half-removed.
 */

declare(strict_types=1);

require_once __DIR__ . '/bootstrap-assert.php';

$plugin_root = dirname(__DIR__);

/** @return string[] every PHP file in the plugin except its tests */
function aiol_source_files(string $root): array
{
    $files = [];
    $rii = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root));
    foreach ($rii as $file) {
        if (!$file->isFile() || $file->getExtension() !== 'php') {
            continue;
        }
        if (strpos($file->getPathname(), DIRECTORY_SEPARATOR . 'tests' . DIRECTORY_SEPARATOR) !== false) {
            continue;
        }
        $files[] = $file->getPathname();
    }
    return $files;
}

/**
 * Strips comments and docblocks using PHP's own tokenizer.
 *
 * This is not decoration. The first version of this file scanned RAW source,
 * and a mutation test — commenting out the `do_action` to recreate R1
 * exactly — still reported 8 passed. A commented-out publisher was counted
 * as a real one, which means the test could not have caught the bug it was
 * written for. Scanning executable code only is what makes the check real.
 */
function aiol_executable_code(string $path): string
{
    $out = '';
    foreach (token_get_all(file_get_contents($path)) as $token) {
        if (is_array($token)) {
            if (in_array($token[0], [T_COMMENT, T_DOC_COMMENT], true)) {
                continue;
            }
            $out .= $token[1];
        } else {
            $out .= $token;
        }
    }
    return $out;
}

$files = aiol_source_files($plugin_root);
T::true(count($files) >= 15, 'wiring scan found the plugin source files');

$source = '';
foreach ($files as $f) {
    $source .= aiol_executable_code($f) . "\n";
}

// Custom hooks only. WordPress/WooCommerce core hooks (save_post,
// woocommerce_update_product, ...) are published by WordPress itself, so
// requiring a do_action for them would be wrong.
preg_match_all("/add_action\(\s*'(aiol_[a-z0-9_]+)'/", $source, $listened);
preg_match_all("/do_action\(\s*'(aiol_[a-z0-9_]+)'/", $source, $published);

$listened_hooks  = array_values(array_unique($listened[1]));
$published_hooks = array_values(array_unique($published[1]));

T::true(count($listened_hooks) > 0, 'the plugin registers at least one custom aiol_ hook listener');

// --- THE R1 CHECK, generalised ------------------------------------------------

foreach ($listened_hooks as $hook) {
    T::true(
        in_array($hook, $published_hooks, true),
        "hook '$hook' is listened for AND fired somewhere (a listener with no publisher is dead code — this is the R1 bug class)"
    );
}

// --- The inverse: a published hook nobody consumes ------------------------------
//
// Not an error on its own — an extension point published for third parties
// is legitimate. But an UNDOCUMENTED one usually means a half-removed
// feature, so it must at least be described in a comment near the
// do_action.

foreach ($published_hooks as $hook) {
    if (in_array($hook, $listened_hooks, true)) {
        continue;
    }
    $raw = '';
    foreach ($files as $f) {
        $raw .= file_get_contents($f) . "\n";
    }
    $documented = (bool) preg_match(
        '/(?:\*|\/\/)[^\n]*' . preg_quote($hook, '/') . '/',
        $raw
    );
    T::true(
        $documented,
        "hook '$hook' is fired with no in-plugin listener, so it must be documented as an intentional extension point"
    );
}

// --- Specific regression: the exact hook that was dead ----------------------------

T::true(in_array('aiol_mapping_changed', $listened_hooks, true), 'R1: aiol_mapping_changed has a listener');
T::true(in_array('aiol_mapping_changed', $published_hooks, true), 'R1: aiol_mapping_changed has a publisher');

// --- Documented extension points must be fired ------------------------------------
//
// `aiol_actor_observed` is advertised in ADR-046 as the seam future phases
// consume. An advertised seam that never fires is a promise the code does
// not keep.

T::true(in_array('aiol_actor_observed', $published_hooks, true),
    'aiol_actor_observed is genuinely fired — ADR-046 advertises it as an extension point');

// --- Every listener callback must exist -------------------------------------------
//
// A second dead-wiring class: `add_action('x', [$this, 'typo'])` registers
// fine and fails silently at runtime. Checks array-callback method names
// against the methods actually declared in the same file.

$missing_callbacks = [];
foreach ($files as $file) {
    $code = aiol_executable_code($file);
    preg_match_all("/add_(?:action|filter)\(\s*'[^']+'\s*,\s*\[\s*\\\$this\s*,\s*'([a-z0-9_]+)'\s*\]/i", $code, $cbs);
    if (!$cbs[1]) {
        continue;
    }
    preg_match_all('/function\s+([a-z0-9_]+)\s*\(/i', $code, $methods);
    foreach (array_unique($cbs[1]) as $cb) {
        if (!in_array($cb, $methods[1], true)) {
            $missing_callbacks[] = basename($file) . '::' . $cb;
        }
    }
}
T::is($missing_callbacks, [], 'every [$this, "method"] hook callback is a method that actually exists');

exit(T::report('wiring'));
