# Known Issues

> **Lifecycle and ownership of every item below is tracked in
> [`DEBT_REGISTER.md`](DEBT_REGISTER.md), which is authoritative where
> the two disagree.** This file describes issues; that file tracks what
> happened to them.


## Phase 0
- Production readiness: `live` and `ready` health checks need separate implementation.

## Phase 1
- Integration test coverage can be expanded.

## Phase 2
- Graph currently supports limited node types.
- Relationship source FK completed in Phase 3.

## Phase 3
- Embedding provider is a deterministic placeholder (real API not used yet).
- No actual ingestion (URL, PDF, WordPress import) implemented yet.

## Phase 4
- `recompute_claim_aggregate`'s weight thresholds (0.5 conflict floor;
  1.0/2.0 net-weight buckets for weak/moderate/strong) are a first-pass
  heuristic, not tuned against real evidence distributions — revisit
  once real Evidence data exists (Phase 5, Research Engine).
- No dedicated "conflict list" or dashboard view yet — a conflicting
  claim is discoverable today only by reading its `evidence_strength`
  field directly (`GET /claims/{id}` or `GET /claims?...`), not via a
  purpose-built `?evidence_strength=conflicting` browse experience.

## Phase 5
- No real ResearchProvider is implemented — `NotConfiguredResearchProvider`
  is the only one wired up (see app/integrations/research/base.py).
  Every queued task will honestly complete with
  `result.outcome_status == "not_configured"` until a real provider
  (web search, PubMed/DOI lookup, or a search over this project's own
  Source/Document/Chunk store) is implemented and registered.
- `docs/master-spec/MASTER_SPEC.md` was missing at implementation time
  (see docs/DECISIONS.md ADR-013 for the full history) — **resolved**:
  the canonical file has been added, verified byte-for-byte, and
  cross-checked against the Phase 5 implementation with zero
  contradictions found (section 22's fields/modes/trail requirement and
  section 62's phase order both match what was already built).
- CONTINUOUS research mode has no actual scheduler — a CONTINUOUS
  ResearchProject is a valid domain object today, but nothing
  automatically creates new ResearchTasks under it on a recurring
  basis. Real scheduling infrastructure (e.g. Celery beat) is future
  work, as section 19 of the implementation instructions anticipated.
- No dedicated "research trail" browse UI/endpoint beyond
  `GET /research/tasks/{id}/references` — answering "which research
  led to this Knowledge Object" end-to-end today requires walking
  Task -> Project -> (optional) Knowledge Gap manually via separate
  GETs, not a single purpose-built query.
- Pre-existing repository hygiene items noticed during the Phase 5
  audit, unrelated to Phase 5 itself and left untouched per "keep
  changes focused": a handful of empty stray files at the repo root
  (`-`, `downgrade`, `upgrade`, `git`, `FETCH_HEAD`) and an empty
  duplicate `ai-context/` directory alongside the real
  `docs/ai-context/` — harmless, but worth a cleanup commit.

## Phase 6
- `normalize_query()` is deliberately simple (lowercase + whitespace
  collapse only — no stemming, diacritic folding, or stopword
  removal). It catches exact-content duplicates that differ only in
  casing/spacing but will treat genuinely-the-same-demand queries that
  differ more (e.g. plural/singular, synonym) as separate `Query` rows.
  Revisit once real-world import data shows how much this matters.
- Query clustering v1 (word n-gram Jaccard, see `docs/DECISIONS.md`
  ADR-016) has no real semantic understanding — it groups queries that
  share vocabulary, not queries that mean the same thing using
  different words. `_SIMILARITY_THRESHOLD` (0.5) is a first-pass,
  documented, revisitable constant, not tuned against real query
  distributions.
- The rule-based intent classifier's Persian/English anchor-phrase
  coverage is a small, deliberately-scoped seed set (see
  `app/services/intent_classifier.py`), not exhaustive. Genuinely
  ambiguous or uncovered queries are left unclassified (`DISCOVERED`)
  rather than guessed, by design — but that means real-world query
  volume will surface many DISCOVERED queries needing either rule
  expansion or manual classification.
- CSV import only (no Excel/`.xlsx`) — the approved v1 decision to
  avoid a new dependency (`openpyxl`/`pandas`). Revisit once a library
  choice is explicitly approved.
- `intents.product_id` has no FK constraint until Phase 7 creates
  `products` — referential integrity for that column is service-layer
  only (see `docs/DECISIONS.md` ADR-015) until then.
- No dedicated bulk "re-import updates existing fields" path —
  re-importing an already-known query only appends a `QueryProvenance`
  occurrence; it never overwrites the existing `Query` row's
  `search_volume`/`commercial_value`/`priority` even if the new import
  has fresher data. This avoids silent overwrites but means keeping
  those fields current requires an explicit `PATCH /queries/{id}`.
- **✅ Resolved — was an open spec deviation:** master spec section 23
  requires "The system must accept manually uploaded Excel/CSV query
  lists." Phase 6 v1 initially shipped CSV-only; `.xlsx` support
  (`openpyxl`) was added in a follow-up revision — `POST
  /queries/import` now dispatches to `query_service.parse_excel_rows`
  or `parse_csv_rows` based on the uploaded file's extension/
  content-type. See `docs/DECISIONS.md` ADR-020.
- **🟠 Migration `0007`'s downgrade is destructive**, not just
  reversible: reversing the additive `research_reference_type` enum
  extension requires deleting any `research_task_references` row using
  the two new values (`query`/`query_group`), since Postgres has no
  `DROP VALUE` and those values have no equivalent in the restored
  Phase 5 enum. Fine for the dev/CI migration-cycle check; genuinely
  data-lossy if ever run against a production database with real
  `query`/`query_group` references — see the downgrade()'s own inline
  comment in `migrations/versions/0007_query_engine.py` for the full
  warning, added specifically so this isn't glossed over as "just a
  reversible migration."

## Phase 7
- **Defense-in-depth gap (same class as Phase 5's, carried forward
  knowingly):** the database cannot by itself enforce that an Offer /
  ProductEvidence / ProductRelation row's `organization_id` matches its
  parent Product's. Both are independent FKs; the service layer
  validates the match before every insert and tests cover it, but a
  composite FK (or equivalent) would make it structurally impossible.
  See `docs/DECISIONS.md` ADR-022.
- **Provenance is per-row, not per-field.** A Product created by a
  merchant and later partially updated by a WooCommerce sync carries
  one `provenance` value; it cannot express "name is merchant-authored,
  price came from Woo". See ADR-021.
- **`ProductEvidence.claim` is free text**, deliberately (a merchant's
  claims are their own vocabulary). This means two links can state the
  same claim in different words and the system will treat them as
  distinct — there is no claim normalization or deduplication.
- **No product DELETE endpoint.** ARCHIVED covers retirement; hard
  deletion would destroy evidence/trust audit trail. Same reasoning as
  Source/Document in Phase 3. If genuine deletion is ever required
  (e.g. GDPR erasure of merchant data), it needs its own design.
- **Trust has no aggregate view.** "How trusted is this product" is
  answered today by listing that product's VERIFIED trust records and
  reading them; there is no summary endpoint, by design (ADR-024).
  Phase 8 will need to decide how to compare trust across products.
- **No WooCommerce sync yet.** `Product.external_id` and
  `ProductProvenance.WOOCOMMERCE` exist so a future sync has somewhere
  to write, but no sync job, mapping table, or conflict-resolution
  policy is implemented — that is Phase 10 per section 62.
- **Phase 6's Excel deviation is unrelated to and untouched by this
  phase** (it was resolved separately — see the Phase 6 section above).
- **Explicit-null PATCH semantics are fixed for Phase 7 endpoints only**
  (ADR-026). Earlier phases' update services still skip None values, so
  "clear this nullable field" is not expressible on, for example,
  `PATCH /knowledge/{id}` or `PATCH /sources/{id}`. Deliberately not
  changed across already-frozen phases in a Phase 7 hardening pass;
  worth a dedicated, separately-reviewed sweep.
- **`.github/workflows/ci.yml` exists in the repository but was absent
  from earlier delivered ZIPs** — the packaging command excluded
  `*.git*`, which matched `.github` as well as `.git`. Fixed in
  packaging; noted here because it means CI could not be inspected in
  those earlier snapshots even though it was present in the repo.

## Phase 8
- **Scoring weights and thresholds are documented judgments, not tuned
  values.** `_WEIGHTS` (0.35/0.25/0.25/0.15), the 0.5 neutral, the 0.1
  negative, and the 0.6 confidence threshold in
  `recommendation_policy.py` were chosen for legibility and defensible
  ordering, not derived from outcome data — none exists yet. They will
  need revisiting once real recommendations have been observed. Any
  change MUST bump `POLICY_VERSION` (ADR-029).
- **Relevance scoring is exact-match only** (category, brand,
  knowledge-object link, literal substring of stated interest). There
  is no semantic matching, deliberately: the only embedding provider in
  this codebase is a documented non-semantic placeholder (ADR-016), and
  scoring on it would look rigorous while being meaningless. A product
  that is genuinely relevant but shares no literal attribute with the
  request scores neutral, not high.
- **Domain boundaries are convention, not enforcement** (ADR-027).
  Nothing mechanically prevents a future module importing Phase 7's ORM
  models directly instead of going through
  `app/contracts/commerce.py`. An import-linter rule would fix this.
- **`POLICY_VERSION` bumping is manual.** A weight change without a
  version bump would silently mislabel historical decisions.
- **No recommendation feedback loop.** Nothing records whether a
  recommendation was shown, clicked, or converted, so the engine cannot
  learn or be evaluated against reality. That is deliberate for a
  deterministic MVP, but it means "is this policy any good?" is
  currently unanswerable from within the system.
- **CustomerContext has no retention policy.** Withdrawing consent
  clears identity fields and blocks recommendations, but contexts are
  never automatically expired or deleted. A real deployment needs a
  retention rule; none is implemented.
- **Effective verification is computed, not stored** (ADR-032). There
  is no materialised "effectively verified" column, so you cannot
  filter on it directly in SQL — `contracts/commerce.py` computes it by
  joining Evidence on every read. Correct, but at scale a materialised
  view may be warranted.
- **Evidence scope is explicit and auditable, NOT semantically
  guaranteed** (ADR-033). Within one organization, Product B's lab
  report can be attached to Product A. The system never makes that leap
  itself, never auto-verifies it, and records who verified it — but it
  cannot judge semantic fit. An earlier report overstated this as a
  "guarantee"; that wording is corrected.
- **Database-level tenant integrity is still incomplete.** `Offer`,
  `ProductEvidence`, `ProductRelation` and `Recommendation` each carry
  `organization_id` and a parent FK as two independent constraints; the
  database cannot enforce that they agree. Service layer and tests do.
  A composite FK (`UNIQUE (id, organization_id)` on parents, then
  composite FKs on children) would close this for the non-polymorphic
  relationships. Deliberately NOT done in this pass: it touches five
  tables across two frozen phases and deserves its own reviewed
  migration. `TrustRecord.subject_id` is polymorphic and cannot be
  closed this way at all.
- **`TrustSubjectType` is an MVP vocabulary** (ADR-035), not a settled
  boundary — section 30's trust chain names far more subject kinds than
  the three currently modelled.

## Phase 9
- **Polymorphic pointers remain service-enforced.** `trust_records.subject_id`,
  `research_task_references.reference_id` and `wordpress_mappings.object_id`
  point at one of several tables depending on a type column; SQL has no
  foreign key for that. The composite-FK hardening in migration `0010`
  closed every NON-polymorphic case (`DEBT_REGISTER.md` A3) — these are
  what remains, and closing them would need a different subject model,
  not a constraint.
- **The rate limiter fails open when Redis is unreachable** (ADR-039).
  Deliberate: a cache outage turning into a total integration outage is
  a worse failure than temporarily unmetered traffic. `/health/ready`
  reports Redis as degraded so operators can see it. Revisit if the
  cost model makes unmetered traffic the larger risk.
- **No webhook signature verification.** The adapter authenticates with
  a bearer credential over TLS, which is sufficient for a client-
  initiated call. If Phase 10 introduces WordPress-initiated webhooks
  where the plugin is the sender, signature verification and replay
  protection become necessary and are not built.
- **No adapter-side plugin code.** Phase 9 delivers the Core-side
  adapter boundary (identity, mappings, contracts). The PHP plugin in
  `plugin/` remains a 32-line stub; building it is deliberately out of
  scope for a backend phase and needs its own review.
- **`A4` was a stale register entry, not a defect** — `/live` and
  `/ready` were already separate since Phase 1. Recorded because a
  stale entry survived four reviews and was nearly re-implemented.
- **The WordPress plugin has never been run inside WordPress.** Its
  WordPress-dependent paths (hooks firing, nonce/capability enforcement,
  admin rendering, meta box in the block editor, HTTP via `wp_remote_request`)
  are `ENVIRONMENT BLOCKED`: no WordPress install exists here. What IS
  verified is every pure-logic path — 68 PHP tests covering JSON-LD mapping,
  status aggregation, credential validation, secret redaction and error
  categorisation — plus `php -l` on all 21 files. A real install is required
  before release.
- **No screenshots or rendered measurements exist** (ADR-044). The harness to
  produce them ships in `tests/visual/`.
- **§38's "WooCommerce hooks" is genuinely ambiguous** against §40/§62
  (ADR-041). Phase 9 implements identity projection only. Needs your
  decision before Phase 10.
- **RTL is unverified.** The table uses logical properties (`text-align:
  start`, `padding-inline`) so it should reflow correctly, but nothing has
  rendered it.

## Phase 10
- **No WooCommerce runtime verification.** `map_offer_state()` is tested as a
  pure function against synthesised state; it has never seen a real
  `WC_Product`. Variation handling, `woocommerce_product_set_stock` firing,
  and currency resolution are all ENVIRONMENT BLOCKED.
- **`MAX_ATTEMPTS = 5` is untuned** (ADR-051) — a documented constant, not a
  value derived from production retry data.
- **Offer sync runs inline, not in a Celery worker.** §41 says to use async
  workers. A SyncJob row is recorded for every sync (audit trail and
  idempotency are real), and a bulk guard (ADR-054) now caps inline syncs at
  20 per request and defers the rest to WP-Cron — so a bulk import no longer
  storms Core. What is still NOT built: routing sync through the Phase 5
  Celery infrastructure. WP-Cron only fires on traffic, so a large import on
  a quiet site drains slowly.
- **No WooCommerce→Core product creation.** A Woo product must be mapped to
  an existing Core product by ID. Auto-creating Core products from Woo would
  let an unreviewed catalogue become knowledge, which §26/§44 forbid.

## Phase 12
- **No automated collection.** No platform provider adapter exists; every
  observation is entered by a human (`collection_method=manual_paste`).
  Automated probing needs credentials and per-platform terms review that
  have not been done. **ENVIRONMENT BLOCKED / NOT IMPLEMENTED** — not a
  defect, a scope boundary.
- **No observation in this codebase came from a real AI platform.** All
  tests use synthetic data.
- **Click and Purchase are not measurable** (ADR-062) and this is
  permanent for this layer.
- **`period_spent` is a counter, not a live sum** (ADR-063). Drift bounded
  by one probe; `last_reconciled_at` exists but no reconcile job is built.

## Phase 12 — P12-18 / P12-19
- **Live AI platform execution: ENVIRONMENT BLOCKED.** No credentials. The
  provider interface, schemas, normalization, failure states and fixtures
  exist and are tested; no observation in this codebase came from a real AI
  platform, and every fixture row carries `is_fixture=True`.
- **Live Search Console / SERP execution: ENVIRONMENT BLOCKED.** Same
  position: adapter implemented, live connection not claimed.
- **Gap emission is a boundary, not an engine.** Visibility can reference
  `KnowledgeGap`; automatic gap creation from visibility findings is not
  built, deliberately, to avoid duplicating Phase 2's gap domain.

