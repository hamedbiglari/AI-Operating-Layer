# Phase 17 — Security Evidence

All items below were executed; "test" = `tests/test_phase17_ai_execution.py` against an
alembic-built PostgreSQL 16 database, "live" = real uvicorn / Celery / Chrome.

| Area | Evidence | Result |
|---|---|---|
| Authentication | API without token -> 401 (test); dashboard with a bad token -> "Permission denied (HTTP 401)" state (live, Chrome) | PASS |
| Tenant read isolation | foreign detail / chain -> 404, foreign list -> empty (test) | PASS |
| Tenant write isolation | no POST/PUT/PATCH/DELETE route (405, test + live curl) | PASS |
| Cross-tenant linking (DB) | composite FKs reject foreign parent, knowledge object, user, previous execution (test) | PASS |
| IDOR on chain | recursive chain query is tenant-scoped at every step (test) | PASS |
| Terminal immutability (DB) | every creation/outcome column rejected via raw SQL for succeeded and failed rows (parametrized test); ORM mutation rejected; creation facts frozen even while RUNNING; link columns cannot be nulled while target exists or re-pointed; parent delete+recreate does not relink; DELETE rejected; tenant offboarding still removes chains | PASS |
| Concurrency | stale in-memory object cannot overwrite; reclaimer-vs-finalizer race keeps the reclaimer's verdict and never reports late output as success (row lock `SELECT … FOR UPDATE`) | PASS |
| Admin-only provider cost | viewer sees `provider_cost_visible=false` (API test) and "Hidden (admin only)" (live Chrome); owner sees cost; cost not sortable | PASS |
| Credential handling | key is `SecretStr`, env-only; fake key never appears in API body, logs, DB row (test); `.env.example` empty; repo scan finds no key pattern | PASS |
| Per-tenant credentials | none exist; a tenant cannot select or supply a credential (no API surface) | N/A (FACT) |
| Prompt / response leakage | AIExecution has no content columns; prompt absent from API, logs, row (test) | PASS |
| Error leakage | adapter surfaces status codes only, never provider bodies (401 body containing the prompt is not echoed — test) | PASS |
| Provider bypass | adapter refuses without a persisted RUNNING row (test); static scan: no provider HTTP outside `app/integrations/llm/` (test + grep) | PASS |
| Budget gate | invocation refused unless the caller cleared its budget (test) | PASS |
| CORS | closed by default (test); explicit origin allowed, foreign origin refused (live preflight); GET only, no credentials mode | PASS |
| Browser token storage | token kept in memory only; localStorage/sessionStorage untouched (live Chrome) | PASS |
| XSS in the new screen | all API values rendered with `textContent` / `<bdi>`; no `innerHTML` of API data (code review) | PASS (review) |

## Mutation testing (critical logic)
| Mutant | Result |
|---|---|
| M1 remove tenant filter from `get_execution` | KILLED |
| M2a malformed pricing -> zero price | SURVIVED -> test added -> KILLED |
| M2b missing token counts not treated as unknown | KILLED |
| M3 actual cost copied from estimate | KILLED |
| M4 budget gate disabled | KILLED |
| M5 provider cost visible to every role | KILLED |
| M6 app-level terminal guard removed | KILLED |

Not re-run this phase (outside Phase 17's surface): SSRF matrix, upload/file security,
rate limiting, session-expiry behaviour.
