# Debt Register

Single source of truth for carried-forward technical debt. Every item
has a stable ID that appears in ADRs, commit messages and test names,
so "what happened to A3?" has exactly one answer.

`KNOWN_ISSUES.md` describes issues per phase in prose; this file tracks
their **lifecycle and ownership**. Where they disagree, this file wins.

Status values: `OPEN` · `CLOSED` · `DEFERRED (owner phase)` · `ACCEPTED`
(a documented design position, not a defect).

## Class A — blocking, closed in Phase 9

| ID | Item | Origin | Status | Evidence |
|----|------|--------|--------|----------|
| **A1** | No machine-client authentication existed; auth was JWT-user-only | Phase 1 gap | **CLOSED** (Phase 9) | `Installation`/`InstallationCredential`, `security/machine_identity.py`, ADR-036, `test_phase9_machine_identity.py` (22 tests) |
| **A2** | No rate limiting anywhere | Phase 0 gap | **CLOSED** (Phase 9) | `security/rate_limit.py`, ADR-039, applied to `/adapter/**` after identity resolution |
| **A3** | DB could not enforce `child.organization_id == parent.organization_id` | Phase 5, deferred twice | **CLOSED** (Phase 9) for all non-polymorphic relationships | migration `0010`, ADR-037, `test_sql_level_tenant_integrity.py` (6 tests proving SQL-level rejection) |
| **A4** | `/live` and `/ready` "need separate implementation" | Phase 0 register entry | **CLOSED — was already done in Phase 1.** Register entry was stale, not a real defect. Phase 9 extended `/ready` with Redis reporting | `api/v1/health.py` |

**A4 is recorded as a register-accuracy failure, not a code failure.** A
stale entry survived four reviews and was nearly re-implemented. That is
the reason this file exists.

## Class B — adjacent, addressed in Phase 9

| ID | Item | Status | Evidence |
|----|------|--------|----------|
| **B1** | Explicit-null PATCH semantics fixed only for Phase 7 endpoints | **DEFERRED (Phase 14)** — touches every earlier phase's update service; deserves one reviewed sweep, not a drive-by | ADR-026 |
| **B2** | `TrustSubjectType` needs a `SITE` value | **CLOSED** | `SITE` added; additive enum change |
| **B3** | `POLICY_VERSION` bumping is manual | **CLOSED** | `test_policy_version_matches_weights` |
| **B4** | Stray root files, duplicate empty `ai-context/` | **CLOSED** | removed |
| **B5** | `get_trust_summaries()` did not filter `subject_type` | **CLOSED** | `contracts/commerce.py`; PRODUCT-only filter + test |

## Class C — deferred with a named owner phase

Deferred ≠ forgotten. Each has an owner; none may be implemented early.

| ID | Item | Owner phase |
|----|------|-------------|
| C1 | WooCommerce sync (`commerce_mappings`, §40) | **Phase 10** |
| C2 | Real embedding provider (replaces deterministic placeholder) | **Phase 11** |
| C3 | Real ingestion pipeline (URL/PDF/WordPress import, §44) | **Phase 11** |
| C4 | Real `ResearchProvider` | **Phase 11** |
| C5 | CONTINUOUS research scheduler | **Phase 11** |
| C6 | Conflict-list view | **Phase 14** |
| C7 | Research-trail browse endpoint | **Phase 14** |
| C8 | Trust aggregate view | **Phase 14** |
| C9 | Recommendation feedback loop | **Phase 14** |
| C10 | `CustomerContext` retention policy | **Phase 13** (Rights) |
| C11 | Rights enforcement on adapter representations | **Phase 13** |

## Class D — accepted design positions (not debt)

Untuned recommendation weights · exact-match relevance · n-gram
clustering · simple `normalize_query()` · seed-set intent rules ·
free-text `ProductEvidence.claim` · row-level provenance · no product
DELETE · **evidence scope explicit-not-semantic (ADR-033)** · effective
verification computed not stored (ADR-032).

Each has a stated rationale in `DECISIONS.md`. Revisit only on evidence,
not on preference.

## Class E — resolved, retained for history

| Item | Resolved by |
|------|-------------|
| Excel/`.xlsx` import missing (spec deviation) | ADR-020, Phase 6 follow-up |
| `.github/` excluded from delivered ZIPs | packaging fix |
| `MASTER_SPEC.md` absent from repo | ADR-013 |
| Explicit-null PATCH on Phase 7 endpoints | ADR-026 |
| `ProductEvidence`/`TrustRecord` verifiable over rejected Evidence | ADR-032 |

## Still open after Phase 9

| ID | Item | Why not closed |
|----|------|----------------|
| **P1-poly** | Polymorphic pointers (`trust_records.subject_id`, `research_task_references.reference_id`, `wordpress_mappings.object_id`) remain service-enforced | SQL has no FK to "one of several tables". Not closeable by composite FK; would need a different subject model. |
| **P2-ratelimit-failopen** | Rate limiter fails open when Redis is unreachable | Deliberate (ADR-039): a cache outage becoming a total integration outage is the worse failure. Revisit if the cost model changes. |
| **B1** | Explicit-null PATCH across pre-Phase-7 endpoints | See above — Phase 14. |

## Phase 9 plugin — added to the register

| ID | Item | Status | Owner |
|----|------|--------|-------|
| **P9-wp-untested** | Plugin never run inside WordPress; hooks/nonces/capabilities/admin rendering unverified | ENVIRONMENT BLOCKED | needs a real WP install before release |
| **P9-visual** | No screenshots or rendered measurements (ADR-044) | ENVIRONMENT BLOCKED | harness ships in `tests/visual/` |
| **P9-woo-ambiguity** | §38 "WooCommerce hooks" vs §40/§62 Phase 10 boundary (ADR-041) | OPEN — needs a decision | product owner, before Phase 10 |
| **P9-rtl** | RTL rendering unverified (logical properties used, not rendered) | ENVIRONMENT BLOCKED | with P9-visual |
| **P9-a11y-live** | Keyboard traversal and screen-reader announcement unverified | ENVIRONMENT BLOCKED | with P9-wp-untested |

## AI Access Toolkit absorption

| ID | Item | Status |
|----|------|--------|
| **AAT-absorb** | Legacy toolkit absorbed; 23 capabilities classified | **CLOSED** — map + 42 regression tests |
| **AAT-gateway** | Parallel canonical API removed | **CLOSED** — negative test asserts no REST routes |
| **AAT-score** | Composite readiness score removed | **CLOSED** — ADR-047 |
| **AAT-privacy** | IP/URL logging removed | **CLOSED** — test greps for `REMOTE_ADDR` |
| **AAT-https** | Credentials over plaintext HTTP | **CLOSED** — ADR-045 |
| **AAT-i18n** | fa_IR catalogue | **PARTIAL** — 75 of 145 strings translated; rest fall back to English rather than ship a wrong translation |
| **AAT-agent-tool** | `AGENT_TOOL` actor type has no signatures | **OPEN** — Phase 10+, the type exists so agentic traffic has somewhere to go |

## Phase 11

| ID | Item | Status |
|----|------|--------|
| **P11-sort-rollout** | Sorting threaded through 39/41 collection routes; 2 documented exclusions | **CLOSED** — ADR-060, 25 tests, 6/6 mutations caught |
| **P11-mcp** | No MCP server; capability manifest only | **DEFERRED** by §63 (MCP = future/secondary). ADR-058 |
| **P11-ask-context** | `/ai/ask` does not accept a `customer_context_id`; it always evaluates context-free | **OPEN** — deliberate for v1 (no external party should attach to a stored customer context without a consent story) |
| **P11-cursor-pagination** | Offset pagination can still skip/repeat rows over a mutating dataset; the tiebreak fixes ordering determinism, not snapshot isolation | **OPEN** — cursor pagination not implemented |
| **MARKITDOWN** | Document normalization absent; `Document.content` accepts plain text only | **OPEN — deferred Phase 3 work.** Audit: `docs/audits/MARKITDOWN_AUDIT.md`. Not in Master Spec; needs an ADR before adoption |

## Phase 12

| ID | Item | Status |
|----|------|--------|
| **P12-providers** | No platform provider adapters; collection is manual | **OPEN** — needs credentials + terms review per platform |
| **P12-scheduler** | No scheduled monitoring worker | **OPEN** — would reuse Celery (Phase 5) |
| **P12-reconcile** | `period_spent` counter can drift from the row sum | **OPEN** — bounded by one probe |
| **P12-competitors** | No competitor tracking | **DEFERRED** — not in §31 |

## Phase 3 Document Intelligence (completed retroactively)

| ID | Item | Status | Owner |
|----|------|--------|-------|
| **P3-vision** | Level 4 vision interpretation of figures/charts not built; `vision_model` always NULL | **DEFERRED** — needs a provider + cost policy | Phase 3 follow-up |
| **P3-scanned-ocr** | Full-page OCR for scanned PDFs not built; no scanned fixture | **DEFERRED** | Phase 3 follow-up |
| **P3-original-retention** | Uploaded bytes are discarded after conversion; `storage_path` is NULL. §10 asks for the original to be preserved | **OPEN** — needs an object-store decision | Phase 3 follow-up |
| **P3-async-ingest** | Upload is synchronous; §40 wants 202 + job_id via Celery | **OPEN** — Celery exists (Phase 5) | Phase 3 follow-up |
| **P3-benchmark** | No 50/200/1000-document benchmark | **OPEN** — §19 | Phase 3 follow-up |
| **P9-plugin-canonical-md** | Plugin still renders `post_content`, not the canonical Knowledge representation (ADR-067) | **OPEN** | Phase 9 adapter |
| **P12-budget-race** | Budget is read→decide→write; §38 wants atomic reservation | **OPEN** — must be fixed before paid provider adapters | Phase 12 follow-up |

## v5 implementation

| ID | Item | Status | Owner |
|----|------|--------|-------|
| **V5-evidence-review-flag** | `POST /evidence/{id}/review` accepts any `EvidenceStatus` and `review_evidence()` always sets `human_reviewed = True`, so moving evidence *into* `pending_review` (or back to `draft`) marks it as human-reviewed although nobody has reviewed it yet. Federated research creates its candidates directly as `pending_review` with `human_reviewed = False` (`federated_research_service.py:491`), which is correct; the review endpoint is the only *manual* path into `pending_review`, and it gets the flag wrong. Claims reject non-review target statuses (`test_review_with_non_review_status_is_rejected`); evidence has no equivalent guard. Found while seeding `test_dashboard_summary.py` (2026-10-23); dashboard counts read `status` only, so they are unaffected | **OPEN** — needs a decision: restrict the review endpoint to reviewed states and add a separate submit-for-review action, or set `human_reviewed` only for `verified`/`rejected` | Evidence lifecycle |
| **V5-aiagent-model-drift** | Migration `0016` adds `uq_ai_agents_id_organization_id` (unique on `id, organization_id`), but the `AIAgent` model (`app/models/ai_agent.py`) does not declare it. The tenant-composite FKs in `access_policy.py`, `page_view.py` and `search_demand_event.py` reference that pair, so `Base.metadata.create_all()` on an empty database fails with `InvalidForeignKey: there is no unique constraint matching given keys for referenced table "ai_agents"`. The test harness (`tests/conftest.py` `db_engine`) uses `create_all()`, so every DB-backed test errors in setup on a fresh database unless `alembic upgrade head` has run first. Databases built by migrations are unaffected. Found 2026-10-23 while verifying B1 against a new local Postgres | **OPEN** — fix either way: add `UniqueConstraint("id", "organization_id", name="uq_ai_agents_id_organization_id")` to `AIAgent.__table_args__` (keeps the model in line with the migration), or have the test harness run migrations instead of `create_all()` (tests the real schema). Also worth a check for other model/migration drift of the same kind | Test harness / models |
| **V5-conversion-card-link-mismatch** | The "Conversions in progress" card links to Sources filtered by source status (`#screen-sources?status=processing`), but the label says "Conversions". There is no conversion-state filter in the Sources list. | **OPEN** | UI / Dashboard |
| **V5-no-conversions-list-endpoint** | There is no org-wide list endpoint for document conversions, only `/documents/{id}/conversions`. | **OPEN** | Backend |
| **V5-alembic-model-drift-wide** | `alembic check` against a database at head (`0046`) reports upgrade operations across 36 tables: 42 index removals and 38 additions (mostly naming, e.g. `ix_agent_definitions_org` in the migrations vs `ix_agent_definitions_organization_id` in the models), 18 type changes (`TIMESTAMP(timezone=True)` vs `DateTime` on agent-table columns) and 24 constraint removals. Pre-existing; surfaces only with `alembic check`; tests pass because the test harness uses `create_all()`. Distinct from **V5-aiagent-model-drift**, which covers only `AIAgent`. Found 2026-10-23 while adding `GET /knowledge/overview`, which touches no model or migration | **OPEN** — out of Step 6 scope; reconcile models and migrations table by table | Models / migrations |
| **V5-knowledge-overview-cache** | `GET /knowledge/overview` computes its counts on every request, with no server cache (matching `/dashboard/summary`). To order by "action needed" across all pages it aggregates over all of the organization's claims, linked evidence and open gaps, so its cost grows with the organization's total claims. Measured 2026-10-23 on 54 objects / 8,500 claims / 8,458 evidence links: median 30 ms per call, page query 15 ms. Monitor p95 of `GET /knowledge/overview` at 50-row pages on prod for 2 weeks before deciding TTL. | **OPEN** — add a Redis cache with a 5–10 s TTL, keyed by organization and query, if p95 exceeds 300 ms | Backend / Knowledge |
| **V5-source-sort-published-at** | `SORTABLE_FIELDS["Source"]` allow-listed `published_at`, but the model's column is `publication_date`, so `GET /sources?sort_by=published_at` passed validation and then crashed in `apply_sort` (500, not 422). It was the only allow-listed column, across 76 models, that did not exist. | **CLOSED** (Step 7-1) — allow-list corrected; `test_every_allow_listed_sort_column_exists_on_its_model` now checks every model | Backend |
| **V5-document-list-full-content** | `GET /documents` and `GET /sources/{id}/documents` return each document's full `content` (up to 2 MB) in every list row (`DocumentRead`). | **OPEN** — dropping it from list rows changes an existing contract; not needed for Step 7 | Backend / Sources |
| **V5-source-archive-state** | Source has no archive state. The Sources screen "Archived" badge is removed in Step 7A. Not a bug; a missing feature. | **OPEN** | Backend / Sources |
| **V5-dataset-card-not-real** | CSV/XLSX upload produces a converted document, not structured records. The Add source "Dataset" card is removed in Step 7E. Structured-record ingestion is not implemented. | **OPEN** | Backend / Sources |
| **V5-site-article-no-path** | The Add source "Site article" card is removed in Step 7E. No integration or endpoint creates a source from a post URL. | **OPEN** | Backend / Sources |
| **V5-source-export** | The Sources screen design has an Export button; no endpoint exports sources. The button is removed in Step 7A2a. Not a bug; a missing feature. | **OPEN** | Backend / Sources |
| **V5-source-row-actions** | The Sources screen design has a "More actions" menu on every row; no per-source action exists yet (archive, delete, re-run). The menu is removed in Step 7A2a. | **OPEN** | Backend / Sources |
| **V5-users-view-aria-label** | The Users screen's view toggle group (`#screen-admin-users`, `visual-harness/index.html`) still has `aria-label="View"`, which has no FA entry; Sources and Knowledge use "Display mode" («حالت نمایش»). The narrow-screen rule `.toolbar__actions .btn-group[aria-label="View"]` depends on that label, so renaming it means changing the selector too. Users is not a `--require`d screen. | **OPEN** — out of Step 7A4 scope | UI / i18n |
| **V5-theme-toggle-ui** | The theme selector is a plain `<select>` (`#pick-theme`) in preferences; there is no visual dark/light toggle in the toolbar. The user wants a standard toggle next to the language selector, keeping the same `savePrefs` behaviour and Step 5 race guard, with FA entries for both state labels. | **OPEN** — UI polish, after Step 7 | UI |
