# FINAL PILOT CHECKLIST (2026-09-29)

Tick on the pilot host. Anything unticked stays unticked in the report — do not tick from documentation.

## A. Install
- [ ] PostgreSQL 16 + pgvector, Redis 7, Python 3.12 present
- [ ] `.env` filled: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `AI_CREDENTIAL_KEY`, `CORS_ALLOWED_ORIGINS`, `APP_ENV=production`, `APP_DEBUG=false`
- [ ] `alembic upgrade head` → `0032 (head)`
- [ ] `bash scripts/verify_migration_cycle.sh` → verified
- [ ] `pytest -q` → 1161 passed, 0 failed, 0 skipped
- [ ] `bash wordpress-plugin/tests/run.sh` → ALL PHP CHECKS PASSED
- [ ] uvicorn + `celery worker` + `celery beat` running behind TLS; SSE not buffered by the proxy
- [ ] Dashboard served over HTTPS from an origin in `CORS_ALLOWED_ORIGINS`
- [ ] `PAYMENT_PROVIDER` is **not** `sandbox`

## B. First run
- [ ] Sign up with an email code (no password anywhere)
- [ ] Dashboard panels show LIVE DATA after connecting
- [ ] AI Center: add a provider account, paste the key, Test → healthy
- [ ] Task routing: pick the model for research and extraction, save
- [ ] Wallet: shows the configured provider, or BLOCKED if none

## C. Research on a real product
- [ ] Knowledge object with primary keyword, scientific name, synonyms, compounds, outcome
- [ ] Save a query set and run it → providers ok, sources found
- [ ] Re-run → 0 new sources
- [ ] Open a source → access state honest, acquisition links work
- [ ] Obtain one article legally, upload it → "Full text acquired"; a landing page → "not attached"
- [ ] Research question with two compounds and a related species → all routes searched separately
- [ ] Approve a compound study stating the compound → stays **indirect**
- [ ] Approve a subject study → **direct**; graph shows 1 direct path
- [ ] Record a dependency between a review and its trial → independent count drops
- [ ] Saturation panel states a real reason
- [ ] Link supporting + contradicting evidence to a claim → conflict appears; resolving requires a reason
- [ ] Create a completion task; the wrong evidence is refused

## D. Live progress, memory, commerce
- [ ] Run a job → live line moves without refreshing; pause / resume / cancel work
- [ ] Memory Center: search, compare two versions, export ZIP
- [ ] WordPress plugin connected → content and commerce mappings sync
- [ ] Offer price and stock correct; `/ai/ask` returns the merchant URL; cart and an unpaid order created

## E. Security spot checks
- [ ] A second tenant sees none of the above (404s, empty lists)
- [ ] A viewer cannot export memory or move money
- [ ] Provider credential never appears in any API response or log
- [ ] Replay a payment webhook → acknowledged, credited once

## F. Sign-off
- [ ] Record the date, the host, the migration head, and the test counts
- [ ] Any unticked box is listed in the final report as remaining work
