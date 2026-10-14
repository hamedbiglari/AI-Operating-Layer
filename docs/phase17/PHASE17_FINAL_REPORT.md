# Phase 17 — Final Report (closure)

**Verdict: BLOCKED** — live-provider verification is blocked by an external credential
dependency. The Phase 17 implementation is structurally verified to the extent possible
without that credential; this is not an architecture failure.

- REAL PROVIDER STATUS: BLOCKED_EXTERNAL_DEPENDENCY (`ANTHROPIC_API_KEY`, plus `AI_MODEL_PRICING_JSON` for known cost)
- AIEXECUTION STATUS: IMPLEMENTED

## Closure remediation (defects found and fixed in this pass)
1. DB immutability loopholes in 0017's trigger: terminal rows deletable; parent/actor/attribution columns re-pointable or nullable while the target existed; creation facts mutable while RUNNING. Fixed by 0018.
2. Finalization race: a stale in-memory object could be finalized over a row the reclaimer had terminalized. Fixed with a row lock and a wrapper that keeps the recorded verdict and never reports the late provider output as success.
3. Provider cost exposed to every tenant role (API and via `VisibilityTest.estimated_cost`). Now OWNER/ADMIN only, single source of truth on AIExecution.
4. No operational surface. Added the live AI Executions dashboard screen (+ explicit CORS).
5. Stale cleanup unschedulable in deployment: compose had no worker/beat and a wrong build context. Fixed; beat verified live.
6. Default list order not index-served (15 ms at 20k rows). Index added: 3 ms.
7. Mutation testing found an untested path (malformed pricing -> zero). Test added.
8. Documentation error in the first Phase 17 package ("no beat schedule exists") corrected.

## Test accounting
Baseline before Phase 17: 827. Added by Phase 17: 118. Removed/renamed: 0. Total: 945.
Full suite at 941 tests (4 chunks, fresh alembic DB `aiol_p17final`): 935 passed, 6 failed, 0 skipped.
The 4 tests added afterwards (malformed pricing) pass; Phase 17 file alone: 118 passed.
Final: 945 tests, 939 passed, 6 failed, 0 skipped, 0 environment failures.
The 6 failures are pre-existing Phase 13 defects (identical on the pre-Phase-17 tree).

Details: CLOSURE_MATRIX, FINAL_GAP_MATRIX, RUNTIME_EVIDENCE, SECURITY_EVIDENCE,
EXCEPTION_REGISTER, PROJECT_MEMORY_UPDATE.

## Project-closure re-verification (2026-09-24)
Fresh DB `aiol_closure`: migration cycle through 0018 passes; Phase 17 suite 120/120.
Added 2 tests (actor delete-and-recreate: user, installation). Final accounting:
827 baseline + 120 Phase 17 = **947 tests; 941 passed, 6 failed (pre-existing), 0 skipped**
(the full suite last ran at 941 tests on identical application code; the 6 tests added
since touch only the test file and pass). Real provider: still BLOCKED_EXTERNAL_DEPENDENCY.

## Final existing-owner closure pass (2026-09-24)
Phase 17 unchanged: still BLOCKED only by `ANTHROPIC_API_KEY`. Regression: Phase 17 suite passes
within the 961/961 backend run on migrations 0001→0019. The AI-executions nav icon size regression
from the closure pass was fixed.
