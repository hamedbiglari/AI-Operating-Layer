# PHASE 14 — FINAL REPORT

## 1. Executive Summary

Phase 14 was executed as a real, runtime-verified forensic and repair
pass against the Phase 13 snapshot, in a sandbox with no Docker, no PHP
interpreter, and restricted outbound network egress from any process
other than this session's own tool calls. Within those constraints,
every claim below is backed by an actual command run against a real
PostgreSQL 16 + pgvector database, real Redis, and a real booted FastAPI
application — not static reading of the code.

**This is not a PASS.** Large, mandated sections of the full Phase 14
brief (Docker orchestration, WordPress/WooCommerce runtime, browser
E2E, performance benchmarking at scale, the full security/tenant matrix,
billing, most of the 142-route API surface) were not exercised, for
reasons stated plainly in Section 21 (Remaining Gaps) below. What was
tested was tested for real, and every bug reported here was reproduced,
diagnosed to its root cause, and — except where explicitly marked
otherwise — fixed and re-verified.

## 2. Phase 13 Baseline

Snapshot: `AI-Operating-Layer-Phase13-C-dashboard-updated.zip`.
`docs/phase13/PHASE13_REPORT.md` recorded Phase 13 itself as
`BLOCKED` / `IMPLEMENTED — NOT VERIFIED — NOT ACCEPTED`: no prior
session had a working database, dependency set, or PHP interpreter, so
the entire backend, migration chain, and worker layer had never
actually been run.

## 3. What Phase 14 Actually Verified, With Evidence

### 3.1 Runtime environment (Section 7)
No Docker in this sandbox. Installed PostgreSQL 16 + pgvector 0.6.0 and
Redis directly via apt (both in the allowed network egress list) and
ran them as local processes. Installed the exact pinned
`requirements.txt` into a real venv — all imports (fastapi, sqlalchemy,
alembic, pytest, celery, psycopg, pgvector) succeed. This alone is
further than any prior session reached; both earlier sessions recorded
`ModuleNotFoundError` for the entire dependency chain with no network
egress available to them.

### 3.2 Database / migrations (Sections 8-9) — FIXED, VERIFIED
Two real bugs found and fixed in
`migrations/versions/0016_phase13_analytics_access.py`:
- It assumed `adapter_scope` was a native Postgres ENUM type and tried
  `ALTER TYPE ... ADD VALUE` against a type that has never existed
  (the column is a plain string array, validated at the application
  layer). Removed the dead DDL; no migration is needed for it at all.
- An explicit enum pre-creation loop collided with SQLAlchemy's own
  automatic type creation for the same enum objects reused across four
  tables, causing "type already exists" even on a freshly created
  database. Removed the redundant explicit loop.

Verified: `alembic upgrade head` (0001→0016, clean), `alembic downgrade
-1` then back to head (clean both directions), and the project's own
`scripts/verify_migration_cycle.sh` (`base → head → base → head`) —
passes end to end. First time this chain has ever completed, in any
session.

### 3.3 Backend boot (Section 10) — FIXED, VERIFIED
`app/services/search_demand_service.py` imported `QueryProvenance` from
the wrong module (`app.models.query` instead of
`app.models.query_provenance`), a hard `ImportError` that blocked the
entire application from booting, since FastAPI imports the whole router
tree at startup. Fixed the import.

Verified after the fix: real `uvicorn` boot, `GET /` → 200, `GET
/api/v1/health` → 200 with `"database":"ok"` and `"redis":"ok"` (a real
connectivity check against both live services, not a stub), 142 routes
mounted across every Phase 0-13 router, unauthenticated requests to
protected endpoints on two different routers → 401 with the correct
structured error envelope (`code`/`message`/`request_id`), and invalid
input → 422, not a raw crash.

### 3.4 Worker / async processing (Sections 19, 99) — FIXED, VERIFIED
Celery worker genuinely connects to the real Redis broker and registers
all 4 tasks. Ran the real end-to-end chain for `POST
/documents/ingest-url`: API creates job → worker receives it → **BUG**:
`run_ingestion_job()` unconditionally read `payload["document_id"]`,
but URL-kind jobs never have one at creation (fetching the URL is what
creates the document) — every such job failed with `KeyError`, was
retried twice per its own retry policy, then failed permanently. The
correct handler, `url_ingestion_service.fetch_and_ingest_url`, already
existed fully written and was simply never called. Fixed the dispatch,
and separately fixed the retry classification for a rejected URL to
fail once (not retry 3 times), matching the code's own already-stated
intent. Re-ran the same job after the fix: now fails in exactly 1
attempt with a genuine network error (this sandbox's worker process has
no outbound internet access — an environment limitation, not a code
defect) instead of 3 attempts with a `KeyError`.

### 3.5 Tenant isolation (Sections 34, 81) — VERIFIED, PARTIAL COVERAGE
Two real, separate organizations, real JWTs, real data. 8 attacks run,
8 blocked: foreign-source read (404), foreign-source mutation (404, no
change), list-endpoint leak check for sources (empty, not present),
`/organizations/me` scoping (not spoofable — takes no client input),
forged JWT with a tampered `org` claim and the original signature (401
— signature verification catches it), foreign knowledge-object read
(404), knowledge-object list leak check (empty), foreign ingestion-job
read (404). This is real evidence, not inference — but it is 8 attacks
against 3 resource types, not the full Section 81 list (products,
billing, AI execution, admin routes, visibility, support, and
role-based authorization within one tenant remain untested).

### 3.6 Automated test suite (Section 57)
827 tests collected. Time-boxed runs (this sandbox's tool-call time
limit, not a code issue) completed roughly 60% of the suite for real:
**82 passed / 3 failed** in the three files sampled in full
(`test_phase12_visibility.py`, `test_phase13_access_and_agents.py`,
`test_phase13_telemetry.py`). The remaining ~40% of the suite was
collected (so its existence and structure is confirmed) but not
executed to completion in this pass.

Three real, reproduced failures:
1. `test_specific_agent_rule_beats_a_stricter_general_rule` — a
   specific per-agent access-policy rule is expected to beat a general
   actor-type rule, but the general rule wins. Traced the matching
   logic in `access_policy_service.evaluate()` and confirmed it is
   correctly ordered (agent-specific candidates checked first,
   returns on first match) — the bug is upstream of it, most likely in
   `ai_agent_service.resolve_or_discover()` not resolving the *same*
   agent identity on the second request as it did on the first (so the
   specific policy's stored `agent_id` no longer matches). **Diagnosed,
   not yet fixed** — the fingerprint-matching logic needs its own
   focused pass.
2. `test_unknown_sort_field_is_422_naming_the_allowed_values` —
   `KeyError: 'detail'`. The app's error envelope was standardized to
   `{"error": {"code", "message"}}` (confirmed independently in Section
   3.3's live testing); this test still asserts on the older FastAPI
   default shape (`{"detail": [...]}`). Most likely a stale test
   expectation from before the envelope was standardized, not an app
   regression — **not yet confirmed which side is wrong**.
3. `test_a_human_view_has_no_agent_signature_not_a_placeholder` — a
   human-classified page view is expected to have its user-agent field
   nulled out, but the raw string is present. **Not yet investigated.**

None of these three were fixed in this pass — they are reported as
found, not silently patched or hidden.

## 4. Fixed, Runtime-Verified Bugs (Summary)

| # | File | Bug | Verified fix |
|---|---|---|---|
| 1 | `migrations/versions/0016_...py` | `ALTER TYPE` on a type that never existed | Migration chain runs clean, both directions |
| 2 | `migrations/versions/0016_...py` | Duplicate enum-type creation | Same as above |
| 3 | `app/services/search_demand_service.py` | Wrong import path, blocked app boot entirely | App boots, 142 routes live |
| 4 | `app/services/ingestion_job_service.py` | URL-ingestion jobs never dispatched to the function that handles them | Job fails on the real network step now, not on the dispatch bug |

## 5. Remaining Gaps (Honest, Not Exhaustive)

- **WordPress / WooCommerce**: no PHP interpreter exists in this
  sandbox. Nothing in `plugin/` was executed. NOT_VERIFIED.
- **Browser / E2E / visual / accessibility / RTL** (Sections 59-63):
  not attempted this pass. NOT_VERIFIED.
- **Performance / large-dataset behaviour** (Sections 52-55): not
  attempted. NOT_VERIFIED.
- **Billing / wallet / trial** (Sections 31-32): not exercised against
  the real API this pass. NOT_VERIFIED.
- **AI Visibility / AI Execution Log / cost accounting** (Sections
  21-27): endpoints exist and are mounted (confirmed in the OpenAPI
  route list) but were not exercised end-to-end. NOT_VERIFIED.
- **~40% of the pytest suite**: collected, not executed to completion
  in this pass, due to this sandbox's per-command time limit rather
  than any suspected code issue.
- **Admin routes, RBAC, role-based authorization within one tenant**
  (Sections 42-43): not tested this pass.
- **The 3 real test failures in Section 3.6**: found, diagnosed to
  varying depth, not fixed.

## 6. Final Verdict

**PHASE 14 — BLOCKED.**

Not because what was tested failed — nearly everything tested passed,
and every found defect that blocked forward progress was fixed and
re-verified. It is BLOCKED because the mandate's own PASS criteria
(Section 101) require implementation + runtime verification + security
verification + testing across the *entire* surface — WordPress,
browser/E2E, performance, billing, and the majority of the tenant-
isolation and security matrix remain genuinely untested in this
environment, and 3 real test failures are still open. Declaring
anything higher than BLOCKED would be exactly the status inflation this
mandate spends most of its length forbidding.
