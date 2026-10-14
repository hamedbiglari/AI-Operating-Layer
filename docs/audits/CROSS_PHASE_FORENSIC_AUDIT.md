# Cross-phase forensic audit — Phases 0–12

Adversarial audit of the whole system, not a per-phase re-check. Every
finding below was produced by executing code against the repository.

## Inventory

| Item | Count |
|---|---|
| API routes | 178 |
| Models | 42 |
| Services | 39 |
| Migrations | 15 |
| Test modules | 60 |
| Composite tenant FKs | 27 |

## DEFECT FOUND AND FIXED

### D1 — `ingest_document_job` defined twice in one module — **P1**

`app/workers/tasks.py` contained **two** definitions of
`ingest_document_job`, both decorated `@celery_app.task(name="documents.ingest")`.

Why this matters more than it looks: Python keeps the second definition,
and Celery binds the task name to whichever registered last. The first
definition was therefore **dead code that read as live** — a maintainer
editing it would have changed nothing, and the worker would have kept
executing the other one. Nothing in 759 passing tests could see this,
because both bodies delegated to the same service and behaved identically.

**Cause:** introduced by my own ADR-073 consolidation. I appended the new
thin wrapper, and the regex that removed the old one did not match.

**Fix:** removed the first (overridden) definition. Behaviour is unchanged
by construction — it was never executing.

**Regression:** `test_no_function_is_defined_twice_in_the_same_module`,
plus a Celery-task-name uniqueness check, both mutation-verified.

## Findings assessed and closed

| ID | Area | Result |
|---|---|---|
| F1 | Tenant columns | **CLEAN** — every model carries `organization_id` except `organizations`, which IS the tenant |
| F2 | DB-level tenant enforcement | **CLEAN** — 27 composite FKs |
| F3 | Status-collapse antipatterns | **CLEAN** — the 4 candidate sites are counters (`dict.get(k, 0) + 1`), not measurements |
| F4 | Cross-tenant attack | **CLEAN** — 55 parameterised GET routes probed with another tenant's real IDs; **0 leaks** |
| F5 | Duplicate responsibility | **1 defect (D1)**; the other ~85 name collisions are the normal route→service delegation pattern |
| F6 | Query normalization | **CLEAN** — `normalize_query` exists once; Phase 6 remains canonical and search intelligence reuses it |
| F7 | Dead enums / orphan models / unregistered routers | **CLEAN** |

## A false positive worth recording

The Celery-uniqueness test initially reported `documents.ingest` as
duplicated. It was not: two regexes in my own test matched the same
multiline decorator and double-counted it. Fixed to a single pattern, then
mutation-verified against a genuinely duplicated name.

**In an audit a false positive is as damaging as a false negative** — it
spends attention on a non-problem and erodes trust in the remaining
findings.

## New permanent invariants

`tests/test_forensic_integrity.py` — 13 cross-phase structural tests that
no per-phase suite owned:

- no function or class redefined within one module
- every Celery task name registered exactly once
- exactly one query-normalization implementation
- every tenant-scoped model carries `organization_id`
- no declared-but-unused enum, no orphan model module, no unregistered router
- fixture and live observations remain distinguishable (`is_fixture`)
- search and AI observations remain structurally distinct
- no global AI score anywhere (ADR-047 / 059 / 064 still hold)
- click and purchase remain unrepresentable (ADR-062)
- visibility events carry no causal field

## Verification

```
python -m pytest -q   ->  772 passed, 0 failed  (290.67s)
migration cycle       ->  base -> head -> base -> head, fresh DB, 15 migrations
cross-tenant probe    ->  55 routes, 0 leaks (authentication asserted first)
```

The tenant probe's first version returned 0 leaks while unauthenticated —
it proved nothing. It now asserts it is authenticated and that the victim
tenant's resources exist before concluding anything.

## Unchanged environment blockers

Live AI platform execution · live Search Console / SERP execution ·
WordPress runtime · WooCommerce runtime · browser / RTL visual.

No blocker was cleared, and none was converted to a pass.
