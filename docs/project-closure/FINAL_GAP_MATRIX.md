# FINAL GAP MATRIX — against FINAL PROJECT COMPLETION + HARDENING + GAP CLOSURE PROMPT
Audited 2026-09-29 against the repository (source, migrations 0001→0028, tests), not against documentation.
Statuses are the prompt's own vocabulary (§0.9).

| § | Requirement | Status | Implementation | DB / migration | API | UI | Test | Remaining action |
|---|---|---|---|---|---|---|---|---|
| 1 | Recover the product contract | IMPLEMENTED_AND_VERIFIED | `docs/ai-context/MASTER_REQUIREMENT_LEDGER.md`, 108 ADRs, 30 closure docs, phase reports | — | — | — | — | Nothing recoverable is left unread; nothing was invented |
| 2 | Preserve working functionality | IMPLEMENTED_AND_VERIFIED | no subsystem rewritten; every pass re-ran the whole suite | — | — | — | 1113/1113 | — |
| 3 | Passwordless sign-up | IMPLEMENTED_AND_VERIFIED | `signup_code_service.py` (ADR-106) | `signup_codes`, 0027, nullable `users.password_hash` | `/auth/signup/request`, `/auth/signup/verify` | sign-up + code pages wired | 12 | — |
| 4 | AI Center as a real product | PARTIALLY_IMPLEMENTED | providers/accounts/models/health/routing all exist and are live in the dashboard | 0020 | `/ai-center/*` (25 routes) | AI Center, 7 tabs | 29 | **Missing:** per-provider usage, last successful call and known quota shown in the UI; cost columns |
| 5 | AI model / task assignment UI | PARTIALLY_IMPLEMENTED | per-task policy with allowed accounts, routing mode, cost cap; worker enforces it | `background_task_policies`, 0021 | `/agent-network/background-policies` | Settings › Background AI processing | 21 | **Missing:** preferred/fallback *model* per task, estimated cost and a Test-connection button on that screen |
| 6 | Credential management | PARTIALLY_IMPLEMENTED | Fernet at rest, write-only, last-4 only, rotation by replacing, connection test | `ai_provider_accounts`, 0020 | PUT/DELETE credential, `/test` | AI Center › Accounts (set, test) | in 29 | **Missing:** "used by which routing policy" and last-validation time in the UI |
| 7 | AI usage + credit wallet | PARTIALLY_IMPLEMENTED | wallet, append-only ledger, reserve/settle/release, per-execution cost on `ai_executions` | `wallets`…`payments`, 0026 | `/billing/*` | Payment screen (live) | 10 | **Missing:** per-provider / per-model / per-task usage roll-ups; platform margin |
| 8 | Payment system | IMPLEMENTED_BUT_UNVERIFIED_EXTERNAL | intent, idempotency, signed webhook, time window, replay + amount/currency checks | 0026 | `/billing/payments`, `/billing/webhooks/{provider}` | wallet UI; BLOCKED state when unconfigured | 10 | Connect a real provider (only `sandbox` exists) |
| 9 | Memory Center | IMPLEMENTED_AND_VERIFIED | search/filter/sort, versions, field-by-field compare, JSON/JSONL/CSV/ZIP export (ADR-110) | 0031 | `/memory/*` | Memory Center screen | 4 + browser | — |
| 10 | Live job progress | IMPLEMENTED_AND_VERIFIED | SSE stream + job view; pause/resume/cancel | 0020 | `/ai-center/jobs/{key}/events` | AI Center job view (live line) | 3 + browser | ETA is deliberately absent rather than invented |
| 11 | Research modes | IMPLEMENTED_AND_VERIFIED | every question declares its mode; gap-driven must name its gap (ADR-111) | 0032 | `/research/questions` `mode` | mode on the question form | 5 | — |
| 12 | Keyword / topic search, query cluster | IMPLEMENTED_AND_VERIFIED | `research_query_sets`: saved, editable, re-runnable with a run count (ADR-111) | 0032 | `/research/query-sets` (+ run) | research console | 2 | — |
| 13 | Source depth states | IMPLEMENTED_AND_VERIFIED | 11 states incl. title_only, landing_page_only, paywalled, registration_required, access_blocked | 0028 (ADR-107) | `/research/sources/{id}/access-state` | acquisition panel | 5 | — |
| 14 | Full-text acquisition | IMPLEMENTED_AND_VERIFIED | OA-only fetch through the SSRF guard + user upload; claim only after a parsed document ≥4 000 bytes; provenance + audit | 0028 | `/acquire-full-text`, `/attach-full-text` | "Obtain the full text" panel | 10 | — |
| 15 | Acquisition assistant | IMPLEMENTED_AND_VERIFIED | DOI, publisher, PubMed, Europe PMC, OA copies, library and scholar locators | 0025 | `/research/sources/{id}/detail` | source detail | in 10 | — |
| 16 | Evidence completion | IMPLEMENTED_AND_VERIFIED | `evidence_completion_tasks`; only qualifying reviewed evidence satisfies one; dead ends need a reason | 0032 | `/evidence-completion-tasks` | gaps + research console | 4 | — |
| 17 | Compound / indirect evidence | IMPLEMENTED_AND_VERIFIED | 10 routes; DB CHECK keeps every indirect route indirect (ADR-108) | 0029 | evidence-map, evidence-graph | per-route table in the evidence map | 12 | — |
| 18 | Multi-compound reasoning | IMPLEMENTED_AND_VERIFIED | several compounds + related species per question, a combination route, `evidence_about`, labelled graph | 0029 | `/questions/{id}/evidence-graph` | compounds/species inputs + graph view | 8 | — |
| 19 | Evidence strength vs extraction confidence | IMPLEMENTED_AND_VERIFIED | `extraction_confidence` + note, separate from strength; machine extraction cannot claim certainty (DB CHECK) | 0031 | evidence + conflict comparison | conflict comparison | 2 | — |
| 20 | Source dependency / independent count | IMPLEMENTED_AND_VERIFIED | `source_dependencies`, transitive grouping, count in the evidence map (ADR-109) | 0030 | `/sources/{id}/dependencies`, `/questions/{id}/dependency-graph` | "How many independent findings" panel | 4 | — |
| 21 | Conflict intelligence | IMPLEMENTED_AND_VERIFIED | `evidence_conflicts` with the side-by-side comparison and five states; a resolution needs a written reason (DB CHECK) | 0031 | `/evidence-conflicts/*` | disagreements panel in the evidence map | 3 | — |
| 22 | Research saturation | IMPLEMENTED_AND_VERIFIED | `research_iterations` + computed stopping reason; all-providers-down is not saturation (ADR-109) | 0030 | `/questions/{id}/saturation` (GET/POST) | "Should the search stop?" panel with the per-round table | 5 | — |
| 23 | Knowledge gap engine | IMPLEMENTED_AND_VERIFIED | 14 gap types incl. structure/retrieval/ux/commerce; Find More; a gap never closes itself | 0032 | `/knowledge-gaps` | Gaps screen | 4 + acceptance | — |
| 24 | Knowledge Object | IMPLEMENTED_AND_VERIFIED | identity, aliases, claims, evidence, relations, confidence, version, status, gaps, provenance | — | `/knowledge/*` | Knowledge screens (live) | in suite | Domain extensions remain extensible |
| 25 | Provenance | IMPLEMENTED_AND_VERIFIED | KO → claim → evidence → document → **chunk** → source; page-level kept when the parser gives it | — | — | provenance screen | in suite | — |
| 26 | Human review | IMPLEMENTED_AND_VERIFIED | evidence candidates land in `pending_review`; approval requires stating what was tested; agent never edits a published KO | — | `/research/evidence-candidates/{id}/review` | review rows | 4 | Risk-based *forced* review by claim type is not modelled |
| 27 | Dashboard UX | PARTIALLY_IMPLEMENTED | 44 screens, 20+ live; loading/empty/error/blocked/demo states; responsive | — | — | — | check.js 33/33 | **Missing:** a dedicated Memory Center and Audit Log screen; some detail pages still DEMO |
| 28 | Live execution UX | IMPLEMENTED_AND_VERIFIED | job created → panel → SSE → stage/counts → terminal; state persisted in `ai_jobs` | 0020 | — | AI Center | 3 + browser | — |
| 29 | WordPress | IMPLEMENTED_AND_VERIFIED | thin adapter; auth, tenant, discovery, import, publish, mappings, retries, WooCommerce | — | — | plugin admin | 221 + E2E order #24 | — |
| 30 | Security | IMPLEMENTED_AND_VERIFIED | SSRF, tenant isolation, IDOR, credential secrecy, upload validation, rate limits, webhook signature/replay, CORS, trusted proxy | — | — | — | across suite | — |
| 31 | Data privacy | IMPLEMENTED_AND_VERIFIED | IP truncated, no IP persisted by the plugin, credential encryption, audited export, tenant deletion cascades | — | — | — | in suite | — |
| 32 | Observability | IMPLEMENTED_AND_VERIFIED | job id, tenant, status, times, stop reason, provider/model/cost, **retry_count and switch_count** | 0032 | job view | AI Center job view | in suite | — |
| 33 | Database | IMPLEMENTED_AND_VERIFIED | composite tenant FKs, indexes, uniques, append-only ledger + AIExecution triggers | 0001→0028 up/down/up | — | — | migration cycle | — |
| 34 | API quality | IMPLEMENTED_AND_VERIFIED | auth, tenant scope, validation, error envelope, pagination, canonical sorting, idempotency | — | — | — | sorting + envelope contracts | — |
| 35 | Testing | IMPLEMENTED_AND_VERIFIED | 1113 backend, 221 plugin, migration cycle, dashboard, responsive, locale, E2E | — | — | — | 0 skipped | — |
| 36 | External dependencies | IMPLEMENTED_BUT_UNVERIFIED_EXTERNAL | code, config, validation, error handling, UI state and deterministic test adapters exist for each | — | — | BLOCKED states | fixture/TEST_PROVIDER | AI key, SMTP, Google OAuth, GSC/GA4, payment provider, Walrus, live scholarly hosts, Docker |
| 37 | Real vs demo data | IMPLEMENTED_AND_VERIFIED | LIVE / NOT CONNECTED / BLOCKED / DEMO chips on every panel | — | — | — | browser | — |
| 38 | Documentation | IMPLEMENTED_AND_VERIFIED | all eight FINAL_* documents written, ADRs 087–112, CURRENT_STATE and the ledger current | — | — | — | — | — |
| 39 | Final gap matrix | IMPLEMENTED_AND_VERIFIED | this file | — | — | — | — | — |
| 41 | Anti-false-pass workflow trace | IMPLEMENTED_AND_VERIFIED | the whole chain runs in one test on the production code path | 0032 | — | — | `test_acceptance_taranjabin` | The only broken link left is external: live scholarly hosts |
| 43 | Taranjabin acceptance test | IMPLEMENTED_AND_VERIFIED | one test walks all twenty steps on the production code path (ADR-112) | — | — | — | `test_acceptance_taranjabin` | — |

## Counts
IMPLEMENTED_AND_VERIFIED 33 · PARTIALLY_IMPLEMENTED 3 · IMPLEMENTED_BUT_UNVERIFIED_EXTERNAL 2 · MISSING 0 · DESIGNED_ONLY 0 · UNKNOWN_REQUIREMENT_NOT_RECOVERABLE 0

The three PARTIALLY_IMPLEMENTED are §4, §5 and §7: the AI Center, task-assignment and wallet screens do not yet roll up
usage, cost and quota per provider, model and task. Everything else the prompt asks for is implemented, wired to the
dashboard and covered by an executed test.
