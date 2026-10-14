# Phase 17 — Exception Register

Every deliberate deviation from a literal requirement, with its reason. Nothing here
hides a defect; each item is either an explicit design exception or an external limit.

| ID | Requirement text | Exception | Reason | Class |
|---|---|---|---|---|
| EX-01 | "result_reference" listed as an AIExecution attribute | Not a column | Phase 16 closure (ADR-P16-AI-005): the result side holds the link (`visibility_tests.ai_execution_id`, typed junctions later). A reverse pointer would be a second, unenforced copy of the same fact. | DESIGN |
| EX-02 | trace_id / span_id | Not columns | No OpenTelemetry (or any tracing) is installed or running. `request_id` is the correlation that exists. | DESIGN (no infra) |
| EX-03 | request_id on every execution | NULL for worker-originated calls | The HTTP request id is not propagated into Celery tasks (FACT: grep). Correlation for worker calls is the typed parent FK. | DESIGN |
| EX-04 | Status vocabulary (running/succeeded/failed/timeout/rate_limited/cancelled) | Adds `abandoned` | A RUNNING row whose worker died has an unknown outcome; FAILED would assert a fact nobody knows. Cost stays NULL. | DESIGN |
| EX-05 | Terminal immutability of link columns (parent / actor / knowledge object) | May change in exactly one way: to NULL, only when the referenced row no longer exists | That is the `ON DELETE SET NULL (col)` referential action required by Phase 16. Nulling while the target exists, or re-pointing, is rejected by the trigger (tested). | LIFECYCLE EXCEPTION |
| EX-06 | Immutability | `updated_at` remains writable | ORM bookkeeping only; carries no execution fact. | LIFECYCLE EXCEPTION |
| EX-07 | Deletion | Execution rows cannot be deleted except by tenant offboarding (organization delete) | No other sanctioned deletion path exists; a future retention purge must be added deliberately. | DESIGN |
| EX-08 | Arc "two parents rejected" test | Structurally unrepresentable | Only Visibility invokes a model; the arc has one column. The cardinality CHECK is written over the arc so it binds when a second domain is added. | DESIGN |
| EX-09 | Visibility platform | Model-backed probes serve `platform=other` only | `visibility_platform` (native enum) has no Claude value; observing Claude must not be recorded as ChatGPT/Gemini. | DESIGN |
| EX-10 | Provider cost visibility | Visible to tenant OWNER/ADMIN only; other roles get `provider_cost_visible=false` | Billing design: provider (wholesale) cost is admin-only. No platform-admin role exists in the codebase; none was invented. Cost sort removed from the list API so ordering cannot leak it. | SECURITY |
| EX-11 | VisibilityTest.estimated_cost | NULL for model-backed observations | Cost lives once, on AIExecution; copying it would duplicate the fact and expose it to all roles via the visibility API. | DESIGN |
| EX-12 | Stale cleanup "production automatic" | Scheduled via Celery beat (`AI_EXECUTION_RECLAIM_INTERVAL_SECONDS`); docker-compose now defines `worker` and `beat` | Beat + worker verified live in this sandbox; the compose file itself could not be run (no Docker) — YAML validated only. | ENVIRONMENT_BLOCKED (compose run) |
| EX-13 | Real provider call | Not executed | No credential in this environment; none invented. | BLOCKED_EXTERNAL_DEPENDENCY |
| EX-14 | Browser dashboard is the visual-harness | The AI Executions screen is the harness's only live (API-backed) screen; all other harness screens remain fixture prototypes | Phase 17 §49: minimum operational surface only; wiring the rest of the dashboard is the pre-existing Phase 14 dashboard-integration gap, not Phase 17. | SCOPE |
