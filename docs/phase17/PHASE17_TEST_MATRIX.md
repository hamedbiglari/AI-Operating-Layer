> Counts below are from the first Phase 17 pass. Final accounting: PHASE17_FINAL_REPORT.md (945 tests, 939 passed, 6 pre-existing failures).

# Phase 17 — Test Matrix

All provider-boundary tests are **MOCK_VERIFIED**: the real Anthropic adapter
(request building, streaming size cap, parsing, error mapping) runs against an
`httpx.MockTransport` with the fake key `sk-test-NOT-A-REAL-KEY-phase17`.
Database behaviour is exercised against a real PostgreSQL 16 schema built by
`alembic upgrade head` (not `create_all` — see Gap G-07).

| Layer | Test(s) in `tests/test_phase17_ai_execution.py` | Result |
|---|---|---|
| DATABASE — arc | valid parent; no parent (trigger); unknown parent_type; cardinality CHECK present | PASS |
| DATABASE — tenant | cross-tenant parent; cross-tenant knowledge object; cross-tenant user; cross-tenant previous execution (app + DB) | PASS |
| DATABASE — deletion | delete VisibilityRun → execution kept, FK NULL, org kept, parent_type kept | PASS |
| DATABASE — immutability | app guard; DB trigger rejects status / cost / tokens / provider change | PASS |
| UNIT/SERVICE — wrapper | row RUNNING before call; success usage/cost; usage absent → NULL; unknown price → NULL | PASS |
| PROVIDER ADAPTER | 401, 429, timeout, connect error, malformed JSON, missing content, 503, oversized body — safe error, no prompt/key | PASS (8) |
| RETRY | F→F→S chain + chain API order; independent costs, no double count; provider fallback; model fallback; manual retry | PASS |
| SECURITY | not-configured → no row; budget gate required; adapter refuses without permit; static no-bypass scan; API isolation/401/405; no secret/prompt leak (API, logs, row) | PASS |
| ACTOR | machine caller: installation_id set, user_id NULL | PASS |
| WORKER | stale RUNNING → ABANDONED, young row untouched, threshold floor | PASS |
| DOMAIN — Visibility | observation links terminal execution; retry links terminal; no credential → no row; wrong platform → no call; audit untouched | PASS |
| BUDGET | no call → no spend; settles to chain estimated cost | PASS |
| MIGRATION | `scripts/verify_migration_cycle.sh` base→head→base→head on fresh DB | PASS |
| RUNTIME (live processes) | see PHASE17_RUNTIME_EVIDENCE.md | PASS (no-credential path) |
| REAL_PROVIDER | — | BLOCKED_EXTERNAL_DEPENDENCY (no credential) |
| BROWSER | — | NOT_VERIFIED (no dashboard surface built) |

## Accounting (exact)

| | Count |
|---|---|
| Collected before Phase 17 | 827 |
| Added by Phase 17 | 39 |
| Collected now | 866 |
| Full-suite run (4 chunks, 864 tests at the time, alembic DB `aiol_p17`) | 858 passed, 6 failed, 0 skipped |
| The 2 tests added after that run (budget) + visibility suites re-run | 92 passed, 0 failed |
| Phase 17 file alone | 39 passed |

The 6 failures are pre-existing and unrelated to Phase 17:
`test_phase13_telemetry.py` ×2 and `test_phase13_access_and_agents.py` ×1 (recorded
in the Phase 14 report), and `test_sorting.py` ×3 — re-run on the
**pre-Phase-17 tree** against a fresh migrated DB: the identical 3 fail there
(7 unsorted Phase 13 telemetry routes). `/api/v1/ai-executions` initially added
itself to that list; it was fixed (canonical `SortParams`/`apply_sort`) and is
now absent from every failure message (verified with `-vv`).
