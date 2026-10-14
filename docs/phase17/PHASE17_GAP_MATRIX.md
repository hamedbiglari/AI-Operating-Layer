> SUPERSEDED by PHASE17_FINAL_GAP_MATRIX.md (closure). Kept for history; its P17-12 statement "no beat schedule exists" was wrong.

# Phase 17 — Gap Matrix

| ID | Requirement | Implementation | DB | API | Worker | Provider | Security | Test | Runtime evidence | Status | Gap | Risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P17-01 | AIExecution model | ai_execution.py | yes | — | — | — | tenant FK | yes | migration | DONE | — | Low |
| P17-02 | Migration | 0017 | yes | — | — | — | — | cycle | cycle output | RUNTIME_VERIFIED | needs PG ≥15 (guarded) | Low |
| P17-03 | Persistence service | ai_execution_service.py | yes | — | — | — | immutability | yes | live run | DONE | — | Low |
| P17-04 | Shared wrapper, row before call | invocation.py | yes | — | — | — | budget gate, permit | yes | — | MOCK_VERIFIED | — | Low |
| P17-05 | Provider adapter | llm/base.py, anthropic.py | — | — | — | yes | no key leak | 8 cases | reachability 401 | MOCK_VERIFIED | — | Low |
| P17-06 | First real provider call | anthropic.py | — | — | — | — | — | — | — | BLOCKED_EXTERNAL_DEPENDENCY | no credential | — |
| P17-07 | Retry / fallback semantics | invoke_with_policy | chain CHECK | chain API | — | — | tenant chain | yes | — | MOCK_VERIFIED | — | Low |
| P17-08 | Domain result linkage | visibility llm provider | FK | — | yes | — | composite FK | yes | live no-credential run | MOCK_VERIFIED | synthesis junction not needed yet (DEFERRED) | Low |
| P17-09 | Usage / cost | pricing.py | CHECKs | — | — | — | — | yes | — | MOCK_VERIFIED | pricing from config, not a pricing table | Low |
| P17-10 | Audit separation | wrapper writes no audit | — | — | — | — | — | yes | — | DONE | — | Low |
| P17-11 | Tenant / security | composite FKs, scoped reads | yes | 404/401/405 | — | — | yes | yes | live 405 | DONE | full security matrix beyond this surface not rerun | Medium |
| P17-12 | Stale RUNNING | reclaim + task | partial index | — | task registered | — | — | yes | worker registration | PARTIAL | no beat schedule exists in the project to run it periodically | Medium |
| P17-13 | API | ai_executions.py | — | list/detail/chain | — | — | read-only | yes | live | RUNTIME_VERIFIED | — | Low |
| P17-14 | Regression | — | — | — | — | — | — | 866 | 858+92 | DONE | 6 pre-existing failures | Low |
| G-01 | Real provider end-to-end | — | — | — | — | — | — | — | — | BLOCKED_EXTERNAL_DEPENDENCY | credential | High until done |
| G-02 | Research / Recommendation / SyncJob AI paths | — | — | — | — | — | — | — | — | DEFERRED | no real model path in those domains | — |
| G-03 | Dashboard AI Execution surface | — | — | API exists | — | — | — | — | — | MISSING | no page; out of bounded scope | Medium |
| G-04 | Explicit Claude platform value | — | enum | — | — | — | — | — | — | DEFERRED | uses OTHER | Low |
| G-05 | request_id into Celery | — | — | — | — | — | — | — | — | DEFERRED | worker executions have no request_id | Low |
| G-06 | trace_id / span_id | — | — | — | — | — | — | — | — | DEFERRED | no tracing infra | Low |
| G-07 | `create_all` on a fresh DB | — | — | — | — | — | — | — | — | NOT_VERIFIED (pre-existing) | fails on `ai_agents` composite FK in the **pre-Phase-17 tree too** (verified); tests require an alembic-built DB | Medium |
| G-08 | Unsafe composite SET NULL on older visibility_tests FKs | — | — | — | — | — | — | — | — | NOT_VERIFIED (pre-existing) | not reproduced in new tables; existing ones untouched | Medium |
| G-09 | AICostRecord / billing | — | — | — | — | — | — | — | — | DEFERRED | out of scope | — |
| G-10 | Default list sort index | — | — | — | — | — | — | — | perf baseline | OBSERVATION | NULLS LAST sort not index-served | Low |
