<?php
/**
 * Access gate precedence — the pure evaluation, no WordPress, no I/O.
 *
 * This is the PHP half of a rule implemented twice (the other half is
 * `access_policy_service.evaluate()` in Core). The duplication is
 * deliberate and explained in class-aiol-access-gate.php; these tests
 * assert the half that runs at the edge, and the Python suite asserts the
 * authoritative half, against the same cases in the same order.
 */

declare(strict_types=1);

require __DIR__ . '/bootstrap.php';

$actor = static fn(string $type, string $label = '') => [
    'type' => $type, 'label' => $label, 'confidence' => AIOL_Actors::DETECTED,
];

$rule = static fn(array $over = []) => array_merge([
    'id' => 'rule-1', 'agent_signature' => null, 'actor_type' => null,
    'purpose' => null, 'tier' => AIOL_Access_Gate::FREE, 'reason' => null, 'terms_url' => null,
], $over);

// --- no rules -------------------------------------------------------------
$r = AIOL_Access_Gate::evaluate($actor(AIOL_Actors::AI_CRAWLER, 'GPTBot (OpenAI)'), []);
T::is($r['decision'], 'not_configured', 'no rule => not_configured, NOT allowed (nobody decided)');
T::is($r['tier'], AIOL_Access_Gate::UNSET, 'no rule => unset tier');

// --- actor-type rule ------------------------------------------------------
$r = AIOL_Access_Gate::evaluate(
    $actor(AIOL_Actors::AI_CRAWLER, 'GPTBot (OpenAI)'),
    [$rule(['actor_type' => AIOL_Actors::AI_CRAWLER, 'tier' => AIOL_Access_Gate::FORBIDDEN])]
);
T::is($r['decision'], 'blocked', 'an actor-type rule blocks every AI crawler');

// --- purpose separates training from answering ----------------------------
$policies = [
    $rule(['id' => 'train', 'actor_type' => AIOL_Actors::AI_CRAWLER,
           'purpose' => AIOL_Actors::PURPOSE_TRAINING, 'tier' => AIOL_Access_Gate::FORBIDDEN]),
    $rule(['id' => 'answer', 'actor_type' => AIOL_Actors::AI_USER_AGENT,
           'purpose' => AIOL_Actors::PURPOSE_ANSWERING, 'tier' => AIOL_Access_Gate::FREE]),
];
T::is(
    AIOL_Access_Gate::evaluate($actor(AIOL_Actors::AI_CRAWLER, 'GPTBot (OpenAI)'), $policies)['decision'],
    'blocked',
    'no to training'
);
T::is(
    AIOL_Access_Gate::evaluate($actor(AIOL_Actors::AI_USER_AGENT, 'ChatGPT-User (OpenAI)'), $policies)['decision'],
    'allowed',
    'yes to answering a live customer question'
);

// --- specific beats general, even when general is stricter ----------------
$policies = [
    $rule(['id' => 'specific', 'agent_signature' => 'GPTBot', 'tier' => AIOL_Access_Gate::FREE]),
    $rule(['id' => 'general', 'actor_type' => AIOL_Actors::AI_CRAWLER, 'tier' => AIOL_Access_Gate::FORBIDDEN]),
];
$r = AIOL_Access_Gate::evaluate($actor(AIOL_Actors::AI_CRAWLER, 'GPTBot (OpenAI)'), $policies);
T::is($r['decision'], 'allowed', 'most-specific-first, NOT strictest-wins');
T::is($r['policy_id'], 'specific', 'and it reports which rule decided');

// "strictest wins" would make "block all AI crawlers EXCEPT this one"
// impossible to express, which is a policy merchants actually want.

// --- paid -----------------------------------------------------------------
$r = AIOL_Access_Gate::evaluate(
    $actor(AIOL_Actors::AI_CRAWLER, 'CCBot (Common Crawl)'),
    [$rule(['actor_type' => AIOL_Actors::AI_CRAWLER, 'tier' => AIOL_Access_Gate::PAID,
            'terms_url' => 'https://merchant.example/ai-terms'])]
);
T::is($r['decision'], 'payment_required', 'paid => 402 semantics');
T::is($r['terms_url'], 'https://merchant.example/ai-terms', 'and carries the terms link');

// --- unset behaves exactly like no rule -----------------------------------
T::is(
    AIOL_Access_Gate::evaluate(
        $actor(AIOL_Actors::AI_CRAWLER, 'GPTBot (OpenAI)'),
        [$rule(['actor_type' => AIOL_Actors::AI_CRAWLER, 'tier' => AIOL_Access_Gate::UNSET])]
    )['decision'],
    'not_configured',
    '"I made a row but have not chosen" must not read as "I allowed it"'
);

// --- direct signature lookup survives a merchant rename --------------------
// Regression: evaluate() used to derive the signature ONLY from
// actor['label'] via a reverse lookup against the canonical table. The
// dashboard reads Core's AiAgent records, whose display_name a merchant
// can rename - after a rename, label-based lookup silently returns null
// and every agent-level policy row for that agent stops matching, with
// no error anywhere. The fix: evaluate() now accepts a direct
// 'signature' key and uses it without going through label at all. This
// is the exact call shape AIOL_Admin::render_dashboard() uses.
$renamed_agent = [
    'type'      => AIOL_Actors::AI_CRAWLER,
    'signature' => 'GPTBot', // Core's canonical key, known directly - no label involved
];
$r = AIOL_Access_Gate::evaluate(
    $renamed_agent,
    [$rule(['agent_signature' => 'GPTBot', 'tier' => AIOL_Access_Gate::FORBIDDEN])]
);
T::is(
    $r['decision'],
    'blocked',
    'a direct signature match still works after a merchant renames the agent (label is never consulted)'
);

// The edge path (enforce(), given only a raw User-Agent) has no
// pre-known signature and MUST still fall back to the label lookup -
// this is the only path that ever produces a 'label'-only actor array.
$edge_actor = ['type' => AIOL_Actors::AI_CRAWLER, 'label' => 'GPTBot (OpenAI)'];
$r = AIOL_Access_Gate::evaluate(
    $edge_actor,
    [$rule(['agent_signature' => 'GPTBot', 'tier' => AIOL_Access_Gate::FORBIDDEN])]
);
T::is(
    $r['decision'],
    'blocked',
    'the edge path (label only, no pre-known signature) still resolves via signature_for_label()'
);

exit(T::report('access gate'));
