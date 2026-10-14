# AIExecution Integration (ADR-091/093, REQ-AIC-007)

## Phase 16 lock preserved
HYBRID_CANONICAL_EXECUTION is unchanged:
- One real AI model invocation = one AIExecution
- Retry = new AIExecution (previous_execution_id set)
- Fallback = new AIExecution
- AIExecution is canonical; domain tables reference it, never the reverse

## Additions in migration 0020 (additive, no 0017/0018 change)

### provider_account_id
Nullable composite FK to ai_provider_accounts (id, organization_id).
ON DELETE SET NULL (column) — if the account is deleted, this column clears.
Creation fact: immutable once the execution row is created (trigger enforcement).

### ai_job_id
Second arc column. `ai_executions` now has two possible parents:
- visibility_run_id (Phase 12 domain parent)
- ai_job_id (AI Center batch job parent)
The exclusivity CHECK and the require-parent trigger cover both.
Exactly one of the two must be non-null on INSERT.

### stop_reason
Outcome fact: set during finalisation, frozen once terminal.
Vocabulary (27 values): COMPLETED, TOKEN_LIMIT, CONTEXT_LIMIT, RATE_LIMIT, QUOTA_EXHAUSTED,
SPEND_LIMIT, AUTHENTICATION_FAILED, AUTHORIZATION_FAILED, CREDENTIAL_EXPIRED,
PROVIDER_UNAVAILABLE, PROVIDER_TIMEOUT, PROVIDER_INTERNAL_ERROR, NETWORK_TIMEOUT,
DNS_ERROR, TLS_ERROR, CONNECTION_RESET, SAFETY_BLOCKED, CONTENT_BLOCKED,
USER_CANCELLED, SYSTEM_CANCELLED, COST_LIMIT, HANDOFF, MANUAL_SWITCH,
STALE_RUNNING_RECLAIMED, BUDGET_BLOCKED, NOT_CONFIGURED, UNKNOWN.

## Distinct logs
AIExecution log ≠ Audit log ≠ Operational log ≠ Security log ≠ Memory log ≠ Billing log.
Raw prompts/responses are NOT stored on the AIExecution row (references/hashes only).
