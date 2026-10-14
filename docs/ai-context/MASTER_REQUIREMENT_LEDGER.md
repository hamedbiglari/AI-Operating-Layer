# Master Requirement Ledger (canonical; append-only)

Source for all REQ-AIC / REQ-KW / REQ-DI / REQ-MEM rows: owner prompt "GLOBAL AI CENTER + AI RESOURCE
REGISTRY + MULTI-ACCOUNT ROUTING + SHARED MEMORY + DEMAND INTELLIGENCE + KEYWORD-DRIVEN KNOWLEDGE ENGINE",
2026-09-25. Authority: USER-APPROVED REQUIREMENT. Status values: IMPLEMENTED_VERIFIED, IMPLEMENTED_PARTIAL,
REGISTERED_OPEN, BLOCKED_EXTERNAL_DEPENDENCY, NOT_ESTABLISHED.

| REQ-ID | Title | Status (2026-09-25) | Components | Tests / evidence |
|---|---|---|---|---|
| REQ-AIC-001 | AI Resource Registry (provider ≠ account ≠ model, credentials, health, dynamic models) | see AI_CENTER_FINAL_VERIFICATION.md | migration 0020, `app/models/ai_center.py`, `/ai-center/*` | `test_ai_center.py` |
| REQ-AIC-002 | Multiple accounts of the same provider, tracked independently | idem | idem | idem |
| REQ-AIC-003 | Six routing modes, explainable decisions | idem | `app/services/ai_routing_service.py`, `ai_routing_decisions` | idem |
| REQ-AIC-004 | Shared AI Working Memory (tenant-isolated, versioned, provenance) | idem | `ai_working_memory`, `app/services/ai_memory_service.py` | idem |
| REQ-AIC-005 | Checkpoint before switching + durable handoff package + resume | idem | `app/services/ai_job_service.py`, `ai_jobs`, `ai_job_items` | idem (100-document scenario) |
| REQ-AIC-006 | Walrus optional semantic memory (non-canonical, server-side, graceful degradation) | IMPLEMENTED_PARTIAL — boundary + honest health only; no client (contract unverified, no credentials) | `app/integrations/memory/walrus.py` | `test_walrus_is_optional_and_reported_honestly` |
| REQ-AIC-007 | AIExecution integration (account attribution, job parent, stop reason); AIExecution stays canonical | see final verification | migration 0020, `app/models/ai_execution.py` | `test_arc_now_rejects_two_parents`, `test_stop_reason_is_immutable_once_terminal` |
| REQ-AIC-008 | Credential management: encrypted at rest, write-only, rotate/disable/delete, connection test | see final verification | `app/security/credential_crypto.py`, `/ai-center/accounts/*/credential`, `/test` | credential + connection tests |
| REQ-AIC-011 | AI Resource Discovery Registry seeded from the owner's list; status machine; never infer ACTIVE | see final verification | `ai_discovery_entries`, `app/services/ai_discovery_seed.py` | `test_discovery_seed_is_idempotent_and_never_claims_activity` |
| REQ-AIC-012 | Cost control before spending (estimate, budget, stop) | see final verification | `app/services/ai_job_service.py` | `test_job_cost_limit_stops_the_job` |
| REQ-AIC-009 | Official-source verification of every discovered resource (web research per entry) | REGISTERED_OPEN | — | — |
| REQ-AIC-010 | Provider usage / quota / balance synchronisation from provider APIs | BLOCKED_EXTERNAL_DEPENDENCY (no credentials) | — | — |
| REQ-DI-001/002/003 | Demand / human-behaviour / AI-behaviour intelligence (GSC, GA4, …) | REGISTERED_OPEN — connectors need external OAuth; first-party telemetry (Phase 13) exists | — | — |
| REQ-KW-001 | Keyword & Query Workspace per Knowledge Object | idem | `knowledge_keywords` | idem |
| REQ-KW-002 | Keyword upload (CSV, Excel, TXT, JSON, manual) keeping original values | idem | idem | idem |
| REQ-KW-003 | Search New Sources from selected keywords → research tasks | idem | idem | idem |
| REQ-KW-004 | Keyword → … → published content traceability | REGISTERED_OPEN (keyword → research task link implemented) | — | — |
| REQ-KO-001 | Knowledge Object page expansion (price with timestamp/source, etc.) | REGISTERED_OPEN | — | — |
| REQ-SET-001 | All Settings preferences persisted through backend | REGISTERED_OPEN (organization name persisted since the closure pass) | — | — |
| REQ-UX-001 | English locale free of Persian UI strings (automated audit) | REGISTERED_OPEN | — | — |
| REQ-CR-001 | Platform AI credits / internal ledger | NOT_ESTABLISHED (ADR-082..084 PROPOSED; prompt conditions it on approval) | — | — |
| REQ-MEM-001 | Master Memory registration of every material change | IMPLEMENTED (this ledger, change ledger, ADRs, current state) | `docs/ai-context/*` | — |

## Update — final existing-owner correction pass (2026-09-25)
| REQ-ID | Status | Detail |
|---|---|---|
| REQ-AIC-013 (Background Processing Policy) | IMPLEMENTED_BACKEND + API_ONLY | Tables + API; worker enforcement = REGISTERED_OPEN (worker must read policy before dispatch) |
| REQ-AIC-014 (Agent Orchestration / Interoperability) | IMPLEMENTED_BACKEND | 8 tables + 13 routes; agent-to-agent handoffs; memory bindings; tenant isolated; 12 tests |
| REQ-AIC-015 (AI Catalog as first-class nav) | PRODUCTION_UI_LIVE | screen-ai-catalog; reads /ai-center/discovery; no sample data; search/filter |
| REQ-AIC-016 (Shared Memory Control screen) | PRODUCTION_UI_LIVE | Settings cards + AI Center tabs; creates memory profiles; shows semantic backend status |
| REQ-UX-002 (Agent Network visible in Dashboard) | PRODUCTION_UI_LIVE | AI Center → Agent network tab |

## Update — final closure pass (2026-09-26)
| REQ-ID | Status | Evidence |
|---|---|---|
| REQ-AIC-013 Background policy worker enforcement | IMPLEMENTED_VERIFIED | worker-path tests; Settings UI; migration 0022 |
| REQ-AIC-014 Agent orchestration (A → B handoff) | RUNTIME_VERIFIED (internal, TEST_PROVIDER) | browser orchestration console; 20 tests |
| REQ-KW-004 Keyword → published content | TEST_VERIFIED + UI | keyword_traces (0022) |
| REQ-DI-001/002/003 Demand intelligence | IMPLEMENTED_VERIFIED (internal sources); live GSC/GA4 BLOCKED_EXTERNAL_DEPENDENCY | demand_* (0023), 6 tests, browser |
| REQ-UX-001 English locale | RUNTIME_VERIFIED | automated audit, 0 UI strings |

## Update — completion pass (2026-09-27)
| REQ-ID | Status | Evidence |
|---|---|---|
| REQ-SET-001 Settings persisted through backend | IMPLEMENTED_VERIFIED | user_preferences (0024), 5 tests, browser reload |
| Phase 14 dashboard wiring (remaining screens) | IMPLEMENTED_VERIFIED | 8 more live screens + live Add source; fixture-only screens explicitly labelled |
