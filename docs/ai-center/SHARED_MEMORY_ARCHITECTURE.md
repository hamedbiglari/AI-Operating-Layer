# Shared AI Working Memory & Job Architecture (ADR-089/090, REQ-AIC-004/005)

## Purpose
Survive provider limits and AI switching without losing intermediate findings.
The next AI must not start from zero.

## DB tables

| Table | Purpose |
|---|---|
| `ai_jobs` | Business parent of executions. job_key (tenant-unique), goal, policy, stage, status, stop_reason, max_cost. |
| `ai_job_items` | One row per document/item. Status: pending / completed / failed. Records which account completed each item and why failures occurred. |
| `ai_working_memory` | Memory items: JOB_STATE, AI_HANDOFF, INTERMEDIATE_FINDING, OPEN_QUESTION, CURRENT_SYNTHESIS, NEXT_ACTION, CONFLICT_CONTEXT, PROCESSING_CHECKPOINT, AI_SUMMARY. Versioned (append-only — a new version row per update). Provenance: created_by user, linked execution id. |

## Job lifecycle

```
create_job → items loaded as pending
     ↓
run_job → route to account A → execute items
     ↓ (account stops: quota / rate limit / auth / timeout / manual)
CHECKPOINT persisted (PROCESSING_CHECKPOINT memory item)
HANDOFF package persisted (AI_HANDOFF memory item)
     ↓
switch to account B → load handoff → resume pending items
     ↓
completed items never re-processed
```

## Handoff package contents
goal, current_stage, completed_items, pending_items, failed_items, processed_count,
total_count, progress_percent, findings, claims, evidence_refs, source_refs, conflicts,
knowledge_gaps, current_synthesis, next_actions, previous_executions, last_provider,
last_model, failure_reason, checkpoint_time.

## Idempotency
`UNIQUE (organization_id, job_key)` on jobs. `UNIQUE (organization_id, job_id, kind, version)`
on memory items.

## AIExecution arc
`ai_executions.ai_job_id` joins the arc (two arc columns now: visibility_run_id and ai_job_id).
The cardinality CHECK rejects two parents simultaneously.

## Controls
`POST /ai-center/jobs/{key}/control` with action: pause / resume / cancel / retry_failed /
switch_resource (requires new_account_id) — each creates an auditable event.
