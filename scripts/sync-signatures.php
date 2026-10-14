<?php
/**
 * Regenerates AIOL_Actors::$signatures from the canonical Python list.
 *
 * `cloud-core/app/services/actor_signatures.py` is canonical. Two
 * runtimes classify the same traffic; if their lists drift, the edge
 * blocks one thing while the report shows another and the merchant's
 * access policy silently stops matching.
 *
 * ORDER IS PRESERVED EXACTLY. Matching is first-hit, so
 * `Claude-SearchBot` and `Claude-User` must precede `ClaudeBot` —
 * reordering would classify a customer's live question as a training
 * crawler, which is the single most damaging way this feature can fail.
 *
 * Usage:  php scripts/sync-signatures.php
 */

declare(strict_types=1);

$root = dirname(__DIR__);
$python = file_get_contents($root . '/cloud-core/app/services/actor_signatures.py');
if ($python === false) {
    fwrite(STDERR, "cannot read canonical signature list\n");
    exit(1);
}

preg_match_all(
    '/Signature\("([^"]+)",\s*"([^"]+)",\s*(None|"[^"]*"),\s*ActorType\.(\w+),\s*AccessPurpose\.(\w+)\)/',
    $python,
    $matches,
    PREG_SET_ORDER
);

if ($matches === []) {
    fwrite(STDERR, "parsed zero signatures — the generator itself is broken\n");
    exit(1);
}

$types = [
    'HUMAN' => 'self::HUMAN',
    'SEARCH_CRAWLER' => 'self::SEARCH_CRAWLER',
    'AI_CRAWLER' => 'self::AI_CRAWLER',
    'AI_USER_AGENT' => 'self::AI_USER_AGENT',
    'AGENT_TOOL' => 'self::AGENT_TOOL',
    'UNKNOWN' => 'self::UNKNOWN',
];

$lines = [];
foreach ($matches as [, $needle, $display, $vendor, $type, $purpose]) {
    $label = $vendor === 'None' ? $display : $display . ' (' . trim($vendor, '"') . ')';
    $lines[] = sprintf(
        "        '%s' => [%s, '%s', self::PURPOSE_%s],",
        $needle,
        $types[$type],
        str_replace("'", "\\'", $label),
        $purpose
    );
}

echo count($lines) . " signatures parsed. Paste into class-aiol-actors.php:\n\n";
echo implode("\n", $lines) . "\n";
