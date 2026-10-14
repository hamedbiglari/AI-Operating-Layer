# ADR: Manual Retry (P14-CORRECTION-001)

## Classification
`PHASE14_REQUIREMENT_GAP_DISCOVERED_IN_PHASE15`. The Phase 14 master
prompt (Section 18, Processing Center) explicitly required real
controls including "Retry, Retry failed" — this was never implemented.
Not a Phase-15-only gap; it was owed by Phase 14 and missed.

## Decision: Model A
Same `job_id`. `attempts` keeps counting from wherever automatic retry
left off. No new job/execution row.

## Why, not a third model
`SyncJob.attempts`, `MAX_ATTEMPTS`, and the documented state machine
(`QUEUED -> RUNNING -> SUCCEEDED | RETRYING -> ... | FAILED`) are all
built around one persistent row per logical ingestion. A second row per
retry would fork that history and break the 1:1
`idempotency_key -> job` relationship `create_url_ingestion_job` already
depends on. Model B was rejected for this reason, not by preference.

## Eligibility
Only `FAILED` or `DEAD_LETTER` jobs may be retried. `409 CONFLICT`
otherwise (RUNNING/QUEUED/RETRYING/SUCCEEDED/CANCELLED all rejected,
each with the job's real current status in the message).

## Idempotency
Retry transitions the job to `QUEUED` and dispatches to Celery exactly
once per FAILED->QUEUED transition. A repeated `POST .../retry` against
a job that already left the eligible-state set (because the first call
already moved it to QUEUED) returns the current job unchanged and does
not dispatch again — verified at the DB level in
`docs/phase15/runtime-evidence/p14-correction-001/`.

## Failure history
`error_message` is deliberately NOT cleared on retry — it is left as-is
until the next real outcome (`succeed()` or `fail()`) overwrites it, so
the dashboard can show the original failure alongside the retry attempt
in progress, not a blank slate.

## Security
Enforced identically to job creation: `require_roles(*KNOWLEDGE_EDITOR_ROLES)`
plus tenant-scoped lookup (`WHERE organization_id = caller's own`) inside
the service function itself — a foreign-tenant job and a nonexistent job
both return `404`, with no distinguishing signal.

## Cost safety
This job type (`documents.ingest`) does not call a billable AI provider;
it re-enters the same worker path (`ingest_document_job` ->
`run_ingestion_job`) that budget/cost accounting already governs for the
original submission. No new bypass surface introduced.
