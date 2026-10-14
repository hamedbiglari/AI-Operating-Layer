# FINAL EXTERNAL DEPENDENCY MATRIX (2026-09-29)

For each dependency: the code exists, configuration exists, validation and error handling exist, the UI
shows an honest state, and tests cover the path with a deterministic adapter. What is missing is the
credential or the service itself. Status stays BLOCKED_EXTERNAL_DEPENDENCY until connected and verified.

| Dependency | What is implemented | Test adapter used | UI state when absent | Exactly what is missing | How to activate |
|---|---|---|---|---|---|
| Commercial AI provider (Anthropic / OpenAI / Google) | provider registry, encrypted accounts, model registry, six routing modes, job runner, cost recording, fallback, quota handling | `TEST_PROVIDER` (deterministic, dev-only) | AI Center shows the provider without a credential; tasks report BLOCKED | an API key and its pricing | add the account in AI Center › Accounts, paste the key, press Test; set `AI_MODEL_PRICING_JSON` for cost |
| SMTP (login and sign-up codes) | code generation, HMAC storage, expiry, attempt limits, throttling, delivery interface | in-memory mailbox in tests | sign-in and sign-up return 503 "email delivery is not configured" | SMTP host, port, credentials, sender | set `SMTP_*` in `.env`, restart, request a code |
| Google OAuth (sign-in) | button, redirect handling, account linking | — | button visible, backend returns not configured | OAuth client id and secret | create the client, set `GOOGLE_OAUTH_*`, add the redirect URI |
| Google Search Console | connector, CSV import path, demand signal ingestion | CSV fixture import (works today) | Traffic screen shows BLOCKED for live pull | OAuth consent + property access | connect in Settings › Connections |
| Google Analytics 4 | connector, property selection, metric pull | — | BLOCKED | OAuth + property id | same |
| Payment provider | intent, idempotency, signed webhook, replay protection, amount/currency checks, ledger credit | `sandbox` provider (dev-only) | Wallet shows BLOCKED EXTERNAL DEPENDENCY, top-up disabled | a merchant account and webhook secret | set `PAYMENT_PROVIDER` + `PAYMENT_WEBHOOK_SECRET`, register the webhook URL |
| Live scholarly APIs (Crossref, NCBI, Europe PMC) | real HTTP clients, per-provider failure isolation, DOI→PMID→title dedup, polite headers | documented-format fixtures | each provider's failure shown separately in the research console | outbound HTTPS to the three hosts (blocked by this sandbox's allow-list) | run on a network with egress; set `RESEARCH_CONTACT_EMAIL`, optionally `NCBI_API_KEY` |
| ClinicalTrials.gov | **not implemented** — the provider interface exists, the adapter does not | — | not offered | an adapter | write one against the provider interface |
| Scopus / Web of Science | **not implemented** (licensed) | — | not offered | a licence and an adapter | — |
| Configurable web search | interface exists; no adapter configured | — | run reports `web: not_configured` | a search API key and adapter | — |
| Walrus (object storage) | client, boundary, honest DISCONNECTED state | local storage | DISCONNECTED | endpoint + credentials | set `WALRUS_*` |
| Docker / docker-compose | compose file maintained | — | — | a Docker daemon (absent in this sandbox) | `docker compose up` on the target host |

**Not blocked by anything external:** database, Redis, Celery worker, WordPress/WooCommerce integration,
the research engine's own logic, evidence and conflict handling, memory, wallet accounting, dashboard.
