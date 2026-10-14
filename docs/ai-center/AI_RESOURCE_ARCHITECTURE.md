# AI Resource Architecture (ADR-087, REQ-AIC-001/002)

## Core separation

```
Provider   — the organisation / API service (e.g. "Anthropic", "Google", "Mistral AI")
Account    — a specific credential set for that provider (e.g. "Prod account A",
             "Research account B") — fully independent usage, health, quota, spend limits.
Model      — registered per provider, not hard-coded; dynamic registry (REQ-AIC-012).
```

Nothing in these three tables is shared across tenants.  Every row carries `organization_id`.

## DB tables (migration 0020)

| Table | Purpose |
|---|---|
| `ai_providers` | Name, canonical name, API base URL, documentation, adapter key (which invocation adapter handles calls), credential method, verification status. |
| `ai_provider_accounts` | One per credential set. Credential ciphertext (Fernet-encrypted; never returned raw). Health status + last check. Failure count. Remaining requests/tokens, quota reset time, spend limit + currency. |
| `ai_models` | Model id string, capabilities, context window, modalities. Not hard-coded. |
| `ai_health_events` | Historical health observations per account. |

## Credentials (ADR-088)
Fernet (AES-128-CBC + HMAC-SHA256) keyed by `AI_CREDENTIAL_KEY` (separate from JWT key).
Without the key the API refuses the write (never stores in clear).
Only a fingerprint (last-4) and boolean `credential_set` are returned.

## AIExecution attribution (ADR-093 / REQ-AIC-007)
`ai_executions.provider_account_id` (nullable composite FK, ON DELETE SET NULL on the column) records which account served each call. Column is a creation fact (immutable once set) and participates in the exclusive arc enforced by the trigger.

## Tenant isolation
Every query is filtered by `organization_id`. Composite FK constraints prevent cross-tenant references at the database level.
