<?php
/**
 * Parity: the PHP signature table must equal the canonical Python list,
 * in the same ORDER.
 *
 * This is the test that turns "two runtimes must agree" from a code
 * review responsibility into a build failure. It lives in its own file so
 * a future refactor of the actor tests cannot quietly delete it along
 * with a rewrite.
 */

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

$canonical_path = dirname(__DIR__, 2) . '/cloud-core/app/services/actor_signatures.py';

if (!is_file($canonical_path)) {
    // Not a pass. The plugin can ship without the Core tree present, but
    // in that checkout this property is UNVERIFIED, and saying so is the
    // point.
    fwrite(STDERR, "SKIP: canonical signature list not present in this checkout - parity UNVERIFIED\n");
    exit(0);
}

$python = (string) file_get_contents($canonical_path);
preg_match_all('/Signature\("([^"]+)"/', $python, $m);
$expected = $m[1];

T::true($expected !== [], 'parsed a non-empty canonical signature list (guards the test itself)');
T::is(AIOL_Actors::signature_keys(), $expected, 'PHP signature table matches the canonical Python list exactly, in order');

// Order, not merely membership. First-hit matching makes this load-bearing.
$keys = AIOL_Actors::signature_keys();
$claude_bot  = array_search('ClaudeBot', $keys, true);
$claude_user = array_search('Claude-User', $keys, true);
T::true(
    $claude_user !== false && $claude_bot !== false && $claude_user < $claude_bot,
    'Claude-User precedes ClaudeBot (otherwise a customer question is classified as a training crawler)'
);

T::is(AIOL_Actors::purpose_for(AIOL_Actors::AI_CRAWLER, 'GPTBot'), AIOL_Actors::PURPOSE_TRAINING, 'GPTBot is training');
T::is(AIOL_Actors::purpose_for(AIOL_Actors::AI_USER_AGENT, 'ChatGPT-User'), AIOL_Actors::PURPOSE_ANSWERING, 'ChatGPT-User is answering');
T::is(AIOL_Actors::purpose_for(AIOL_Actors::UNKNOWN, null), AIOL_Actors::PURPOSE_UNKNOWN, 'an unrecognised client declares no purpose');

exit(T::report('signature parity'));
