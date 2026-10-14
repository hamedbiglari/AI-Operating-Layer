# AI Usage & Cost Model (REQ-AIC-007/010/012)

## Per-account telemetry (what the system stores after each execution)
remaining_requests, remaining_tokens, quota_reset_at, last_used_at, failure_count, health_status.
These come from provider response headers / error bodies when available.
Unknown values stay NULL — never set to 0.

## Provider cost on AIExecution
estimated_provider_cost (from pricing config × input+output tokens) and
actual_provider_cost (from provider response if available) are stored on ai_executions.
The two are never conflated. Unknown cost stays NULL.

## Cost gate (REQ-AIC-012)
ai_jobs.max_cost_per_job: before each item a worst-case estimate (max tokens × price) is
compared against remaining budget. If exceeded the job stops with status cost_limit_reached.

## Per-account spend limit
ai_provider_accounts.spend_limit + spend_limit_currency: the routing engine skips an account
if the estimated cost of the next call would exceed the limit.

## What is NOT implemented (REQ-AIC-010 — BLOCKED_EXTERNAL_DEPENDENCY)
Real-time provider usage synchronisation (polling the provider's usage API) requires API
credentials and provider-specific endpoints. No credentials exist in this environment.

## Platform AI Credits (REQ-CR-001 — NOT_ESTABLISHED)
ADR-082..084 remain PROPOSED. The architecture (BYOK + optional PLATFORM_AI_CREDITS with
separate ledger) is documented in docs/billing/BILLING_ARCHITECTURE.md but NOT implemented.
The internal ledger is separate from provider cost — these must never be merged.
