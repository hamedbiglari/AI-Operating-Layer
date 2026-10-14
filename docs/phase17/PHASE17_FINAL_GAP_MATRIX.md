# Phase 17 — Final Gap Matrix (supersedes PHASE17_GAP_MATRIX.md)

Statuses: PASS · PARTIAL · IMPLEMENTED_NOT_VERIFIED · BLOCKED_EXTERNAL_DEPENDENCY · ENVIRONMENT_BLOCKED · NOT_IMPLEMENTED · OUT_OF_SCOPE · DEFERRED · FAILED

| ID | Requirement | Source | Current state | Code | DB | API | Worker | Provider | Security | Test | Runtime | Evidence | Status | Action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| G-01 | Canonical AIExecution = one real model invocation | P16 C | model + wrapper | ✓ | 0017 | ✓ | ✓ | adapter | ✓ | ✓ | live | TEST_MATRIX | PASS | — |
| G-02 | Migration reversible | P17 §34 | 0017, 0018 | ✓ | ✓ | — | — | — | — | cycle | fresh DB | RUNTIME | PASS | — |
| G-03 | Terminal immutability (app + DB) | P17c §10–11 | 0018 guard: creation facts, outcome facts, link columns, delete | ✓ | 0018 | — | — | — | ✓ | 15 kinds | live (backdate rejected) | SECURITY | PASS | fixed this closure (3 real loopholes) |
| G-04 | Execution created before call | P17 §14 | permit check + observed RUNNING at call time | ✓ | — | — | — | ✓ | — | ✓ | — | TEST | PASS | — |
| G-05 | Single invocation wrapper, no bypass | P17 §10,20 | permit + static scan | ✓ | — | — | — | ✓ | ✓ | ✓ | grep | SECURITY | PASS | — |
| G-06 | Provider abstraction isolated | P17 §11,21 | `app/integrations/llm/` only | ✓ | — | — | — | ✓ | — | ✓ | grep | — | PASS | — |
| G-07 | First real provider call | P17 §22–24 | adapter ready; no credential | ✓ | — | — | — | ✗ | — | mock | 401 w/o key | RUNTIME | BLOCKED_EXTERNAL_DEPENDENCY | provision `ANTHROPIC_API_KEY` + `AI_MODEL_PRICING_JSON` |
| G-08 | Success / failure / retry / fallback semantics | P17 §15,19–22 | new row per invocation, chain | ✓ | CHECK | chain | — | mock | — | ✓ | UI chain | TEST | PASS (mock provider) | real-provider rerun when G-07 unblocks |
| G-09 | Finalization race (reclaimer vs worker) | P17c §31 | row lock; verdict kept; late output not success | ✓ | — | — | ✓ | — | ✓ | ✓ | — | TEST | PASS | fixed this closure |
| G-10 | Tokens truthful | P17 §18 | NULL unless reported | ✓ | CHECK | ✓ | — | ✓ | — | ✓ | UI | TEST | PASS | — |
| G-11 | Unknown cost ≠ 0; estimate ≠ actual | P17 §16–17 | NULL; malformed price = unknown | ✓ | CHECK | ✓ | — | — | — | ✓ + mutation | UI | SECURITY | PASS | mutant M2a found and killed |
| G-12 | Billing boundary / no second ledger | P17 §31 | AIExecution owns provider usage; observation no longer copies cost | ✓ | — | — | — | — | ✓ | ✓ | — | EXCEPTION EX-11 | PASS | `AICostRecord` stays DEFERRED (billing) |
| G-13 | Admin-only provider cost | P17c §32 | OWNER/ADMIN only; no cost sort | ✓ | — | ✓ | — | — | ✓ | ✓ + mutation | live viewer | SECURITY | PASS | — |
| G-14 | Visibility linkage | P17 §23 | VisibilityTest → terminal execution; API exposes link | ✓ | FK | ✓ | ✓ | mock | ✓ | ✓ | live | TEST | PASS | — |
| G-15 | Research boundary | P17 §24 | no model call exists → no rows | — | — | — | — | — | — | static | — | FACT | PASS (nothing to link) | — |
| G-16 | SyncJob boundary | P17 §25 | ingestion only, no model call | — | — | — | — | — | — | static | — | FACT | PASS | — |
| G-17 | Tenant isolation / authorization | P17 §37 | ✓ | ✓ | composite FKs | ✓ | — | — | ✓ | ✓ + mutation | live | SECURITY | PASS | — |
| G-18 | Execution API | P17 §36 | list/detail/chain, filters, pagination, sort | ✓ | index | ✓ | — | — | ✓ | ✓ | live | — | PASS | — |
| G-19 | Operational surface | P17 §49 | live AI Executions screen in the dashboard | ✓ | — | ✓ | — | — | ✓ | Chrome E2E | live | RUNTIME | PASS | — |
| G-20 | Stale RUNNING recovery scheduled | P17 §33 | beat schedule + compose worker/beat | ✓ | partial idx | — | ✓ | — | ✓ | ✓ | live beat | RUNTIME | PASS (compose run ENVIRONMENT_BLOCKED) | — |
| G-21 | Audit separation | P17 §30 | wrapper writes no audit row | ✓ | — | — | — | — | — | ✓ | — | TEST | PASS | — |
| G-22 | Request correlation | P17 §29 | request_id optional; no OTel | ✓ | — | — | — | — | — | — | — | EX-02/03 | PASS (by design) | — |
| G-23 | Browser / RTL / responsive | P17c §39–40 | new screen verified | — | — | — | — | — | — | Chrome | live | RUNTIME | PASS for the Phase 17 screen | — |
| G-24 | Performance | P17c §41 | 1k/10k/20k measured; list index added | ✓ | 0018 idx | — | — | — | — | — | measured | RUNTIME | PASS (synthetic) | — |
| G-25 | Regression reconciled | P17c §36 | 945 tests; 6 pre-existing failures | — | — | — | — | — | — | ✓ | — | TEST_MATRIX | PASS | — |
| X-01 | `create_all` on a fresh DB fails (ai_agents composite FK) | Phase 13 | pre-existing, verified on pre-P17 tree | | | | | | | | | | OUT_OF_SCOPE | Phase 13 model drift |
| X-02 | Older visibility_tests composite FKs use plain SET NULL | Phase 12 | pre-existing, untouched | | | | | | | | | | OUT_OF_SCOPE | Phase 12 schema |
| X-03 | 6 failing tests (telemetry ×2, access-policy ×1, sorting ×3) | Phase 13 | pre-existing, identical on pre-P17 tree | | | | | | | | | | OUT_OF_SCOPE | Phase 13 |
| X-04 | Harness SVG `width="var(--icon-size)"` console warnings | Phase 13 dashboard | pre-existing | | | | | | | | | | OUT_OF_SCOPE | dashboard |
| X-05 | Harness mobile table cards overflow container by 34 px | Phase 13 dashboard | pre-existing, same on existing screens (measured) | | | | | | | | | | OUT_OF_SCOPE | dashboard |
| X-06 | Rest of dashboard not wired to API | Phase 14 §12,65 | pre-existing integration gap | | | | | | | | | | OUT_OF_SCOPE | Phase 14 |
