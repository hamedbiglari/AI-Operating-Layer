# AI Center — Gap Matrix (2026-09-25)

| REQ-ID | Requirement | Status | Blocker / note |
|---|---|---|---|
| REQ-AIC-001 | AI Resource Registry (provider / account / model separation, credentials encrypted, health) | IMPLEMENTED_VERIFIED | 0020, 29 tests, browser |
| REQ-AIC-002 | Multiple accounts of same provider, tracked independently | IMPLEMENTED_VERIFIED | per-account credential, usage, health, limits |
| REQ-AIC-003 | Six routing modes, deterministic, explainable decisions | IMPLEMENTED_VERIFIED | all 6 modes tested, preview endpoint |
| REQ-AIC-004 | Shared AI Working Memory (versioned, tenant-isolated, provenance) | IMPLEMENTED_VERIFIED | ai_working_memory; checkpoint test |
| REQ-AIC-005 | Checkpoint before switch + durable handoff + resume from package | IMPLEMENTED_VERIFIED | 100-document scenario test; completed items never re-processed |
| REQ-AIC-006 | Walrus optional semantic memory, non-canonical | IMPLEMENTED (boundary) | no Walrus endpoint/credentials; health = DISCONNECTED; native memory canonical |
| REQ-AIC-007 | AIExecution account attribution + stop reason; Phase 16 lock preserved | IMPLEMENTED_VERIFIED | additive columns 0020; immutability trigger extended |
| REQ-AIC-008 | Discovery Registry seeded from owner's list; status machine; never infer ACTIVE | IMPLEMENTED_VERIFIED | 114 entries on import-seed; idempotent |
| REQ-AIC-009 | Official-source verification of every discovered resource | REGISTERED_OPEN | no automated verification; manual PATCH endpoint exists |
| REQ-AIC-010 | Provider usage / quota / balance sync from provider APIs | BLOCKED_EXTERNAL_DEPENDENCY | no provider credentials; unknown stays NULL |
| REQ-AIC-011 | Discovery corpus: owner's full list (~80+ names) | IMPLEMENTED_VERIFIED | ai_discovery_seed.py; 114 entries |
| REQ-AIC-012 | Cost gate before execution; job spend limit | IMPLEMENTED_VERIFIED | tested in test_job_cost_limit_stops_the_job |
| REQ-KW-001 | Keyword & Query Workspace per Knowledge Object | IMPLEMENTED_VERIFIED | knowledge_keywords table + 4 routes |
| REQ-KW-002 | Upload keywords (CSV / Excel / TXT / JSON / manual) keeping originals | IMPLEMENTED_VERIFIED | openpyxl; import_batch; raw column |
| REQ-KW-003 | Search New Sources from selected keywords → research tasks | IMPLEMENTED_VERIFIED | last_research_task_id traceability |
| REQ-KW-004 | Full keyword → published-content traceability | REGISTERED_OPEN | keyword → research task link exists; source → evidence → knowledge traceability is the existing pipeline (Phase 3/5) |
| REQ-DI-001 | Demand Intelligence (GSC, GA4 connectors) | REGISTERED_OPEN | external OAuth credentials required |
| REQ-DI-002 | Human behaviour intelligence | REGISTERED_OPEN | first-party telemetry (Phase 13) exists |
| REQ-DI-003 | AI behaviour intelligence | REGISTERED_OPEN | AI Visibility signals (Phase 12) exist; cross-product aggregation not built |
| REQ-MEM-001 | Master Memory registration | IMPLEMENTED | this ledger + ADR-087..094 + CURRENT_STATE update |
| REQ-CR-001 | Platform AI Credits | NOT_ESTABLISHED | ADRs PROPOSED only; prompt conditions it on approval |
