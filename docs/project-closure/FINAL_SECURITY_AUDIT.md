# FINAL SECURITY AUDIT (2026-09-29, migrations 0001→0032)

Method: read the code path for each item, then run the test that proves it. "Verified" means an executed
test asserts the behaviour; nothing here is claimed from documentation.

| # | Area | Finding | Where it is enforced | Test |
|---|---|---|---|---|
| 1 | SSRF | Every outbound fetch resolves the host first and refuses private, loopback, link-local and metadata addresses, non-http(s) schemes, and redirects that land on a blocked address. Scholarly providers may only reach three fixed official hosts. Full-text acquisition accepts only a URL already recorded as an open-access location of that source. | `app/ingestion/url_source.py`, `integrations/research/scholarly.py`, `federated_research_service.acquire_full_text` | `test_url_ingestion_security`, `test_providers_only_reach_fixed_official_hosts`, `test_acquisition_only_from_recorded_open_access_locations`, `test_acquisition_passes_through_the_ssrf_guard` |
| 2 | Credential encryption | Provider credentials are Fernet-encrypted with a key separate from the JWT secret, never returned by any endpoint, never logged, and shown only as the last four characters. | `security/credential_crypto.py`, `api/v1/ai_center.py` | `test_ai_center` (credential write-only + masked) |
| 3 | Authorization | Role checks on every mutating route; money-moving and export routes require owner/admin; viewers may read. | `security/dependencies.py` | `test_money_moving_endpoints_need_an_admin`, `test_memory_is_tenant_isolated_and_export_is_admin_only` |
| 4 | Tenant isolation | Every query is scoped by `organization_id`; cross-tenant reads return 404, never 403 (no existence leak). Verified for research, evidence, conflicts, completion tasks, memory, wallet, jobs, sources and the live WordPress loop. | all routers | ~40 isolation tests + live `e2e_tenant.py` (all 404, no leak) |
| 5 | API token isolation | Installation credentials are per tenant and hashed; a token from one tenant cannot read another's data. | `security/installation_auth.py` | plugin + core suites |
| 6 | SSE authorization | The stream authenticates before the first byte and 404s for another tenant's job; unauthenticated requests get 401. | `api/v1/ai_center.py::job_events` | `test_sse_is_authenticated_and_tenant_scoped` |
| 7 | Export authorization | Memory export is owner/admin only, tenant-scoped, audited, and contains no credentials. | `api/v1/memory_center.py` | 2 tests |
| 8 | Payment webhook verification | HMAC-SHA256 over `timestamp.body`, ±5-minute window, constant-time compare; unsigned or forged requests are rejected. | `services/billing_service.py` | `test_webhook_credits_once_and_rejects_replays` |
| 9 | Webhook replay | A repeated provider event id is acknowledged but never credits twice; amount/currency mismatch never credits. | unique `payment_webhook_events.event_id` | 2 tests |
| 10 | Wallet race conditions | The wallet row is locked (`SELECT … FOR UPDATE`) for the whole reserve/settle/release transaction, so two concurrent reservations cannot both pass the balance check. | `billing_service.reserve/_reservation` | `test_insufficient_balance`, `test_reservation_and_settlement` |
| 11 | Idempotency | Unique `(organization_id, idempotency_key)` on payments, reservations and ledger entries; a replay returns the original row. | migration 0026 | 3 tests |
| 12 | Rate limiting | Login codes, sign-up requests (per email and per IP) and the network check are throttled with cooldown and hourly caps. | `login_code_service`, `signup_code_service`, `network_check` | `test_resend_cooldown_and_hourly_cap`, login-code tests |
| 13 | Audit logging | Registration, memory export, full-text attachment, conflict review and completion-task changes are audited with actor, resource and timestamp. | `services/audit.py` | asserted in 5 tests |
| 14 | SQL injection | No string-built SQL anywhere; every query is a SQLAlchemy construct with bound parameters. Research query terms are additionally restricted to a safe character set and are sent to providers as request parameters, never into SQL. | ORM + `federated_research_service._BOOL_TOKEN` | `test_boolean_query_validation` |
| 15 | XSS | The dashboard builds DOM nodes and sets `textContent`; no `innerHTML` with server data, no `eval`. | `visual-harness/index.html` | `check.js` rule |
| 16 | CSRF | The API is token-based (bearer), not cookie-based, so there is no ambient authority to forge; CORS is an explicit allow-list. | `main.py` | config test |
| 17 | JWT / session | Short-lived access tokens signed with `SECRET_KEY`; passwordless owners have no password hash at all and password login is refused for them. | `auth_service` | `test_signup_without_a_password` |
| 18 | IDOR | Every by-id route filters on the tenant before returning; ids are UUIDv4. | all routers | isolation tests |
| 19 | Path traversal | Uploads are stored under generated names; no user string reaches a filesystem path. | `ingestion_service` | upload tests |
| 20 | File upload validation | Extension allow-list, media-type check, size cap, and conversion in a subprocess; a file that does not parse never becomes evidence. | `ingestion_service.validate_upload` | upload + `test_an_unparsed_or_tiny_upload_claims_nothing` |
| 21 | Oversized payloads | Body size limits on upload and webhook routes (64 kB for webhooks). | `api/v1/billing.py`, ingestion | webhook test |
| 22 | Trusted proxy | `TRUSTED_PROXY_HOPS` says how many `X-Forwarded-For` entries are ours; the VPN advisory never echoes the client IP or header values. | `api/v1/network_check.py` | 4 tests |
| 23 | Secrets in output | Scanned the repository for key patterns (`sk-ant-`, `sk-`, `AKIA`, `whsec_`) before every package build: none. No secret appears in HTML, logs, API responses or the database in plaintext. | — | build-time scan |

## Residual risks (accepted, documented)
- **Browser storage:** the dashboard keeps the Cloud Core token in memory for the session only; a shared machine still exposes an open tab. Sign-out clears it.
- **`sandbox` payment provider:** credits a wallet without real money. It must never be configured in production — stated in the deployment guide and reported in the UI as SANDBOX.
- **Live provider TLS pinning:** not implemented; standard CA validation is used.
- **No pen-test:** this is a code-and-test audit, not an external penetration test.
