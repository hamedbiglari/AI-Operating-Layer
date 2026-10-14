# Phase 17 — Project Memory Update

## Facts now true (verified)
- `ai_executions` (0017, hardened by 0018) is the canonical record of every real AI-model invocation. One provider call = one row; retries and fallbacks are new rows linked by `previous_execution_id` + `attempt_reason`.
- Rows are written only by `app/ai/invocation.py`; adapters refuse to call a provider without a persisted RUNNING row. Provider HTTP exists only under `app/integrations/llm/`.
- DB-enforced immutability: creation facts frozen from insert; outcome facts frozen once terminal; link columns change only via ON DELETE SET NULL of a deleted target; rows cannot be deleted except by tenant offboarding.
- Cost: `estimated_provider_cost` from configured prices × reported tokens; NULL = unknown; `actual_provider_cost` only if the provider reports it. Provider cost is visible to tenant OWNER/ADMIN only. `VisibilityTest.estimated_cost` is NULL for model-backed observations.
- Visibility is the only domain with a model path (platform `other`). Research and SyncJob make no model calls.
- Stale RUNNING rows are reclaimed as `abandoned` by Celery beat (`ai_executions.reclaim_stale`).
- CORS is closed unless `CORS_ALLOWED_ORIGINS` lists exact origins (GET only).
- The dashboard has one live screen, "AI executions", reading the real API; everything else in the harness is still fixture.

## Still not true
- No real provider call has ever been made (no credential).
- `Base.metadata.create_all` fails on a fresh DB (pre-existing, `ai_agents`); tests must use an alembic-built DB.
- Six pre-existing test failures remain (Phase 13 telemetry/access/sorting).

## Decisions confirmed or taken
- Phase 16 architecture C unchanged. Exceptions recorded in PHASE17_EXCEPTION_REGISTER.md (EX-01..EX-14).
- No platform-admin role exists; "admin-only" means tenant OWNER/ADMIN.

## Operational requirements
- Run exactly one `celery beat` per deployment alongside the worker.
- To make the provider live: set `ANTHROPIC_API_KEY` and `AI_MODEL_PRICING_JSON`.
