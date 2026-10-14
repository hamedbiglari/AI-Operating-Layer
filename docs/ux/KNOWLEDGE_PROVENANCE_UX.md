# Knowledge & Provenance UX

Status: **UX contract.** This is the product's central promise; treat
deviations here as defects rather than polish.

## 1. Both directions are mandatory

```
Knowledge → Claim → Evidence → Document → Source      (why do you say that?)
Source → Claim → Knowledge                            (what did this change?)
```

Every important knowledge statement has a reachable path to an original
source. Every source has a reachable list of what it contributed. Neither
direction is optional and neither is a hidden "advanced" view.

The data supports both today: `evidence.source_id` is not nullable,
`evidence.document_id` and `evidence.document_chunk_id` pin the location, and
`claim_evidence` carries the relation. What is missing is the read surface —
there is no `/documents/{id}/provenance` or `/sources/{id}/knowledge`
endpoint (UX-007).

## 2. Status words are the domain's

The UI renders these literally and never maps them onto good/bad or yes/no:

- Claim: `draft`, `pending_review`, `approved`, `rejected`, `disputed`, `deprecated`
- Claim aggregate strength: `unverified`, `insufficient`, `weak`, `moderate`, `strong`, `conflicting`
- Evidence: `draft`, `pending_review`, `verified`, `rejected`
- Evidence relation to a claim: `supports`, `contradicts`, `mixed`, `neutral`
- Evidence directness: `direct`, `indirect`
- Source access: `unknown`, `accessible`, `paywalled`, `restricted`, `unavailable`

`unverified` is the honest steady state of a claim nothing has been linked
to. It is styled as neutral, never as a warning, and never as a failure.

## 3. Unknown is not negative

This rule is enforced structurally in the backend in three places
(recommendation signals, agent responses, visibility observations) and the
interface must not undo it. A product with no evidence is unevaluated, not
bad. A signal that was not checked has said nothing.

Five outcomes stay separate wherever any of them can occur:

```
Not found      we looked, and found nothing
Not accessible we found it and could not read it
Not tested     no one has run the test
Insufficient   there is some, and it is not enough
Unknown        we have not looked
```

## 4. Conflicts are shown, never averaged

When supporting and contradicting verified evidence exist for one claim, the
claim reads `conflicting` and the interface says so at every place the claim
appears — including inside a Knowledge Object's prose, not only on a conflict
screen. Counts of supporting and contradicting sources are given separately.
There is no blended number.

## 5. No invented scores

No "trust score", no "evidence score", no "confidence: 87". Trust is answered
by enumerating verified trust records, each with its claim, its evidence and
its verification date — which is what the backend does, deliberately, instead
of storing a number that could drift from the evidence beneath it.

Where a numeric field genuinely exists and is defined —
`document_tables.extraction_confidence`, `Recommendation.final_score` — it is
shown with its definition and its scope, never promoted into a headline
figure.

## 6. Two-layer verification must be visible

A product-evidence link or a trust record counts as verified only when it
*and* its underlying Evidence row are both verified. Revoking the underlying
Evidence immediately stops it counting. The UI must therefore never cache a
"verified" badge computed at write time, and must show what was revoked when
a count drops.

## 7. Scientific and health content

Traditional use, mechanistic, in-vitro, animal, human and clinical evidence
are separate lines that never substitute for one another. Evidence about a
compound is not evidence about the plant, and the interface must not let
styling imply otherwise. `directness: indirect` is displayed, always, next to
any claim that rests on it.

## 8. Knowledge freshness

Four different facts, four different labels:

```
Knowledge updated   the curated knowledge changed
Content updated     the rendered text changed
Research pending    a task is queued
Review pending      a person owes a decision
```

A date is never touched to make content look fresh.

## 9. Living knowledge and diffs

When new evidence changes a claim, the change is offered for review rather
than applied silently: what changed, what it was, what it is now, and which
new source caused it. Approve, reject, or leave pending are all terminal
states the user can choose, and "leave pending" must not block publication of
the rest.
