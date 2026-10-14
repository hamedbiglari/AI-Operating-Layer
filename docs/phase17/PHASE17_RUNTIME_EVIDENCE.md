# Phase 17 — Runtime Evidence (closure)

Sandbox: PostgreSQL 16 + pgvector, Redis 7, real `uvicorn`, real Celery worker and
Celery beat, real Chrome 131 via Puppeteer. No Docker. No AI provider credential.

## Migration (fresh DB `aiol_p17final`)
`scripts/verify_migration_cycle.sh`: base -> head (0001..0018) -> base -> head,
36 upgrade steps, ends with "=== Migration cycle verified: base -> head -> base -> head ===".
`alembic current` -> `0018 (head)`. Triggers present: `trg_ai_executions_guard_delete`,
`trg_ai_executions_immutable_terminal`, `trg_ai_executions_require_parent`.

## No-credential provider path (live)
Visibility run (platform=other, provider=anthropic, priced, no key) through the worker:
observation `not_configured`, `ai_execution_id` NULL, 0 execution rows, budget spent 0.0000.

## Provider reachability
`POST https://api.anthropic.com/v1/messages` without any key -> HTTP 401. The only missing
input is a credential.

## Scheduled stale-execution recovery (live beat + worker)
Interval 5 s, threshold 120 s; one RUNNING row inserted 2 h old, one fresh.
beat: "Sending due task ai-executions-reclaim-stale" every 5 s.
worker: `{'reclaimed': 1}` then `{'reclaimed': 0}`.
rows: stale -> `abandoned | stale_running_reclaimed | completed | cost NULL`; fresh -> `running`.
Also observed: backdating `started_at` of an existing row via UPDATE is rejected
("creation facts are immutable") — the hardened trigger working on a live DB.

## Dashboard operational surface (live Chrome against the real API)
Rows were produced by the real invocation wrapper with only the provider HTTP mocked
(no credential exists); they are labelled MOCK-provider data, not real-provider evidence.

| Check | Result |
|---|---|
| Before connecting: rows shown | 0 (no fixture data) |
| Unreachable URL | error state, CORS hint |
| Invalid token | "Permission denied (HTTP 401)" |
| Tenant with no executions | empty state, total 0 |
| Owner | 5 rows; stats 5 / 2 / 3 / 0; costs "USD 0.000182 (estimated)" or "Unknown"; tokens "12 / 34" or "Not reported" |
| Detail + attempt chain | chain `rate_limited -> rate_limited (retry)` |
| Status filter rate_limited | 2 rows |
| Viewer role | every cost cell "Hidden (admin only)" |
| RTL (dir=rtl) | mirrored layout, no horizontal page overflow; Persian stage label renders |
| Dark theme | rendered |
| 390 px / 820 px | no horizontal page overflow; mobile card labels present |
| Token in local/session storage | no |
| New console errors | none (pre-existing harness `var(--icon-size)` SVG attribute warnings excluded; see gap matrix) |

Screenshots were captured and reviewed during verification (desktop, dark, RTL, mobile,
tablet, viewer, error, denied, empty); they are not committed to the repository.

## Performance (dedicated DB, 20,000 other-tenant rows also present)
p50/p95 ms, via the service layer:

| Tenant rows | detail | list p1 | status=failed | provider+model | page at offset N/2 | sort duration | chain depth 50 |
|---|---|---|---|---|---|---|---|
| 1,000 | 0.44/0.71 | 2.85/3.10 | 2.35/2.82 | 2.26/2.50 | 2.74/2.92 | 3.35/3.61 | 2.59/2.89 |
| 10,000 | 0.49/0.60 | 8.93/9.32 | 3.37/3.45 | 3.00/3.13 | 9.14/9.41 | 9.38/9.49 | 2.39/2.53 |
| 20,000 | 0.43/0.50 | 15.00/15.40 | 4.17/4.45 | 3.64/3.75 | 18.41/18.81 | 15.78/16.62 | 2.34/2.82 |

Finding: default page-1 order (`started_at DESC NULLS LAST, id`) was served by a full sort.
Fix: `ix_ai_executions_org_list_order` (in 0018). After: 20,050 rows page 1 p50 3.03 / p95 3.49 ms,
plan = Index Scan. Offset pagination remains O(offset) (project-wide API convention); sort by
`duration_ms` is not indexed. Synthetic microbenchmarks; not a production-scale claim.
