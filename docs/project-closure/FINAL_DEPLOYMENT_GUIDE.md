# FINAL DEPLOYMENT GUIDE

## Components
Cloud Core (FastAPI, Python 3.12) · PostgreSQL 16 + pgvector · Redis 7 · Celery worker (same codebase) · WordPress plugin
(PHP 8.x, WooCommerce optional) · Dashboard (static HTML; serve over HTTPS on an origin listed in CORS_ALLOWED_ORIGINS).

## 1. Database
`CREATE DATABASE aiol; CREATE EXTENSION vector;` then `cd cloud-core && alembic upgrade head` → `0026 (head)`.
Verify reversibility on a staging copy: `bash scripts/verify_migration_cycle.sh`.

## 2. Configuration (`cloud-core/.env`, never commit)
Required: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY` (JWT), `AI_CREDENTIAL_KEY` (Fernet key — separate from SECRET_KEY; rotating
it makes stored provider credentials unreadable), `CORS_ALLOWED_ORIGINS`, `APP_ENV=production`, `APP_DEBUG=false`.
Optional, each unlocking one BLOCKED item: `ANTHROPIC_API_KEY` (+ `AI_MODEL_PRICING_JSON`), SMTP settings (login codes),
Google OAuth (sign-in; GSC/GA4 connectors), `RESEARCH_CONTACT_EMAIL` / `NCBI_API_KEY`, `WALRUS_*`,
`PAYMENT_PROVIDER` + `PAYMENT_WEBHOOK_SECRET` (**never `sandbox` in production** — it credits without real money),
`TRUSTED_PROXY_HOPS` (entries your own load balancer adds to X-Forwarded-For). `TEST_PROVIDER_ENABLED` must stay unset.

## 3. Processes
`uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers` behind TLS ·
`celery -A app.workers.celery_app worker --concurrency=4` · `celery -A app.workers.celery_app beat` (stale-execution reclaim).
The SSE endpoint needs response buffering disabled at the proxy (`X-Accel-Buffering: no` is sent; for nginx also `proxy_buffering off` on `/api/v1/ai-center/jobs/`).

## 4. Network egress
Allow HTTPS to api.crossref.org, eutils.ncbi.nlm.nih.gov, www.ebi.ac.uk (research), the AI provider API, the payment
provider, and open-access hosts used for full-text acquisition. Everything else can stay closed; the fetchers refuse private,
loopback and metadata addresses regardless.

## 5. WordPress plugin
Upload `wordpress-plugin` as a plugin, activate, connect with an installation credential from the dashboard.

## 6. Smoke test after deploy
`GET /api/v1/health` → ok · log in with an email code · Dashboard connect → panels show LIVE DATA · Payment screen shows the
configured provider or BLOCKED · run PILOT_TEST_RUNBOOK.md.

## 7. Backups and security
Daily PostgreSQL backups (the ledger and AI executions are append-only records — restore, never edit) · rotate SECRET_KEY per
policy, AI_CREDENTIAL_KEY only with re-entry of provider credentials · keep `/docs` and `/openapi.json` disabled or authenticated in production.
