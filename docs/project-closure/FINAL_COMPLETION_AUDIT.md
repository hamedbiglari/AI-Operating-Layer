# FINAL COMPLETION AUDIT — AI Operating Layer

Date: 2026-10-13 · Scope: full repository · Method: repository inspection plus executable evidence
(test runs, migration cycle, browser checks). Every status below is backed by something that was run,
not by the existence of a file.

**Executive verdict: CONDITIONAL PASS** *(re-stated after three fixes; see §3)* — ready for a controlled pilot with a named operator, not for
unattended production. The internal platform is coherent and tested end to end; three external
dependencies are unconfigured and one capability (the WordPress plugin) could not be re-verified in this
environment. These are listed explicitly in §8 and §24.

---

## 1. Architecture summary

Website / ecommerce → adapter → knowledge platform → storage → agent/API layer → search, AI, agents, commerce.

Implemented as:

| Layer | Where | Evidence |
|---|---|---|
| Cloud Core | `cloud-core/app` — 66 models, 67 services, 40 API route modules | import of `app.main` succeeds; 1219 tests collected |
| Storage | PostgreSQL 16 + pgvector, 36 migrations | `scripts/verify_migration_cycle.sh` → base → head → base → head, exit 0, head `0036` |
| Dashboard | `visual-harness/index.html`, 44 screens, single file | `visual-harness/check.js` → 33/33 rules pass |
| Public website | `website/` — 13 pages × 2 languages | axe-core WCAG 2 A/AA: 0 violations across 26 pages; CLS 0 |
| WordPress adapter | `wordpress-plugin/` — 38 PHP files, 13 test files | **not re-run**: PHP is absent from this environment (§8) |

WordPress is an adapter, not the intelligence layer: the knowledge, evidence, research and graph services
live in `cloud-core/app/services` and are reachable without it.

## 2. Requirement matrix

Status key: **PASS** (UI + API + logic + DB + tests + integration), **PARTIAL**, **BACKEND-ONLY**,
**BLOCKED** (external credential), **FAIL**.

| § | Requirement | Status | Evidence |
|---|---|---|---|
| 3.1 | Knowledge engine pipeline (ingest → parse → chunk → extract → resolve → graph → review → publish) | PASS | `app/ingestion/`, `app/services/knowledge_*`; converter raises `NotImplementedError` only for unsupported MIME types, which is correct refusal, not a stub |
| 3.2 | Universal knowledge object with dynamic sections | PASS | `app/models/knowledge_object.py`, `knowledge_schema_service.py`; category schemas applied per topic |
| 3.3 | Master topic matrix, recalculable coverage | PASS | `knowledge_schema_service.py`, `coverage_service.py`; dashboard `screen-matrix`, `screen-coverage`; `tests/test_coverage_audit.py` |
| 3.4 | Knowledge gaps with actions | PASS | `app/services/gap_*`; gap types and actions enumerated in `app/models/enums.py` |
| 3.5 | Universal research engine, multi-keyword, rerun | PASS | `federated_research_service.py`; Crossref, PubMed, Europe PMC adapters in `app/integrations/research/` |
| 3.6 | Source access depth, never claim full text | PASS | `enums.py` access states incl. `PAYWALLED`, `ABSTRACT_ONLY`; migration `0028_source_access_states` |
| 3.7 | Evidence synthesis, strength ≠ extraction confidence | PASS | `tests/test_memory_center_conflicts.py` covers the distinction |
| 3.8 | Compound → indirect evidence, never upgraded | PASS | **database CHECK** `ck_evidence_compound_route_is_indirect` in migration `0029`; not merely application logic |
| 3.9 | Claim/evidence/provenance graph, citation dependence | PASS | `0030_dependency_saturation`; independent findings counted, not papers |
| 3.10 | Conflict intelligence, never silently merged | PASS | `0031_confidence_conflicts`; conflict states enumerated |
| 4 | AI Center, provider abstraction | PASS *(completed in this pass)* | adapter interface `base.py`; **two adapters**: `anthropic.py` and `openai.py`, each self-registering. Routing policies are now editable by an admin (ADR-120) and provider fallback is tested across both (ADR-121). Google and local models remain unimplemented, by choice, not by gap |
| 5 | Wallet, reserve → settle/release, immutable ledger | PASS | `billing_service.py`; `tests/test_billing_wallet.py` |
| 6, 25 | Live job execution, real backend progress | PASS | SSE at `app/api/v1/ai_center.py:618`, `media_type="text/event-stream"`, streams until terminal state |
| 7, 22 | Central memory, export incl. **Markdown** | PASS *(fixed in this pass)* | was json/jsonl/csv/zip only; `md` added — see §3 below |
| 8 | Document normalization, originals preserved | PASS | `app/ingestion/`; checksum, MIME, provenance retained |
| 9, 10 | Research centre and keyword workbench UI | PASS | dashboard `screen-research`, `screen-sources`, `screen-gap` |
| 11 | Public knowledge website | PASS | 26 pages, 0 axe violations, CLS 0, works without JavaScript |
| 12 | Dashboard IA | PASS | 44 screens under a single shell and one connection |
| 13 | Data truth labelling | PASS | 13 "Not connected to Cloud Core" notices; demo panels carry DEMO/EXAMPLE labels |
| 14 | Auth, tenancy, contract agreement | PASS | passwordless sign-up by 6-digit code in `auth.py`, matching the dashboard's `screen-signup`/`screen-login-code`; 9 tenant-isolation test files |
| 15 | Traffic classification, observed ≠ inferred | PASS | `actor_signatures.py`; six real classes only; the website states the distinction |
| 16 | AI/agent access policies that affect requests | PASS | `access_policy_service.py` |
| 17 | Discovery and demand intelligence | PASS | `demand_service.py`, `ai_discovery_seed.py` |
| 18 | Commerce loop | PASS | `commerce_sync_service.py`; WooCommerce price/stock sync |
| 19 | WordPress plugin contract | **UNVERIFIED THIS PASS** | 38 PHP files, 13 test files present and unchanged; **PHP is not installed here**, so the 221 plugin tests could not be re-run |
| 20 | API contract, no orphan features | PASS | every dashboard screen that reads live data calls a route that exists |
| 21 | Security | PASS | SSRF guard `app/ingestion/url_source.py` (`_is_forbidden_ip`, blocks loopback, link-local, private, carrier-grade NAT and cloud metadata); HMAC webhook signatures `billing_service.py:177`; `tests/test_url_ingestion_security.py`, `test_security.py` |
| 23 | Real AI provider, no fake success | PARTIAL / BLOCKED | two real adapters exist and are MOCK_VERIFIED; `test_provider.py` remains for automated tests only. **No production key is configured for either provider**, so live AI execution is still BLOCKED |
| 24 | Billing independent of gateway | PARTIAL | wallet and ledger work; **no payment gateway configured** |
| 26 | Observability | PASS | audit log records action, actor, tenant, resource; memory export is audit-logged |
| 27 | Test layers | PASS | unit, service, API, DB, migration cycle, integration, security, tenant isolation; browser checks for the website and dashboard |
| 28 | Taranjabin real-data path | PASS | used as the worked example through evidence, graph and publication, with the mannitol relation kept indirect |

## 3. What this audit changed

Three gaps were found and fixed rather than documented.

### (a) Routing policies could not be edited from the dashboard (ADR-120)
The schema carried everything needed to choose providers and order them, but the API offered only `POST` and
`GET`, and the dashboard said on screen: "Create one through the API". By this project's own standard that is
BACKEND-ONLY. Added `GET`, `PATCH`, `DELETE` for a policy and `POST`, `PATCH`, `DELETE`, `/move` for its steps,
with one shared validator so a policy can never be edited into a shape it could not have been created in, and
gapless `position` renumbering. The dashboard's Routing tab now has a create form and, per policy, rename, mode
change, ceiling removal, delete, and per step move up / move down / remove plus an add-step form.
**Evidence:** 6 tests, plus a browser run against a live backend — created a policy, added a second step, moved
it up, and confirmed the stored order `[(0, 'model-backup'), (1, 'model-primary')]` with no console errors.

### (b) Only one provider adapter existed (ADR-121)
`priority_pool` and `PROVIDER_FALLBACK` had nowhere to fall back to. Added `app/integrations/llm/openai.py`
behind the same contract. **Evidence:** 26 adapter tests and 4 two-provider tests, including Anthropic failing
over to OpenAI with each attempt its own execution chained by `previous_execution_id` and marked
`PROVIDER_FALLBACK`.

### (c) Memory export had no Markdown format (ADR-119)

**Memory export had no Markdown format** (§7 and §22 require it). `EXPORT_FORMATS` offered json, jsonl,
csv and zip only.

- `app/services/memory_center_service.py` — `md` added to `EXPORT_FORMATS`; `_markdown()` renders a readable
  document: header naming PostgreSQL as the canonical store, scope, record counts, the no-credential
  statement, then every working-memory record with kind, job key, version, record id, creation time and any
  provenance, source or checksum, its content as nested bullets (long strings as fenced blocks), then memory
  profiles and agent handoffs. Empty sections say so.
- Binary assets are **not** converted: a record pointing at one keeps its reference, checksum and provenance;
  JSON/JSONL/ZIP remain the lossless copy. This follows §7's warning against pretending binaries become Markdown.
- The ZIP now also carries `memory.md`.
- `app/api/v1/memory_center.py` — `export.md` accepted.
- Dashboard — Memory Center gains a Markdown download button.
- Tests — 2 added (readability and provenance, with the zip carrying the same Markdown; admin-only and tenant
  isolation), existing zip file-list assertion updated. ADR-119 recorded.

## 4. Test results

| Suite | Result |
|---|---|
| Backend at the start of this audit | 1217 / 1217 passed, 0 failed, 0 skipped |
| Backend after all three fixes | **1255 / 1255 passed**, 0 failed, 0 skipped (six chunks: 186 + 172 + 214 + 186 + 286 + 211) |
| Tests added in this pass | 38 (2 memory export, 6 routing policy editing, 26 OpenAI adapter, 4 two-provider failover) |
| Migration up → down → up | exit 0, head `0036` |
| Dashboard rules | 33 / 33 |
| Website accessibility (axe-core WCAG 2 A/AA) | 0 violations across 26 pages, both themes |
| Website layout stability | CLS 0 at 320–1920 px, both languages |
| Website without JavaScript | 1029 text blocks checked, 0 hidden |
| WordPress plugin (PHP) | **not re-run** — PHP absent from this environment |

## 5. Honest status of the four non-PASS items

1. **AI provider (§4, §23) — BLOCKED, no longer PARTIAL in design.** Two adapters now exist (Anthropic and
   OpenAI), an admin can order them in a routing policy from the dashboard, and failover between them is
   tested. What remains blocked is only the credential: with no production key for either provider, no live
   call has ever been made. Both adapters are **MOCK_VERIFIED** — real httpx, real request building, real
   response parsing, real error mapping, against a mock transport. That is not evidence of a live call.
2. **Payment gateway (§24) — BLOCKED.** The internal wallet, ledger, reservation and settlement work and are
   tested. No gateway credentials exist, so purchase, webhook verification and reconciliation are unproven
   against a live provider.
3. **WordPress plugin (§19) — UNVERIFIED THIS PASS.** The code and its 13 test files are present and were not
   modified. PHP is not installed in this environment, so the previously recorded 221 passing tests could not
   be re-confirmed today. Treat the plugin as untested until that suite is run on a machine with PHP.
4. **Search Console / analytics connections (§9 in the dashboard IA) — BLOCKED.** No OAuth credentials.

## 6. Remaining risks (highest first)

1. Plugin ↔ cloud contract unverified in this pass (PHP unavailable).
2. Neither provider has ever been called with a real credential; failover is proven only against a mock transport.
3. No live payment path; billing is internal-only.
4. No production load testing; SSE behaviour under many concurrent jobs is untested at scale.
5. The public website's canonical domain is still a placeholder.
6. No live-fire test against a real scholarly API rate limit.
7. Research depends on three external APIs whose availability is outside the system.
8. No backup/restore drill recorded.
9. No staging environment verified in this pass.
10. Persian edition reviewed for layout and accessibility, not copy-edited by a native reviewer.

## 7. Exact external credentials still required

| Need | For |
|---|---|
| Anthropic API key | AI execution, research extraction, publication generation |
| Payment gateway credentials | credit purchase, webhooks, reconciliation |
| Google Search Console OAuth | imported demand data |
| A real domain and TLS certificate | canonical URLs, structured data, service worker |
| SMTP credentials | sign-up codes, newsletter delivery |

## 8. Deployment sequence

1. Provision PostgreSQL 16 with pgvector and Redis.
2. Set `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `CORS_ALLOWED_ORIGINS`.
3. `alembic upgrade head` (expect `0036`).
4. Run the backend test suite against the deployed database.
5. Start the API; confirm `/health`.
6. Serve `website/` statically; set `api` and `org` in `assets/js/site-config.js`.
7. Serve `dashboard/index.html`; connect it from the Dashboard or AI Center screen.
8. Install the WordPress plugin on the pilot site and run its PHP tests **before** trusting the contract.
9. Configure the Anthropic key in AI Center; confirm the connection test.
10. Leave billing BLOCKED until a gateway is configured.

## 9. Known limitations

- Two AI providers implemented (Anthropic, OpenAI); neither verified against a live API.
- No live payment path.
- Plugin suite unverified in this environment.
- The website's hero sphere and demo need JavaScript; all text does not.
- The research engine reports failure rather than saturation when every provider fails — correct, but it means
  provider outages surface as errors to the user.
