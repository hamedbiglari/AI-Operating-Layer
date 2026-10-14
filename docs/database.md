# Database

## Conventions (apply to every table added from Phase 1 onward)

- Primary keys: UUID (`uuid.uuid4()` generated in Python), via
  `UUIDPrimaryKeyMixin` in `app/db/base.py`.
- Timestamps: `TIMESTAMPTZ`, via `TimestampMixin` (`created_at`,
  `updated_at`, both UTC).
- Every tenant-owned table carries `organization_id` with a foreign key
  to `organizations.id`. Tenant isolation is enforced at the service
  layer (query filters), not assumed from the schema alone.
- **Cross-tenant access returns 404, not 403** (`app/security/tenant.py:
  get_tenant_scoped_or_404`). A 403 would confirm a resource exists in
  another tenant; 404 makes "doesn't exist" and "exists but isn't
  yours" indistinguishable to the caller. This is enforced by routing
  every tenant-scoped lookup through this one helper rather than ad hoc
  `db.get()` calls in each endpoint.
- Soft-delete/archive semantics (e.g. a `status` or `archived_at`
  column) are used for business/knowledge data instead of hard deletes.
- Naming convention for constraints/indexes is fixed in
  `app/db/base.py` (`NAMING_CONVENTION`) so Alembic autogenerate output
  is stable and reviewable.
- Foreign keys and indexes are added based on actual access patterns
  (see section 53 of the master spec) as each entity group is
  implemented — not speculatively.

## Vector storage

- `pgvector` is enabled via the Phase 0 migration
  (`migrations/versions/0001_enable_extensions.py`).
- The embedding dimension is **not** hard-coded into a specific model
  column at this stage; `settings.EMBEDDING_DIMENSIONS` is the single
  configurable source used when `document_chunks.embedding` is defined
  in Phase 3, so changing embedding models later doesn't require a
  schema rewrite of every dependent table.
- Indexing strategy for embeddings (HNSW vs IVFFlat) is decided in
  Phase 3 once real chunk volume/query patterns exist.

## Notes from actually running these migrations against real Postgres

- Postgres ENUM types must be created with `create_type=False` on the
  column-level `postgresql.ENUM(...)` definitions whenever the type is
  ALSO created explicitly beforehand in the same migration — otherwise
  SQLAlchemy tries to create it a second time as a side effect of
  `create_table` and raises `DuplicateObject`. This bit migration
  `0002` first; `0003`'s nine enum types apply the same fix from the
  start. See `scripts/verify_migration_cycle.sh` for a way to check the
  full upgrade/downgrade cycle for any new migration before shipping it.
- `users.email` is globally unique (not unique-per-organization): in
  this MVP data model a user belongs to exactly one organization, so a
  global unique index is the correct constraint, not a composite one.
- `sites.domain` is unique per-organization
  (`uq_sites_organization_domain`), not globally — two different
  tenants may legitimately register the same domain during onboarding
  before ownership is verified.

## Current schema (Phase 8)

Migrations applied so far:

- `0001_enable_extensions` — enables `vector` and `pgcrypto`.
- `0002_organizations_users_sites_audit` — `organizations`, `users`,
  `sites`, `audit_logs`.
- `0003_knowledge_core` — `knowledge_objects`, `entities`, `claims`,
  `relationships`, `knowledge_versions`, `knowledge_gaps`, plus nine
  native Postgres ENUM types.
- `0004_sources_documents_chunks` — `sources`, `documents`,
  `document_chunks` (with a `vector(1536)` embedding column and an HNSW
  cosine-distance index), three more native ENUM types, and the
  foreign key on `relationships.source_id` that `0003` deliberately
  deferred.
- `0005_evidence_claim_evidence` — `evidence`, `claim_evidence`, plus
  four more native ENUM types (`evidence_directness`,
  `evidence_strength`, `evidence_status`, `evidence_relation`).
- `0006_research_engine` — `research_projects`, `research_tasks`,
  `research_task_references`, plus five more native ENUM types
  (`research_mode`, `research_project_status`, `research_task_status`,
  `research_reference_type`, `research_reference_role`).
- `0007_query_engine` — `queries`, `query_provenance`, `intents`,
  `query_groups`, `query_group_members`, `query_clusters`,
  `query_cluster_members`, plus five more native ENUM types
  (`query_source`, `query_status`, `query_priority`, `intent_type`,
  `intent_classification_source`), and an additive extension of
  `research_reference_type` (Phase 5) with `query`/`query_group`.
- `0008_commerce_product_knowledge` — `products`, `offers`,
  `product_evidence`, `product_relations`, `trust_records`, plus eight
  more native ENUM types (`product_status`, `product_provenance`,
  `offer_availability`, `offer_condition`, `product_relation_type`,
  `verification_status`, `trust_type`, `trust_subject_type`), and the
  foreign key on `intents.product_id` that `0007` deliberately
  deferred (the same pattern `0004` used for `relationships.source_id`).
- `0009_recommendation_engine` — `customer_contexts`, `recommendations`,
  plus nine more native ENUM types (`context_type`, `context_source`,
  `purchase_intent`, `need_level`, `price_sensitivity`,
  `consent_status`, `response_mode`, `recommendation_status`,
  `signal_state`). Reuses Phase 6's `intent_type` rather than
  duplicating it. No prior migration modified.

### Design decisions specific to Sources/Documents/Chunks (Phase 3)

- **`source_type` and `mime_type` are plain indexed strings, not
  ENUMs** — same open-vocabulary rationale as `object_type`/
  `entity_type`/`predicate`: master spec section 13 lists a starting
  set (scientific_paper, book, pdf, website, ...) but new source
  formats will keep appearing. `access_status`, `rights_status`, and
  `extraction_status` ARE closed workflow states, so those are native
  ENUMs, consistent with every other status field in the schema.
- **The embedding dimension is fixed at migration time, from
  `settings.EMBEDDING_DIMENSIONS`** (default 1536), read directly in
  the migration file via `from app.core.config import settings`.
  pgvector requires a fixed dimension per column — this is the
  "configurable via environment, not hard-coded, but not
  independently-variable-per-row either" position the Phase 0 design
  note asked for. Changing it after data exists requires a new
  migration that alters the column type and re-embeds existing rows.
- **HNSW index, `vector_cosine_ops`.** Built with raw `op.execute(...)`
  DDL since Alembic/SQLAlchemy have no native API for pgvector's
  access-method-specific index options. The ops class
  (`vector_cosine_ops`) must match whatever distance operator the
  application actually queries with
  (`DocumentChunk.embedding.cosine_distance(...)` in
  `document_chunk_service.py`) — an HNSW index built for L2 distance
  would silently not accelerate a cosine-distance query.
- **`document_chunks` has no `updated_at`.** Every other table uses
  `TimestampMixin` (created_at + updated_at) for consistency; chunks
  are the one deliberate exception because they're immutable —
  re-processing a document deletes and recreates its chunks rather
  than editing them in place (see `document_chunk_service.py::
  process_document`), so an `updated_at` column would never actually
  change and would just be dead weight on every row.
- **`document_chunks.organization_id` and `knowledge_versions.
  organization_id`** are both deliberate additions beyond their
  sections' literal field lists, for the same reason established in
  Phase 2: section 8 makes `organization_id` mandatory on every
  tenant-owned table without exception, and denormalizing it avoids a
  join on every tenant-scoped query — including, critically, the
  pgvector similarity search, which filters `WHERE organization_id =
  :org_id` directly on `document_chunks` rather than joining through
  `documents -> sources` first.
- **Editing a Document's content deletes its existing chunks
  immediately**, rather than leaving them in place with a "stale" flag.
  A chunk whose text no longer matches its parent document isn't just
  stale metadata — its embedding no longer represents anything real,
  and would silently corrupt similarity search results if left in the
  index. `extraction_status` resets to `pending`, signaling that
  `/documents/{id}/process` needs to be called again.
- **No hard DELETE for Source or Document.** Neither has a lifecycle
  `status` field in the master spec's literal field list (unlike
  KnowledgeObject's draft/published/archived); `access_status` and
  `extraction_status` cover the states that actually matter for these
  entities. Adding an invented "status" field not in the spec was
  judged worse than simply not offering a destructive delete endpoint.

### Design decisions specific to Evidence/ClaimEvidence (Phase 4)

- **`Evidence.evidence_strength` and `Claim.evidence_strength` are
  deliberately different enums** (`EvidenceStrength`: very_low/low/
  moderate/high, GRADE-style; `ClaimEvidenceStrength`: unverified/
  insufficient/weak/moderate/strong/conflicting). One rates a single
  study in isolation; the other is a Claim's aggregate, mechanically
  recomputed from every linked Evidence row. Conflating them would make
  it impossible to represent "this one meta-analysis is HIGH quality"
  and "this Claim overall is only WEAKly supported" as the two
  different, both-true facts they are.
- **`study_type` stays a plain indexed string**, same open-vocabulary
  rationale as `source_type`/`entity_type`/`predicate` — study-design
  taxonomies (RCT, cohort study, case report, ...) keep growing as
  ingestion covers more domains, and that growth must never require a
  migration.
- **`Evidence.document_id`/`document_chunk_id` are `ON DELETE SET
  NULL`, not `CASCADE`.** Re-processing a Document deletes and
  recreates its chunks (Phase 3's `document_chunk_service.py::
  process_document`); that housekeeping must never silently destroy a
  curated, possibly human-reviewed Evidence row. Losing the exact
  pinpoint just degrades gracefully back to source-level provenance —
  `source_id` itself is `NOT NULL` and `ON DELETE CASCADE`, since
  Evidence genuinely can't exist without SOME source.
- **`claim_evidence` is a plain link table with one substantive column
  of its own (`relation`), not just a bridge.** A single Evidence row
  (one study) can support one Claim while contradicting another, so
  `relation` has to live on the link, not on either side alone — this
  is the field `recompute_claim_aggregate` reads to detect
  disagreement (the "Conflict foundations" this phase adds).
  `UniqueConstraint(claim_id, evidence_id)` prevents the same pair
  being linked twice with different (confusing, contradictory)
  relations — updating the existing link is the correct move instead.
- **Only VERIFIED Evidence counts toward a Claim's aggregate.** Same
  "no auto-publish on unreviewed content" principle Claim.status
  already follows (section 44) — a DRAFT or REJECTED Evidence row
  linked to a Claim must not be able to move that Claim's
  `evidence_strength` until a human confirms the Evidence itself is
  trustworthy.

### Design decisions specific to the Research Engine (Phase 5)

- **`ResearchProject` and `ResearchTask` have two SEPARATE lifecycles**,
  each smaller than the spec's own illustrative full state list
  (DRAFT/QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED/ARCHIVED offered as
  *possible* states for both). QUEUED/RUNNING/FAILED describe
  *execution*, which happens to individual tasks, not to a project as
  a whole — a project doesn't "run", its tasks do. `ResearchProjectStatus`
  = draft/active/completed/cancelled/archived (is the investigation
  still open?); `ResearchTaskStatus` = pending/queued/running/completed/
  failed/cancelled (matches the spec's own "created → queued → worker
  execution → result → completed/failed" diagram almost literally).
  Conflating them would force a project to "complete" the moment its
  first task finishes, which is wrong for CONTINUOUS/EXPLORATORY
  research spanning many tasks over time.
- **`ResearchProject.mode` lives on the project, not the task.** A
  project's mode (GAP_DRIVEN/USER_DRIVEN/EXPLORATORY/CONTINUOUS)
  describes *why* the whole investigation exists; every task under one
  project shares that reason. Duplicating it per-task would just be
  redundant data that could drift from the project's own mode with no
  way to reconcile which one is "true".
- **GAP_DRIVEN projects are constrained at both the API and DB layer**
  to actually reference a Knowledge Gap: a Pydantic validator rejects
  the combination at request time, and
  `ck_research_projects_gap_driven_requires_gap` rejects it at the
  database level too, so no code path — not even a future direct
  script or a bug in some other service — can create a GAP_DRIVEN
  project with no gap.
- **`research_task_references` is a new, Phase-5-scoped table with its
  own `research_reference_type` enum**, not an extension of
  `Relationship`/`graph_node_type` (Phase 2's generic graph-edge
  table), even though `Relationship`'s own docstring anticipates
  "eventually Product/Source/etc." as node types. Research provenance
  ("this task referenced/discovered X") and knowledge-graph edges
  ("this entity contains that compound") are different kinds of fact;
  altering a shared production enum/table already exercised by
  Phases 2-4's tests, for a Phase-5-only need, was judged riskier than
  adding one small, independently-scoped table. See `docs/DECISIONS.md`
  ADR-014.
- **`ResearchProvider` is a swappable interface with exactly one
  implementation today** (`NotConfiguredResearchProvider`), same
  pattern as Phase 3's `EmbeddingProvider`/
  `DeterministicHashEmbeddingProvider` — except this placeholder does
  NOT fabricate a plausible-looking result the way the embeddings one
  intentionally does for pipeline-testing purposes. The master spec's
  section 18 explicitly forbids inventing fake research integrations,
  so `NotConfiguredResearchProvider` honestly reports `NOT_CONFIGURED`
  for every task instead.
- **`execute_research_task` never creates or reviews Claim/Evidence
  rows itself** — it only persists references (pointers) to rows that
  already exist, each independently tenant-checked. This is what makes
  section 12's "discovery is not verification" boundary structural: a
  future real provider that discovers a genuinely new fact would call
  `evidence_service.create_evidence` (or similar) on its own behalf,
  going through that service's own DRAFT-by-default, human-review-gated
  path — `execute_research_task` itself has no privileged shortcut that
  could create pre-verified content.

### Design decisions specific to the Query Engine (Phase 6)

- **`query` (section-23-literal), `normalized_query` (additive dedup
  key), and `raw_query` (additive, lives on `QueryProvenance` not
  `Query`) are three distinct fields, never conflated.** `query` stays
  exactly what section 23 defines — the canonical, immutable form.
  `normalized_query` is a deterministic derived column (lowercase +
  whitespace-collapse) the service layer needs for exact-content
  dedup, same justification pattern as `Document.content_hash`
  (Phase 3). `raw_query` preserves the exact string as it appeared in
  ONE specific import/source event, which can differ slightly
  (typos, casing) across occurrences that all resolve to the same
  `normalized_query` — that per-occurrence variation would be silently
  lost if collapsed into `Query` itself.
- **`QueryProvenance` is an additive, append-only occurrence log**, not
  a section-23-literal table. `Query.source` keeps its literal meaning
  (first-observed source, unchanged after creation); every subsequent
  re-observation of the same demand signal from a different source
  becomes a new `QueryProvenance` row instead of overwriting anything.
- **`source` (Query/QueryProvenance) and `intent_type` (Intent) are
  native Postgres ENUMs, not plain strings** — unlike `source_type`/
  `entity_type`/`predicate` elsewhere. Sections 23 and 24 both give an
  explicit, finite, closed list with no "this will keep growing"
  language, so this follows the project's own rule: closed
  spec-given vocabulary → ENUM.
- **`intents.product_id` has no FK constraint until Phase 7.** This is
  the identical deferred-FK pattern already shipped for
  `relationships.source_id` (added as a plain nullable UUID in the
  Phase 2 migration, given its real FK by Phase 3's migration `0004`
  once `sources` existed) — a future Phase 7 migration adds
  `intents.product_id`'s FK the same way, via `op.create_foreign_key`,
  never by editing migration `0007`.
- **`is_primary` on Intent is enforced unique-per-query by a partial
  unique index** (`WHERE is_primary`), not application logic alone —
  the same defense-in-depth discipline Claim's XOR `CHECK` constraint
  established: "at most one primary Intent per query" holds even if a
  future code path forgets to check it first.
- **`QueryCluster`/`QueryClusterMembership` are additive, NOT part of
  `query_groups`/`query_group_members`.** Section 25 only names the
  *curated* grouping tables; clustering is automatic, similarity-based
  grouping — a genuinely different kind of fact. Critically, a
  `QueryGroup`'s relationship to one or more `QueryCluster`s is
  **derived at read time**, never stored as a `cluster_id` on
  `QueryGroupMembership` — storing it redundantly would create two
  independent sources of truth for "which cluster is this query in"
  that could silently diverge the moment a re-clustering run changes
  an assignment.
- **Knowledge Need has no table at all.** See ADR-017: it is a
  service-level computed judgment
  (`query_group_service.assess_knowledge_need`), not a persisted row —
  deliberately, so that improving Claim/Evidence coverage elsewhere in
  the system automatically changes the answer without anyone touching
  `QueryGroup`.

### Design decisions specific to Commerce (Phase 7)

- **Product carries no price or stock.** Section 27: "Keep Product and
  Offer separate." One Product can have many simultaneous Offers
  (different sellers, currencies, promotional windows), which a price
  column on Product could not represent.
- **`Offer.stock_quantity IS NULL` ≠ `= 0`.** NULL means "quantity
  untracked"; 0 means "tracked, none left". Collapsing them would
  silently turn every untracked in-stock item into out-of-stock.
  Likewise `price IS NULL` means "price on request" (a real B2B state),
  not free.
- **`ProductEvidence.claim` is NOT NULL** — this is the mechanism that
  preserves evidence scope. Evidence is always attached to one specific
  stated assertion about the product, so composition evidence cannot
  drift into clinical-efficacy evidence. Uniqueness is on
  (product, evidence, claim), so one lab report can independently
  support several claims, each separately verifiable. See ADR-025.
- **`TrustRecord` has no score column and `evidence_id` is NOT NULL** —
  section 30's "Do not create a fake trust score" is enforced by making
  an unbacked trust assertion unrepresentable, not merely discouraged.
  See ADR-024.
- **Two-layer verification (ADR-032):** a `product_evidence` or
  `trust_records` row is EFFECTIVELY verified only when its own
  `verification_status` is VERIFIED **and** the `Evidence` row it
  points at is VERIFIED. Enforced at write time (422 otherwise) and
  recomputed at read time by `contracts/commerce.py`, so rejecting an
  Evidence row after the fact immediately revokes everything resting on
  it. Either side being REJECTED makes the whole assertion rejected.
- **Verification is never automatic** for either `product_evidence` or
  `trust_records`: both are born UNVERIFIED and only a human review
  action sets VERIFIED and stamps `verified_at`. Verifying the
  underlying Phase 4 `Evidence` row does NOT verify the product-level
  claim it is cited for — tested explicitly.
- **`product_relations` is its own table, not Phase 2's
  `Relationship`** — same reasoning as ADR-014: knowledge-graph edges
  and product-catalogue edges are different kinds of fact, and this one
  needs a `confidence` column the shared table has no equivalent for.
  Relations are directional and never auto-mirrored.
- **`Product` points at `KnowledgeObject`, never copies it** — a
  nullable FK, so a product about Taranjabin references the Taranjabin
  knowledge object rather than restating its claims.

### Design decisions specific to Recommendation (Phase 8)

- **Every score is paired with a `SignalState`.** `evidence_score`
  alone cannot distinguish "no evidence exists" from "evidence exists
  and was rejected" — both would be low numbers. `evidence_state` and
  `trust_state` carry that distinction explicitly, and UNKNOWN scores
  the neutral 0.5 while NEGATIVE scores 0.1, so absence never ranks
  below rejection. See ADR-028.
- **`policy_version` is NOT NULL on every recommendation.** Scoring
  will change; without recording which policy produced a decision,
  history becomes unexplainable. ADR-029.
- **`reason` is structured JSONB**, not free text, so agents and
  dashboards can consume it without parsing prose. ADR-031.
- **`customer_context_id` and `offer_id` are `ON DELETE SET NULL`** —
  erasing a customer's context (a legitimate privacy action) or
  retiring an offer must not destroy the merchant's decision audit
  trail.
- **`customer_contexts` stores no conversation transcript** (§32).
  `source` records the channel, never the content. Every identity
  field is nullable so a fully anonymous context is a first-class,
  fully functional case.

## Planned entity groups (Phase 9+, see master spec section 9)

visibility_tests · rights_policies · wordpress_mappings/commerce_mappings · sync_jobs

These are introduced incrementally per `docs/development.md`, each with
its own Alembic migration, and each imported into `app/models/__init__.py`
so Alembic autogenerate always sees the full schema.
