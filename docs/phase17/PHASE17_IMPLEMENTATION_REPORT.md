# Phase 17 — Implementation Report

Implements the Phase 16 LOCKED architecture (C — hybrid canonical AI
execution). No architectural divergence. Three bounded, documented
deviations are listed at the end.

## Decision → implementation map

| Phase 16 decision | File(s) | DB | Test(s) |
|---|---|---|---|
| One row per real model invocation | `app/models/ai_execution.py` | `ai_executions` (0017) | success/failure/retry tests |
| Tenant scope, composite FKs (ADR-037) | model DDL + `0017` | `(x_id, organization_id)` FKs to visibility_runs, knowledge_objects, users, installations, self | cross-tenant parent / KO / user / previous tests |
| Exclusive arc + stored discriminator | model CHECKs + insert trigger | `ck_ai_executions_parent_type_known`, `_arc_cardinality`, `_parent_type_matches`, `trg_ai_executions_require_parent` | no-parent, unknown type, cardinality tests |
| Parent deletion keeps accounting fact | column-list `ON DELETE SET NULL (col)` | PG15+ | `test_parent_deletion_preserves_execution` |
| Immutability of terminal rows | service guard + `trg_ai_executions_immutable_terminal` | trigger | app + DB immutability test |
| Shared invocation wrapper, row before call | `app/ai/invocation.py`, `app/services/ai_execution_service.py` | — | "created before call" test (row observed RUNNING inside the provider handler) |
| No bypass | `app/integrations/llm/base.py::require_invocation_permit` | — | adapter-permit test + static scan test |
| Provider isolation | `app/integrations/llm/anthropic.py` only | — | static scan |
| Retry / provider fallback / model fallback / manual retry = new row | `invoke_with_policy` | `previous_execution_id` + `attempt_reason` (CHECK: both or neither) | chain F→F→S, provider fallback, model fallback, manual retry |
| Usage NULL unless reported; UNKNOWN ≠ 0; estimate ≠ actual | `app/ai/pricing.py`, `_finalize` | `ck_ai_executions_cost_currency` | usage-absent, unknown-price, cost tests |
| No raw prompt/response on execution | model (no columns); `input_hash` only | — | leak test (row_to_json) |
| Visibility: VisibilityTest → terminal execution | `app/integrations/visibility/llm.py`, `visibility_run_service.py` | `visibility_tests.ai_execution_id` composite FK | linkage, retry-linkage, no-credential, wrong-platform tests |
| Budget gate before spend | `InvocationContext.budget_cleared`; set only after `reserve_budget` | — | budget-gate test; settlement tests |
| Stale RUNNING recovery | `reclaim_stale_executions`, task `ai_executions.reclaim_stale` | partial index `ix_ai_executions_running_started` | stale test |
| Read-only API | `app/api/v1/ai_executions.py` | — | isolation / 405 / 401 tests |
| Log separation | no audit writes from the wrapper | — | audit-count test |

## Files

New: `app/models/ai_execution.py`, `migrations/versions/0017_phase17_ai_execution.py`,
`app/services/ai_execution_service.py`, `app/ai/{__init__,invocation,pricing}.py`,
`app/integrations/llm/{__init__,base,anthropic}.py`, `app/integrations/visibility/llm.py`,
`app/schemas/ai_execution.py`, `app/api/v1/ai_executions.py`,
`tests/test_phase17_ai_execution.py`, `cloud-core/.env.example`.

Modified (additive): `app/models/enums.py` (4 enums), `app/core/config.py`
(provider settings; key is `SecretStr`), `app/models/{user,knowledge_object,visibility_project}.py`
(UNIQUE (id, organization_id) composite-FK targets), `app/models/visibility.py`
(`ai_execution_id`), `app/models/__init__.py`, `app/integrations/visibility/base.py`
(`ProbeResult.ai_execution_id`, `budget_settlement`), `app/integrations/visibility/fixture.py`
(registers the model-backed provider), `app/services/visibility_run_service.py`
(wrapper path + settlement), `app/schemas/common.py` (sortable fields),
`app/api/v1/router.py`, `app/workers/tasks.py`.

## Deviations (bounded, documented — not redesign)

1. **`ABANDONED` status added.** Phase 16 listed running/succeeded/failed/timeout/
   rate_limited/cancelled. A row whose worker died has an *unknown* outcome;
   marking it FAILED would assert a fact nobody knows. Terminal, cost NULL.
2. **Arc has one column (`visibility_run_id`).** Only Visibility invokes a model.
   The "two parents" case is structurally unrepresentable until a second
   domain is added; the cardinality CHECK is written over the arc so it
   applies automatically.
3. **Model-backed Visibility serves `platform=OTHER` only.** The
   `visibility_platform` enum has no Claude value; observing Claude must not be
   recorded as ChatGPT/Gemini. Any other platform → UNAVAILABLE, no call.
   Adding an explicit platform value is a follow-up (native-enum migration).

## Defect found and fixed during runtime verification

Live run (real uvicorn + Celery, priced, no credential): the probe correctly made
no call and wrote no execution, **but the budget was charged the full
reservation (0.0040)** because settlement fell back to the estimate when the
provider reported no actual cost. Fixed with `ProbeResult.budget_settlement`:
0.0 when nothing was invoked; the chain's summed estimated cost when every
execution's cost is known; otherwise the full reservation (never under-counts).
Re-verified live: spend 0.0000. Two regression tests added.
