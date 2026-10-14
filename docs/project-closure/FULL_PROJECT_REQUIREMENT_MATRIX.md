# Full Project Requirement Matrix (Phase 0 → 17)

Evidence keys: **T** = executed test suite this environment (947 tests: 941 pass, 6 pre-existing fails); **R** = runtime run against real PostgreSQL/Redis/uvicorn/Celery (Phases 14–17 runs); **B** = real Chrome; **P** = WordPress plugin standalone PHP suite (first execution: 216/219 assertions pass). Truth class in brackets.

| ID | Requirement | Original source | Phase owner | Current implementation | Test | Runtime | Security | Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| R-01 | Repo, Docker, FastAPI, PostgreSQL, Redis, Alembic | MASTER §62 P0 | 0 | present; compose fixed in P17 | T | R (no Docker) | — | PARTIAL | compose never run: ENVIRONMENT_BLOCKED [FACT] |
| R-02 | Organizations, users, sites, auth, tenant isolation | MASTER P1, §52 | 1 | present | T | R: signup/login/401/404, 8+ cross-tenant attacks | R | COMPLETE | P14/P15/P17 runs [FACT] |
| R-03 | Knowledge objects, entities, relationships, versions, gaps | MASTER P2 | 2 | present | T | R: KO create/list/update/version | tenant R | COMPLETE | [FACT] |
| R-04 | Sources, documents, chunks, pgvector | MASTER P3 | 3 | present | T | R: source + URL ingestion job | SSRF guard reached | COMPLETE (fetch blocked by sandbox egress) | [FACT] |
| R-05 | Claims, evidence, claim↔evidence, conflicts; evidence ≠ claim | MASTER P4, §63 | 4 | separate tables/APIs | T | not run via API this project | — | COMPLETE (test-verified) | [FACT tests; SIGNAL runtime] |
| R-06 | Research engine; knowledge ≠ research | MASTER P5 | 5 | tasks + honest NotConfigured provider | T | — | — | PARTIAL | no real research provider exists [FACT] |
| R-07 | Query, intent, query clustering/groups | MASTER P6 | 6 | present | T | — | — | COMPLETE (test-verified) | [FACT] |
| R-08 | Products, offers, product evidence, trust; product ≠ offer | MASTER P7, §63 | 7 | present | T | not run in pilot | — | COMPLETE (test-verified) | Phase 15 Case K not executed [FACT] |
| R-09 | Recommendation (evidence-backed, abstention) | MASTER P8 | 8 | rule/policy based, no model | T | — | — | COMPLETE (test-verified) | [FACT] |
| R-10 | WordPress adapter (thin) | MASTER P9, §38 | 9 | plugin; no REST routes of its own (P test) | P | never run inside WordPress | P security 33/33 | BLOCKED | WordPress not obtainable here [FACT] |
| R-11 | WooCommerce adapter / sync | MASTER P10, §40 | 10 | contract + sync code | P 54/54 | never run inside WooCommerce | — | BLOCKED | [FACT] |
| R-12 | AI/REST interfaces, context exchange | MASTER P11 | 11 | `/ai/*`, `/context` | T | — | tenant | COMPLETE (test-verified) | [FACT] |
| R-13 | AI Visibility; mention ≠ citation ≠ recommendation ≠ product ≠ click ≠ visit ≠ purchase | MASTER P12, §31 | 12 | separate signal columns; fixture/not-configured honest | T | R (no-credential path) | — | PARTIAL | no real provider run [FACT] |
| R-14 | Rights layer / AI access policy | MASTER P13, §37 | 13 | access policies, telemetry | T (1 pre-existing fail) | — | — | PARTIAL | specific-agent rule test fails [FACT] |
| R-15 | Analytics / demand / telemetry incl. IP per ADR-079 | P13 REQ | 13 | present | T (2 pre-existing fails) | — | — | PARTIAL | [FACT] |
| R-16 | Dashboard as operational control plane wired to backend | MASTER P14; P14 §12–13, §65 | 14 | harness = fixture prototype; ONE live screen (AI executions) | — | B for AI executions only | — | PARTIAL | [FACT] |
| R-17 | Admin dashboard backend, support tickets, OTP login, billing/wallet/trial | P14 §31–33, §41–43 (conditional on scope) | 14 | UI mock-ups only; no API routes | — | — | — | MISSING | route scan [FACT]; billing DESIGNED only |
| R-18 | Async processing, manual retry, idempotency | P14 §18–20, P15 | 14/15 | present | T | R | tenant R | COMPLETE | [FACT] |
| R-19 | Pilot (10–20 KOs, 5–10 products, 50–100 evidence/articles) | MASTER §55, P15 | 15 | smoke pilot only (1 KO, 1 source) | — | partial | — | NOT_VERIFIED | [FACT] |
| R-20 | MVP success loop query→…→product→click→cart→purchase | MASTER §56 | 15 | click/cart/purchase not modelled; happens on merchant site | — | — | — | NOT_VERIFIED | [FACT: no routes] |
| R-21 | AI-visibility loop with a real AI system | MASTER §56 | 12/17 | pipeline ready | T | — | — | BLOCKED | credential [FACT] |
| R-22 | AIExecution canonical record (Phase 16 C) | P16/P17 | 17 | implemented, immutable, scheduled cleanup, live screen | T 120 | R + B | R | COMPLETE except real provider | [FACT] |
| R-23 | First real AI provider call | P17 §22–24 | 17 | adapter ready | mock | 401 without key | — | BLOCKED | [FACT] |
| R-24 | Resource/cost control (budget before spend; unknown ≠ 0) | P14 §23–24, P17 | 12/17 | visibility budget + execution cost | T | R | R | COMPLETE (scope: AI visibility) | [FACT] |
| R-25 | Scale | MASTER P16 | — | not started | — | — | — | SUPERSEDED (numbering) / not yet due per §55 | [INFERENCE from §55] |
| R-26 | Stack-neutral Cloud Core = source of truth; WordPress = adapter | MASTER §63 | all | plugin registers no REST routes; all state in Cloud Core | P | — | — | COMPLETE | [FACT] |
| R-27 | Project memory synchronized | MASTER §61 | all | was stale (Phase 13); updated in this audit | — | — | — | COMPLETE (after update) | CURRENT_STATE.md [FACT] |
