# Development

## Phased build order

```
Phase 0   Repository, Docker, config, FastAPI, PostgreSQL, Redis, Alembic   <- DONE
Phase 1   Organizations, Users, Sites, Authentication, Tenant isolation    <- DONE
Phase 2   Knowledge Objects, Entities, Relationships, Versions, Gaps       <- DONE
Phase 3   Sources, Documents, Chunks, pgvector                             <- DONE
Phase 4   Claims, Evidence, Claim/Evidence, Conflict foundations           <- DONE
Phase 5   Research Engine                                                  <- DONE
Phase 6   Query Engine, Intent, Query Clustering                           <- DONE
Phase 7   Products, Offers, Product Evidence, Trust                     <- DONE
Phase 8   Recommendation Engine                                          <- DONE
Phase 9   WordPress Adapter                                              <- DONE
Phase 10  WooCommerce Adapter
Phase 11  AI/REST interfaces
Phase 12  AI Visibility
Phase 13  Rights Layer
Phase 14  Dashboard
Phase 15  Pilot
Phase 16  Scale
```

Each phase must leave the repository runnable via
`docker compose up --build` and testable via `pytest`.

## Local workflow

```bash
cp .env.example .env
docker compose up --build          # start api + postgres(pgvector) + redis
docker compose exec api alembic upgrade head
docker compose exec api pytest -v
```

## Adding a new migration (from Phase 1 onward)

```bash
docker compose exec api alembic revision --autogenerate -m "add organizations and users"
docker compose exec api alembic upgrade head
```

Autogenerate only picks up models imported in `app/models/__init__.py`
(which `migrations/env.py` imports as a whole) — add the import there
when a new `app/models/*.py` module is created.

## Running the full test suite against real PostgreSQL

DB-backed tests (`tests/test_auth_flow.py`, `tests/test_tenant_isolation.py`,
`tests/test_users.py`, `tests/test_sites.py`, `tests/test_organizations.py`,
`tests/test_database.py`) skip gracefully with a clear message if
`DATABASE_URL` is unreachable, so local `pytest` still runs without
Docker. This is a convenience for quick unit-test iteration — it is
**not** a substitute for running them for real. Two ways to do that:

```bash
# 1. Via Docker (recommended, matches production topology)
docker compose up -d postgres
docker compose exec api alembic upgrade head
docker compose exec api pytest -v

# 2. Against a local Postgres (what was actually used to validate Phase 1)
alembic upgrade head
pytest -v
```

CI (`.github/workflows/ci.yml`) always runs option 1's equivalent
against a fresh Postgres service container — a green CI run is never a
skip in disguise.

## Verifying a migration's downgrade path

`alembic upgrade head` from a fresh database is exercised by every CI
run automatically. The DOWNGRADE path is not — nothing else runs
`alembic downgrade` against a real database. Before shipping any new
migration, run:

```bash
./scripts/verify_migration_cycle.sh
```

against a real (ideally disposable) Postgres database. It runs
`upgrade head -> downgrade base -> upgrade head` and fails loudly if any
application table survives the downgrade. This is a standalone script
rather than a pytest test on purpose — see the script's header comment
for why cycling DDL is incompatible with the transactional per-test
isolation the rest of the suite relies on.

## Coding rules carried across every phase

- New tenant-owned tables always include `organization_id` and use
  `UUIDPrimaryKeyMixin` + `TimestampMixin` from `app/db/base.py`.
- Public API contracts are Pydantic schemas in `app/schemas/`, never
  raw ORM models.
- Heavy work (ingestion, extraction, embeddings, sync) runs in Celery
  workers (`app/workers/`), never inline in an HTTP request handler.
- Outbound integrations (WordPress, WooCommerce, Search Console, etc.)
  live under `app/integrations/`, isolated behind an interface the
  services layer depends on.
- Every stage ships with tests under `backend/tests/`.

## STATUS — Phase 0

- implemented: repo layout; docker-compose (api, postgres+pgvector,
  redis); `.env.example`; FastAPI app with request-id middleware;
  `GET /` and `GET /api/v1/health` (with DB check); Alembic wired to
  `app.core.config.settings` and `Base.metadata`; migration `0001`
  enabling `vector`/`pgcrypto` extensions; pytest suite; WordPress
  plugin skeleton file.
- tested: baseline pytest suite passing.
- remaining: superseded by Phase 1 below.

## STATUS — Phase 1

- implemented:
  - Production config safety: `Settings` refuses to start with
    `APP_ENV=production` if `SECRET_KEY`/`DATABASE_URL` still hold
    development defaults, or `APP_DEBUG=true` (`app/core/config.py`).
  - Health split: `/health/live` (no DB), `/health/ready` (DB check,
    503 when degraded), `/health` kept as a legacy alias.
  - Request-ID validation: client-supplied `X-Request-ID` is checked
    against an allow-list pattern; invalid values are replaced.
  - Consistent error envelope (`app/core/errors.py`) for HTTP
    exceptions, validation errors, and unhandled exceptions.
  - Domain models: `Organization`, `User`, `Site`, `AuditLog`
    (`app/models/`), all UUID PK + TIMESTAMPTZ, registered centrally in
    `app/models/__init__.py` so Alembic autogenerate never misses one.
  - Security: bcrypt password hashing, JWT access tokens,
    `get_current_user`/`require_roles` dependencies, and
    `get_tenant_scoped_or_404` — the single choke point enforcing that
    cross-tenant access always returns 404, never 403.
  - Services + API: `/auth/register-organization`, `/auth/login`,
    `/auth/me`, `/organizations/me` (GET/PATCH), `/users`
    (GET/POST/GET-by-id/PATCH), `/sites` (GET/POST/GET-by-id/PATCH/
    DELETE-as-archive) — all tenant-scoped, all paginated where they
    list, all writing an audit log entry.
  - Migration `0002`: `organizations`, `users`, `sites`, `audit_logs`
    tables with native Postgres ENUM types, FKs, and indexes.
  - CI (`.github/workflows/ci.yml`): runs `alembic upgrade head` then
    the full pytest suite against a real Postgres **service container**
    on every push/PR — DB-backed tests never silently skip in CI.

- tested — and this time actually run against a **real local
  PostgreSQL 16 + pgvector instance** (not just compiled/imported),
  which surfaced and fixed four genuine bugs before they could reach
  anyone:
  1. `passlib` 1.7.4 is incompatible with `bcrypt>=4.1` — pinned
     `bcrypt==4.0.1`.
  2. Migration `0002` tried to create each Postgres ENUM type twice
     (once explicitly, once as a side effect of `create_table`),
     raising `DuplicateObject` — fixed with `create_type=False` on the
     column-level enum definitions.
  3. Test fixtures used the RFC 2606 reserved `.test` TLD in email
     addresses, which `email-validator` correctly rejects — switched
     test data to `.dev`.
  4. The test suite's session-scoped fixture called
     `Base.metadata.drop_all()` at teardown against whatever database
     `DATABASE_URL` points to — which would silently wipe a developer's
     running dev database after `pytest`. Removed; per-test isolation
     already comes from the transaction-rollback pattern in
     `db_session`, so nothing needed a destructive "reset the world"
     step.

  After these fixes: full upgrade → downgrade → upgrade migration
  cycle verified; **56/56 pytest tests pass** against real Postgres,
  including the full tenant-isolation ("golden test") suite in
  `tests/test_tenant_isolation.py`; a real `uvicorn` process was booted
  and `register-organization`/`login` were exercised end-to-end with
  `curl`.

- remaining: everything from Phase 2 onward — no Knowledge Objects,
  Entities, Sources, Evidence, Claims, Research, Query/Intent,
  Products/Offers, Trust, Recommendations, WordPress/WooCommerce sync,
  or Rights layer exist yet. Two Phase-0-review items remain
  non-blocking future work (documented, not implemented): a
  production-specific `docker-compose.prod.yml` (current compose file
  is dev-only, with bind-mounted source and exposed DB/Redis ports by
  design), and richer structured JSON logging beyond the current
  text-formatted logger.

## STATUS — Phase 2

- implemented: the Knowledge Core.
  - Models: `KnowledgeObject`, `Entity`, `Claim`, `Relationship`,
    `KnowledgeVersion`, `KnowledgeGap` (`app/models/`), all
    tenant-scoped, all registered in `app/models/__init__.py`.
  - Automatic versioning: every `PATCH`/publish/archive on a
    KnowledgeObject writes an immutable `KnowledgeVersion` snapshot
    through a single service-layer choke point
    (`_snapshot_and_bump_version` in `app/services/knowledge_service.py`)
    — there is no code path that mutates a KnowledgeObject without
    leaving a version behind.
  - Claim review lifecycle: `ClaimUpdate` has no `status` field at the
    schema level, so a plain edit cannot bypass review; only
    `POST /claims/{id}/review` can change status, and it always sets
    `human_reviewed=true` (master spec section 44's "no unreviewed
    claims published automatically" enforced structurally, not just by
    convention).
  - Polymorphic graph edges: `Relationship.subject_type`/`object_type`
    (`GraphNodeType`) let one edge table point at either an `Entity` or
    a `KnowledgeObject`; `relationship_service._resolve_and_check_node`
    does the tenant-check a real FK would otherwise give for free.
  - Migration `0003`: `knowledge_objects`, `entities`, `claims`,
    `relationships`, `knowledge_versions`, `knowledge_gaps`, plus nine
    native Postgres ENUM types — applying the `create_type=False`
    lesson from Phase 1 from the start.
  - `scripts/verify_migration_cycle.sh`: a standalone script (not a
    pytest test, deliberately — see the script's own comment for why)
    that runs `upgrade head -> downgrade base -> upgrade head` against
    a real database and asserts no application tables remain after the
    downgrade.
  - Full API surface: `/knowledge` (list/search/create/read/update/
    publish/archive + nested `/entities`, `/claims`, `/relations`,
    `/versions`, `/gaps`), `/entities`, `/claims` (+ `/review`),
    `/relationships`, `/knowledge-gaps` — all paginated where they
    list, all audit-logged on write.

- tested — against the same real local PostgreSQL 16 + pgvector
  instance used to validate Phase 1:
  - **114/114 pytest tests pass** (56 from Phase 1 unchanged + 58 new
    Phase 2 tests), including a dedicated
    `tests/test_knowledge_tenant_isolation.py` "golden test" suite that
    checks cross-tenant 404s for every Phase 2 resource — including the
    two-hop cases that are easy to get wrong: attaching an Entity to
    another org's KnowledgeObject, and creating a Claim that references
    another org's Entity as its subject.
  - Full migration cycle verified via `scripts/verify_migration_cycle.sh`:
    `upgrade head -> downgrade base -> upgrade head` against real
    Postgres, confirming zero application tables remain after the full
    downgrade and the schema rebuilds identically.
  - A live `uvicorn` process was booted and exercised end-to-end with
    `curl`: register organization -> create knowledge object -> create
    entity -> publish -> confirm two-entry version history -> confirm a
    second organization gets a real 404 on the first organization's
    knowledge object.
  - One real bug surfaced and fixed during this validation: the custom
    validation-error handler (`app/core/errors.py`) crashed with
    `TypeError: Object of type ValueError is not JSON serializable`
    whenever a Pydantic `@model_validator` raised a plain `ValueError`
    (e.g. the Claim "must have object_entity_id or object_value" rule)
    — Pydantic v2 puts the raw exception instance in the error's `ctx`
    field, which `json.dumps` cannot serialize. Fixed by running
    `exc.errors()` through FastAPI's `jsonable_encoder` before handing
    it to `JSONResponse`.

- remaining: Sources, Documents, Document Chunks (pgvector embeddings),
  Evidence and Claim/Evidence linking (Phase 4), Research Engine
  (Phase 5), Query/Intent/Query Clustering (Phase 6), Products/Offers/
  Trust (Phase 7), Recommendation Engine (Phase 8), WordPress/
  WooCommerce adapters (Phases 9–10), Rights layer (Phase 13), AI
  visibility (Phase 12). `GET /knowledge/{id}/evidence` from the master
  spec's API list is intentionally not implemented yet — it depends on
  the Evidence model.

## STATUS — Phase 2 fixes (post-review, before Phase 3)

A design review of the Phase 2 delivery caught three real defects
before the phase was considered closed. All three are fixed, migration
`0003` was corrected in place (not layered with a new migration, since
Phase 2 had not yet shipped externally), and 9 regression tests were
added — one full suite run below.

1. **Claim object was "at least one," not XOR.** The original CHECK
   constraint (`object_entity_id IS NOT NULL OR object_value IS NOT
   NULL`) and the matching Pydantic validator both only required at
   least one of the two fields, so a request setting BOTH would
   incorrectly succeed. Fixed at both layers: the constraint is now
   `ck_claims_object_entity_xor_value` (`(A IS NOT NULL AND B IS NULL)
   OR (A IS NULL AND B IS NOT NULL)`), and `ClaimCreate`'s validator now
   checks `has_entity == has_value` (true for both-set and
   neither-set) instead of `not (has_entity or has_value)`. Verified
   live: a `curl` request with both fields now returns a clean `422`
   instead of what would otherwise have been a raw `500` from the
   database CHECK constraint once fix #1 landed without fix #2 below.

2. **`ClaimUpdate` couldn't distinguish "omitted" from "explicitly
   cleared."** `None` was the default for both `object_entity_id` and
   `object_value`, so the API had no way to tell "the client didn't
   mention this field" from "the client wants it set to null" — meaning
   there was no way to switch a claim from one representation to the
   other, or to clear one side at all, without ambiguity. Fixed by
   reading `payload.model_fields_set` in `app/api/v1/claims.py` and
   passing explicit `object_entity_id_provided`/`object_value_provided`
   booleans into `claim_service.update_claim`, which now implements the
   full set of cases: omit → unchanged; set a non-null value → that
   representation wins and the other is auto-cleared; explicit null →
   cleared, but only if the other representation ends up set; both
   non-null → rejected outright (`InvalidClaimObjectError` → `422`),
   never silently resolved in favor of one side.

3. **`GET /knowledge/{id}/relations` paginated each side separately,
   then merged.** The old implementation called `list_relationships`
   twice (once filtered by `subject_id`, once by `object_id`), applied
   `limit`/`offset` to each call independently, then merged and
   deduplicated the two already-paginated result sets in Python — which
   both double-counted a self-loop edge in `total = subject_total +
   object_total` and made `limit`/`offset` meaningless beyond the first
   page. Fixed with a new `list_relationships_for_node` in
   `app/services/relationship_service.py`: a single query with `WHERE
   subject_id = :node_id OR object_id = :node_id`, counted once and
   paginated once, so a self-loop edge appears exactly once and paging
   through the full combined set never skips or repeats a row.

All fixes validated the same way as every other claim in this document
— against a real local PostgreSQL instance, not just by reading the
diff:
- **123/123 pytest tests pass** (114 from before + 9 new regression
  tests: 6 for the Claim XOR/PATCH fixes in `tests/test_claims.py`, 2
  for the relations pagination fix in `tests/test_relationships.py`,
  plus the existing suite re-run to confirm zero regressions).
- Migration `0003` was re-applied from a dropped/recreated database
  (since it was corrected in place) and the full
  `scripts/verify_migration_cycle.sh` cycle
  (`upgrade head -> downgrade base -> upgrade head`) was re-verified
  against real Postgres.
- A live `uvicorn` process was exercised with `curl` for fixes #1 and
  #2 specifically: a claim create with both `object_entity_id` and
  `object_value` returns `422` with a clear message (not a raw `500`);
  a `PATCH` explicitly nulling `object_value` with no `object_entity_id`
  fallback also returns `422` with a clear message.

## STATUS — Phase 3

- implemented: Sources, Documents, DocumentChunks — the full
  chunk/embed/store/search pipeline, end to end.
  - Models: `Source`, `Document`, `DocumentChunk`
    (`app/models/source.py`, `document.py`, `document_chunk.py`), all
    tenant-scoped, all registered in `app/models/__init__.py`.
    `DocumentChunk.embedding` is a real `pgvector.sqlalchemy.Vector`
    column sized from `settings.EMBEDDING_DIMENSIONS`.
  - Two-hop tenant ownership, applied per the Phase 2 review's
    forward-looking note: creating a Document validates its
    `source_id` belongs to the caller's organization
    (`document_service.create_document`) before the row is ever
    written — exactly the same discipline as Claim's subject/object
    entity checks in Phase 2. A dedicated regression test
    (`test_user_cannot_attach_document_to_another_orgs_source`)
    exercises precisely this case.
  - Chunking: `app/services/chunking.py` — a documented, honest
    paragraph/sentence-aware fixed-window baseline, explicitly not
    "true" semantic chunking (see the module's own docstring for why
    that's out of Phase 3's stated scope).
  - Embeddings: a pluggable `EmbeddingProvider` interface
    (`app/integrations/embeddings/base.py`) with one implementation,
    `DeterministicHashEmbeddingProvider` — a documented placeholder
    (deterministic, unit-length, but semantically meaningless vectors)
    chosen specifically because no embedding API is reachable from
    this environment's network allow-list, and requiring one would
    break `docker compose up --build` working without external
    credentials. Swapping in a real provider (OpenAI, Cohere, a local
    sentence-transformers model) requires implementing the same
    two-method interface, no caller changes.
  - Storage/indexing: `vector(1536)` column, HNSW index with
    `vector_cosine_ops` built via raw DDL (Alembic has no native API
    for pgvector's index options) — matched to the `.cosine_distance()`
    operator actually used in queries.
  - Processing is synchronous (`POST /documents/{id}/process`), not a
    Celery task — Redis/Celery infrastructure is still just the empty
    `app/workers/` scaffold from Phase 0; wiring an actual worker
    process is separate infrastructure work not required to prove the
    pgvector pipeline itself works. The function signature doesn't
    assume synchronous execution, so moving it into a worker task later
    is mechanical.
  - Editing a Document's `content` bumps `version`, recomputes
    `content_hash`, and **deletes** (not just flags) any existing
    chunks, resetting `extraction_status` to `pending` — a stale
    embedding is actively wrong, not just outdated, so it's removed
    rather than left to silently corrupt search results.
  - The FK Phase 2 deferred is now in place:
    `relationships.source_id -> sources.id`, added via
    `op.create_foreign_key` in migration `0004` without touching
    existing data.
  - Full API surface: `/sources` (list/search/create/read/update +
    nested `/documents`), `/documents` (list/create/read/update +
    `/process`, `/chunks`, `/chunks/{id}`), and the pgvector-powered
    `/documents/chunks/search` — all paginated where they list, all
    audit-logged on write.

- tested — against the same real local PostgreSQL 16 + pgvector
  instance used for every phase before this one:
  - **158/158 pytest tests pass** (123 from before + 35 new: Sources,
    Documents, DocumentChunks CRUD/RBAC, and a dedicated
    `tests/test_phase3_tenant_isolation.py` golden-test suite that
    specifically includes a pgvector-aware case
    (`test_similarity_search_never_returns_another_orgs_chunks`) —
    two organizations embed the exact same text, and org A's search
    must never surface org B's chunk, proving the tenant filter is
    applied to the vector query itself, not just to REST-layer
    lookups by ID).
  - Full migration cycle verified via `scripts/verify_migration_cycle.sh`
    across all four migrations: `upgrade head -> downgrade base ->
    upgrade head`, confirming the deferred FK on
    `relationships.source_id` is correctly dropped before `sources` on
    the way down and correctly recreated on the way back up.
  - A live `uvicorn` process was exercised end-to-end with `curl`
    proving the full pipeline: register organization -> create source
    -> create document with real text content -> `/process` (chunk +
    embed) -> list chunks -> `/chunks/search` with the exact chunk
    text as the query, confirming a returned cosine distance of
    exactly `0.0`.
  - Migration `0004` applied cleanly against real Postgres on the
    first attempt — no bugs surfaced during this phase's validation
    (unlike Phases 1 and 2, where real-database testing caught genuine
    defects). This is noted explicitly rather than silently omitted,
    since the pattern up to now has been "real testing finds real
    bugs" and it's worth being clear when a phase's first real-DB run
    was actually clean.

- remaining: Research Engine (Phase 5), Query/Intent/Query
  Clustering (Phase 6), Products/Offers/Trust (Phase 7), Recommendation
  Engine (Phase 8), WordPress/WooCommerce adapters (Phases 9–10),
  Rights layer (Phase 13), AI visibility (Phase 12). Real ingestion
  (URL fetching, PDF parsing, WordPress import, CSV/Excel query lists)
  is explicitly not implemented — Phase 3 accepts already-extracted
  plain text via the API; turning raw inputs into that text is future
  ingestion-pipeline work, and a real embedding provider needs to
  replace the placeholder before any of this is used for actual
  semantic search.

## STATUS — Phase 4

- implemented: Evidence and Claim/Evidence linking — the "Conflict
  foundations" this phase's name promises.
  - Models: `Evidence` (`app/models/evidence.py`) and `ClaimEvidence`
    (`app/models/claim_evidence.py`), both tenant-scoped, both
    registered in `app/models/__init__.py`. `Claim` gained an
    `evidence_links` relationship back to `ClaimEvidence`.
  - Evidence's provenance chain is three-hop, not two: `source_id` is
    required and must belong to the caller's org; `document_id` and
    `document_chunk_id` are optional but, if given, must ALSO belong to
    the org AND must actually belong to the given `source_id`/
    `document_id` respectively — not just to some sibling resource in
    the same org (`evidence_service._validate_provenance_chain`, tested
    by `test_document_must_belong_to_given_source` and
    `test_chunk_must_belong_to_given_document`). `document_id`/
    `document_chunk_id` are `ON DELETE SET NULL`, not `CASCADE` —
    re-chunking a Document (which deletes and recreates its chunks,
    Phase 3) must never silently destroy a curated, possibly
    human-reviewed Evidence row; it only loses its precise pinpoint.
  - `EvidenceStrength` (GRADE-style: very_low/low/moderate/high) is
    deliberately a separate enum from `ClaimEvidenceStrength`: one rates
    a single Evidence row (a property of the study itself), the other
    is Claim's rolled-up aggregate. `study_type` stays a plain indexed
    string (open vocabulary, same rationale as `source_type`);
    `directness`, `evidence_strength`, `status` are closed Postgres
    enums.
  - Evidence has the same review-lifecycle discipline as Claim: `status`
    only changes via `POST /evidence/{id}/review`, which always sets
    `human_reviewed=True` and then recomputes every Claim linked to
    that Evidence (verifying evidence is exactly the event that can
    make it start or stop counting toward an aggregate).
  - `ClaimEvidence.relation` (supports/contradicts/mixed/neutral) is the
    raw signal for conflict detection. `weight` is optional (0-1); when
    omitted, `claim_evidence_service._effective_weight` derives it from
    the linked Evidence row's `evidence_strength`
    (very_low=0.25/low=0.5/moderate=0.75/high=1.0) — an explicit weight
    exists only for the rare human override.
  - `claim_evidence_service.py::recompute_claim_aggregate` — called
    after every link create/update/delete and after every Evidence
    review transition — sums support vs. contradict weight across every
    **VERIFIED** linked Evidence row (unverified/draft/rejected evidence
    counts toward nothing, same "no auto-publish on unreviewed content"
    principle as Claim's own review lifecycle) and maps the result onto
    `ClaimEvidenceStrength`: no verified evidence -> `unverified`;
    non-trivial weight on both sides -> `conflicting`; otherwise the net
    (support − contradict) buckets into `insufficient`/`weak`/
    `moderate`/`strong`. This is a **documented heuristic**, not a final
    scientific-consensus algorithm — replacing it with something more
    sophisticated is explicit future work for the Research/Query engine
    phases (5–6).
  - Safety guardrail, the one place this phase touches Claim.status
    automatically: if recompute detects genuine conflict and the Claim
    is currently `APPROVED`, it is auto-downgraded to `DISPUTED` (with
    its own audit log entry). The Claim is **never** auto-upgraded to
    `APPROVED` — that direction always requires a human
    `POST /claims/{id}/review` action.
  - Full API surface: `/evidence` (list/create/read/update +
    `/review`) and `/claim-evidence` (list/create/read/update/delete) —
    the latter a flat top-level resource filterable by
    `claim_id`/`evidence_id`, matching `/relationships`' shape (Phase
    2's generic graph-edge table) rather than nesting under either
    side, since a link genuinely belongs to neither Claim nor Evidence
    more than the other.
  - Migration `0005`: `evidence`, `claim_evidence`, plus the four new
    Postgres enum types.

- tested — against the same real local PostgreSQL 16 + pgvector
  instance used for every phase before this one:
  - **186/186 pytest tests pass** (158 from before + 28 new:
    `test_evidence.py` (provenance-chain validation, review lifecycle,
    filtering), `test_claim_evidence.py` (linking, weight overrides,
    and the conflict-foundations aggregate math itself — including the
    auto-downgrade-to-DISPUTED guardrail), and
    `test_phase4_tenant_isolation.py` (the golden-suite pattern
    continued: every hop of Evidence's provenance chain and both sides
    of a `claim_evidence` link independently checked cross-org).
  - Full migration cycle verified via
    `scripts/verify_migration_cycle.sh`: `upgrade head -> downgrade
    base -> upgrade head`, confirming a clean drop back to zero
    application tables and a clean rebuild including the two new
    tables and four new enum types.
  - The database was fully dropped and recreated from scratch
    (`DROP DATABASE` / `CREATE DATABASE` / `CREATE EXTENSION vector`)
    and the entire 186-test suite re-run against that from-zero
    database as the final validation step — not just an incremental
    `alembic upgrade` on an already-running one.
  - No bugs surfaced during this phase's real-database validation —
    same clean result as Phase 3, noted explicitly for the same reason:
    the project's honest pattern so far is "real testing finds real
    bugs," so a clean run is worth stating plainly rather than
    silently omitting the observation.

- remaining: everything Phase 3's "remaining" list already named
  (Research Engine, Query/Intent, Products/Trust, Recommendations,
  WordPress/WooCommerce adapters, Rights layer, AI visibility, real
  ingestion, a real embedding provider) is unchanged by this phase.
  Additionally still open for a future phase: `recompute_claim_aggregate`'s
  weight thresholds (0.5 conflict floor; 1.0/2.0 net-weight buckets) are
  a first-pass heuristic calibrated for legibility and testability, not
  tuned against real evidence distributions — expect the Research
  Engine phase to either validate or revise them once real Evidence
  data exists to check them against.

## STATUS — Phase 5

- **Source-of-truth note (read this first):** at implementation time,
  `docs/master-spec/MASTER_SPEC.md` — named as the canonical spec by
  the Phase 5 implementation instructions, which quoted its section 22
  (Research Engine) and section 62 (development order) directly — did
  not exist anywhere in this repository or its git history. The quoted
  text was used as the authoritative source for the implementation
  below at the time (see `docs/DECISIONS.md` ADR-013). **Update:** the
  canonical file has since been supplied and added at
  `docs/master-spec/MASTER_SPEC.md` (2237 lines, sections 1-66,
  verified byte-for-byte against the supplied copy). It has been
  cross-checked against everything implemented below: section 22's
  literal field lists, the four research modes, and the "traceable
  results"/"preserve the research trail" requirements all match with
  zero contradiction, so nothing in this STATUS section needed to
  change as a result.

- implemented: the Research Engine foundation — ResearchProject,
  ResearchTask, a swappable ResearchProvider interface, and the
  project's first real Celery worker task.
  - Models: `ResearchProject` (`app/models/research_project.py`),
    `ResearchTask` (`app/models/research_task.py`), and
    `ResearchTaskReference` (`app/models/research_task_reference.py`),
    all tenant-scoped, all registered in `app/models/__init__.py`.
  - `ResearchProject.mode` holds the four spec-named modes
    (GAP_DRIVEN/USER_DRIVEN/EXPLORATORY/CONTINUOUS) — deliberately a
    project-level field, not duplicated per-task, since every task
    under one project shares that project's reason for being. A
    `CHECK` constraint (`ck_research_projects_gap_driven_requires_gap`)
    plus a matching Pydantic validator make "GAP_DRIVEN with no
    `knowledge_gap_id`" impossible at both the API and DB layer.
  - Two independent, deliberately small lifecycles, each with its own
    validated transition table in the service layer (never a free-form
    status field, never a DB `CHECK` trying to encode a graph):
    `ResearchProjectStatus` (draft → active → completed/cancelled →
    archived — the investigation's own open/closed state, since a
    project doesn't "run", its tasks do) and `ResearchTaskStatus`
    (pending → queued → running → completed/failed, plus cancelled —
    matching the spec's own "created → queued → worker execution →
    result → completed/failed" diagram almost literally).
  - `app/integrations/research/base.py::ResearchProvider` — the same
    swappable-provider interface pattern Phase 3 established for
    embeddings (`EmbeddingProvider`). `NotConfiguredResearchProvider`
    is the only provider registered by default and is deliberately
    honest rather than fake: with no reachable external research/search
    API in this environment (same network-allow-list constraint as the
    embeddings placeholder), it reports `NOT_CONFIGURED` for every
    task rather than fabricating a plausible-looking result — the
    spec's own section 18 explicitly forbids inventing fake
    integrations. `ResearchOutcomeStatus` gives the five-way
    distinction section 18 asks for (not configured / provider failed
    / no result found / result found / result inaccessible).
  - `app/workers/celery_app.py` + `app/workers/tasks.py` — `app/workers/`
    was empty scaffolding through Phase 4 (Redis/Celery were in
    `requirements.txt` but never wired to anything); this is the first
    real Celery task in the codebase. `POST /research/tasks/{id}/queue`
    transitions PENDING→QUEUED and dispatches
    `execute_research_task_job.delay(...)`; the task itself opens its
    own DB session (`SessionLocal`, the same factory `get_db` uses) and
    delegates to `research_task_service.execute_research_task`, which
    has no Celery dependency of its own.
  - `execute_research_task` is where section 12's boundary
    ("discovery is not verification") is structural, not just
    documented: the function only ever writes to `research_tasks` and
    `research_task_references`. It never creates, updates, or reviews a
    Claim or Evidence row — a real future provider that discovers new
    evidence would call `evidence_service.create_evidence` itself
    (which already defaults to `status=DRAFT`,
    `human_reviewed=False`), not have this function do it on its
    behalf. Verified directly by
    `test_execute_referencing_existing_evidence_does_not_verify_it`.
  - `research_task_references` is a small, Phase-5-scoped polymorphic
    link table (its own `research_reference_type` enum: source/
    document/evidence/claim/knowledge_object/knowledge_gap; its own
    `research_reference_role` enum: input/output) rather than an
    extension of `Relationship`/`graph_node_type` — see
    `docs/DECISIONS.md` ADR-014 for why reuse was considered and
    rejected.
  - Tenant isolation is the two-hop pattern established in Phase 3/4:
    `research_project_id` must belong to the caller's org before a
    Task can be created under it, and every reference a provider
    reports is independently resolved and tenant-checked (mirroring
    `relationship_service._resolve_and_check_node`) before being
    persisted — a provider reporting a cross-tenant reference_id fails
    the whole execution loudly (`test_execute_rejects_reference_to_another_orgs_resource`)
    rather than silently being dropped or silently succeeding.
  - Full API surface under `/research`: `/projects` (list/create/read/
    update + `/transition`) and `/tasks` (list/create/read/update +
    `/queue` + `/cancel` + `/references`) — reads open to any
    authenticated user in the org, writes requiring
    `KNOWLEDGE_EDITOR_ROLES` (the same split every Phase 2-4 resource
    uses; no separate "execute" permission tier was introduced, since
    no prior phase in this codebase distinguishes write from execute
    more finely than that).
  - Migration `0006`: `research_projects`, `research_tasks`,
    `research_task_references`, plus five new Postgres enum types.

- tested — against the same real local PostgreSQL 16 + pgvector
  instance used for every phase before this one, PLUS a genuine
  Redis + Celery worker smoke test this phase specifically required:
  - **223/223 pytest tests pass** (186 from before + 37 new across
    `test_research_projects.py`, `test_research_tasks.py`,
    `test_research_execution.py`, and
    `test_phase5_tenant_isolation.py`).
  - Celery tasks run in the test suite via `task_always_eager=True`
    (an autouse fixture in `tests/conftest.py`) — Celery's own
    documented technique for testing task bodies synchronously without
    a broker. One real limitation this surfaced and worked around: the
    Celery task opens its own `SessionLocal()` connection, which is
    invisible to the per-test transaction-rollback session `client`
    uses (`tests/conftest.py`'s `db_session`) — cross-connection
    isolation, not a bug. `test_research_tasks.py` therefore patches
    `.delay()` to a no-op when testing the `/queue` endpoint's own
    transition behavior, and `test_research_execution.py` exercises
    `execute_research_task`'s real logic directly, same-session,
    instead. This is stated explicitly rather than glossed over, per
    the "never claim tests passed unless actually executed" rule.
  - **A genuine, non-eager, end-to-end smoke test was also run**: a
    real `redis-server` was started, a real `celery -A
    app.workers.celery_app worker` process was started, and a real
    `uvicorn` process was started — then an actual HTTP client
    registered an organization, created a project and task, and called
    `POST /research/tasks/{id}/queue`. The real worker process
    (connected over the real Redis broker, a genuinely separate OS
    process from the API server) picked up the job and the task's
    status was independently observed to move
    `pending → queued → running → failed` with
    `result.outcome_status == "not_configured"` — proving the actual
    broker/worker wiring works, not just the eager-mode test path.
  - Full migration cycle verified via
    `scripts/verify_migration_cycle.sh`: `upgrade head → downgrade
    base → upgrade head`, confirming a clean drop back to zero
    application tables and a clean rebuild including all three new
    tables and five new enum types.
  - The database was fully dropped and recreated from scratch
    (`DROP DATABASE` / `CREATE DATABASE` / `CREATE EXTENSION vector`)
    and the entire 223-test suite re-run against that from-zero
    database as the final validation step.
  - One real bug was found and fixed during this phase's own test
    development (not a production bug, but worth recording honestly):
    the first draft of `test_research_execution.py` called
    `execute_research_task` on a task still in `PENDING` status,
    which correctly raised `InvalidResearchTaskTransitionError`
    (PENDING can only move to QUEUED or CANCELLED, never directly to
    RUNNING) — the tests were fixed to queue the task first
    (`research_task_service.queue_research_task`, same session) before
    executing it, matching the real production sequence a Celery job
    is always invoked in. The service logic itself did not need to
    change; this was a test-setup bug the transition table correctly
    caught.

- remaining: Products/Offers/Trust (Phase 7), Recommendation Engine
  (Phase 8), WordPress/WooCommerce adapters (Phases 9-10), Rights layer
  (Phase 13), AI visibility (Phase 12) — all unchanged by this phase.
  Specific to Research: no real `ResearchProvider` is implemented
  (every task honestly fails with `not_configured` until one is);
  CONTINUOUS mode has no actual scheduler (Celery beat or equivalent is
  future work). `docs/master-spec/MASTER_SPEC.md` has been added to
  the repository (see the source-of-truth note above and
  `docs/DECISIONS.md` ADR-013).

## STATUS — Phase 6

- implemented: the Query Engine foundation — Query/QueryProvenance
  (section 23), Intent (section 24, with a rule-based classifier),
  QueryGroup/QueryGroupMembership (section 25, curated grouping), and
  QueryCluster/QueryClusterMembership (additive — automatic similarity
  grouping, kept deliberately separate from curated groups).
  - **Query model reconciled with section 23's literal field list**
    via three distinct roles (`query`/`normalized_query`/`raw_query`)
    rather than one field doing double duty — see
    `docs/DECISIONS.md` ADR-015 for the full reasoning and
    `app/models/query.py`/`query_provenance.py`'s own docstrings.
    `import_queries` (CSV **or Excel `.xlsx`** upload — see ADR-020 —
    or a JSON row batch; manual single-entry reuses the same path with
    `source=manual`, per the approved
    decision not to add a bare `POST /queries` beyond section 50's
    literal endpoint list) deduplicates every row against existing
    `Query` rows in the org by `normalize_query()`: a match appends a
    new `QueryProvenance` occurrence; no match creates a new `Query` +
    its first occurrence. Existing fields are never silently
    overwritten by a re-import.
  - **`Query.status` is a true 3-state lifecycle** (DISCOVERED ->
    CLASSIFIED -> ARCHIVED) — CLASSIFIED is set automatically by
    `intent_service.classify_query` the moment a query gets its first
    `Intent` row, never a manual `PATCH` target; ARCHIVED is the one
    genuinely manual action. "Clustered" and "grouped" are
    deliberately NOT states — they're derived facts (does a
    `QueryClusterMembership`/`QueryGroupMembership` row exist?), since
    a query can be classified AND clustered AND grouped simultaneously,
    which a single-valued status can't represent.
  - **The rule-based intent classifier**
    (`app/services/intent_classifier.py`) is a pure function, no DB
    dependency, built specifically to avoid the failure mode the design
    review identified: a bare "کجا" ("where") token must never anchor
    a classification on its own, because it's ambiguous between ORIGIN
    ("از کجا می‌آید" - where does it come from) and TRANSACTIONAL ("کجا
    بخریم" - where to buy). Every rule anchors on a multi-token phrase
    or an unambiguous single English word; rules are evaluated
    most-specific-first with span-consumption so a looser rule can't
    double-fire on a substring a more specific rule already claimed;
    only compound anchors reach high confidence; a query with no rule
    match produces zero Intent rows (stays DISCOVERED), never a guess.
    `test_intent_classifier.py` tests the exact "کجا بخریم" vs. "از کجا
    می‌آید" disambiguation directly, plus 11 other cases.
  - **Multi-intent is real**: a query can have several `Intent` rows;
    `is_primary` (enforced unique per query by a partial unique index,
    not just application logic) marks the dominant one.
    `classification_source`/`reason` give the explainability the
    research trail principle (section 10) already established for
    Phase 5, applied here to classification: which literal anchor
    phrase fired, or was this a human override (`MANUAL`, which always
    creates a NEW Intent row rather than editing a rule-engine row in
    place, preserving classification history).
  - **`intents.entity_id` is a real FK** (Entity already exists,
    Phase 2); **`intents.product_id` has no FK yet** — the same
    deferred-FK pattern already shipped for
    `relationships.source_id` in Phase 2->3 (migration `0004`), applied
    here for the Phase 6->7 boundary. See `docs/DECISIONS.md` ADR-015.
  - **Knowledge Need is a computed judgment, not a table** —
    `query_group_service.assess_knowledge_need` returns a value object
    (has the group's `target_entity_id` got adequate Claim/Evidence
    coverage?), never a persisted row, and `QueryGroup` is explicitly
    NOT treated as if it were the Knowledge Need (a group can be fully
    covered already; conflating the two would make every group
    automatically imply a gap). If the assessment concludes a gap
    exists, Phase 6 never creates one — that stays on the *existing*
    `POST /knowledge-gaps` (Phase 2). See `docs/DECISIONS.md` ADR-017.
  - **Query clustering v1 is word n-gram (unigram+bigram) Jaccard
    similarity**, not embeddings — because the only embedding provider
    in this codebase (`DeterministicHashEmbeddingProvider`, Phase 3) is
    explicitly documented as having no real semantic meaning;
    clustering on top of it would look numerically legitimate while
    being semantically meaningless. `QueryCluster`/
    `QueryClusterMembership` are additive tables (section 25 only
    names the *curated* `query_groups`/`query_group_members`); a
    cluster's relationship to a `QueryGroup` is deliberately NOT stored
    (no `cluster_id` on `QueryGroupMembership`) to avoid two sources of
    truth that could diverge — it's derived at read time instead. See
    `docs/DECISIONS.md` ADR-016 and
    `app/services/query_cluster_service.py`.
  - **`research_reference_type` (Phase 5) is additively extended**
    with `query`/`query_group` (migration `0007`) so a
    `ResearchTaskReference` can trace a research effort back to the
    demand signal that motivated it, reusing Phase 5's existing
    provenance table rather than Phase 6 inventing a parallel one —
    the one place this phase touches a prior migration's schema
    surface, and additive-only (migration `0006` is never edited). See
    `docs/DECISIONS.md` ADR-018 for the full reasoning, including how
    the downgrade path correctly rebuilds the original Phase 5 enum
    value set (Postgres has no `DROP VALUE`).
  - Full API surface: `/queries` (import/list/read/update/archive),
    `/queries/{id}/intents` (list + manual override),
    `/queries/{id}/classify` + bulk `/queries/classify`,
    `/queries/cluster` + `/query-clusters` (list/read/members),
    `/query-groups` (CRUD + members + knowledge-need-assessment) —
    reconciled against section 50's literal 4-line endpoint list, with
    every addition beyond those 4 lines (by-id reads, the archive/
    classify/intent-override actions, cluster browsing) reasoned about
    explicitly as a necessary, conventional complement rather than
    scope creep (see the Phase 6 design proposal this STATUS section
    summarizes, and each addition's own docstring).
  - Migration `0007`: `queries`, `query_provenance`, `intents`,
    `query_groups`, `query_group_members`, `query_clusters`,
    `query_cluster_members`, five new enum types, plus the additive
    `research_reference_type` extension above.

- tested — against the same real local PostgreSQL 16 + pgvector
  instance used for every phase before this one:
  - **281/281 pytest tests pass** (223 from before Phase 6 + 54 from
    Phase 6's initial delivery + 4 more added when Excel import was
    added in a follow-up revision — see below):
    `test_intent_classifier.py` (13 pure unit tests, no DB — including
    the exact "کجا بخریم" vs "از کجا می‌آید" disambiguation the design
    review flagged), `test_queries.py` (import/dedup/CSV/Excel/list/
    update/archive), `test_intent_service.py` (classification, the
    DISCOVERED->CLASSIFIED auto-transition, manual override,
    idempotency), `test_query_groups.py` (CRUD, membership, the
    Knowledge Need assessment exercised against a real Phase 4
    claim/evidence chain), `test_query_clustering.py`, and
    `test_phase6_tenant_isolation.py` (12 tests, including both
    directions of the QueryGroup<->Query membership two-hop).
  - One real bug was found and fixed during this phase's own test
    development (recorded honestly, same as Phase 5's precedent): the
    first draft of a clustering test used two example queries whose
    actual word-shingle Jaccard similarity was 0.33 — below the
    documented 0.5 threshold — and asserted they'd merge. The
    clustering algorithm behaved correctly (0.33 similarity is
    genuinely below the threshold); the test's example data was wrong,
    not the service. Fixed by using a genuinely near-duplicate pair
    (0.71 similarity) instead.
  - **Excel (`.xlsx`) import was added in a follow-up revision after
    initial Phase 6 delivery**, resolving a genuine, independently-
    verified spec deviation (section 23's "Excel/CSV" requirement was
    only half-implemented — see `docs/DECISIONS.md` ADR-020 for the
    full resolution). `parse_excel_rows` (`openpyxl`, `read_only=True`
    streaming, `data_only=True` for formula cells) shares its row-
    validation rules with `parse_csv_rows` via one common
    `_build_import_row` helper, so the two formats cannot silently
    diverge in what they accept. 4 new tests:
    `test_import_excel_file`, `test_import_excel_without_query_column_is_rejected`,
    `test_import_corrupt_excel_file_is_rejected`, and
    `test_import_excel_dedupes_against_existing_csv_import` (proving
    the dedup key works identically across formats — an Excel row and
    a previously-imported CSV row for the same query resolve to the
    same `Query`, not two).
  - Full migration cycle verified via
    `scripts/verify_migration_cycle.sh`: `upgrade head -> downgrade
    base -> upgrade head`, including the `research_reference_type`
    enum rebuild in the downgrade path (rename -> recreate with the
    original Phase 5 value set -> repoint the one column that uses it
    -> drop the temporary type) — confirmed to produce zero
    application tables at the base state and a clean, complete rebuild
    on the way back up. (Adding Excel support required no migration
    change — `QuerySource.EXCEL` already existed since `0007`.)
  - The database was fully dropped and recreated from scratch
    (`DROP DATABASE` / `CREATE DATABASE` / `CREATE EXTENSION vector`)
    and the entire 281-test suite re-run against that from-zero
    database as the final validation step.

- remaining: Products/Offers/Trust (Phase 7), Recommendation Engine
  (Phase 8), WordPress/WooCommerce adapters (Phases 9-10), Rights layer
  (Phase 13), AI visibility (Phase 12) — unchanged by this phase.
  Specific to Query Engine: clustering has no real semantic
  understanding (token-overlap only, see ADR-016);
  `intents.product_id` has no FK until Phase 7; the intent classifier's
  anchor-phrase coverage is a deliberately small seed set, not
  exhaustive — real-world query volume will surface many `DISCOVERED`
  queries needing either rule expansion or manual classification.

## STATUS — Phase 7

- implemented: the Commerce & Product Knowledge foundation — five new
  models across master spec sections 26-30.
  - **`Product` (§26)** carries no price and no stock. Section 27 is
    explicit ("Keep Product and Offer separate"), and one Product
    genuinely can have several simultaneous Offers (different sellers,
    currencies, promotional windows) that a price column could not
    represent. `status` follows KnowledgeObject's DRAFT → IN_REVIEW →
    PUBLISHED → ARCHIVED lifecycle rather than an invented commerce
    one, because §26 states a Product IS "a normalized Product
    Knowledge Object" — so it inherits §44's never-auto-publish
    discipline, enforced by a validated transition table (a direct
    DRAFT→PUBLISHED jump is rejected). `knowledge_object_id` is a
    nullable FK: a product POINTS AT knowledge, never copies it.
  - **`Offer` (§27)** keeps two distinctions the spec's field list
    alone would not force: `stock_quantity IS NULL` ("untracked") is
    not `= 0` ("tracked, none left"), and `price IS NULL` ("price on
    request", a real B2B state) is not zero. Collapsing either would
    silently misrepresent inventory.
  - **`ProductEvidence` (§28)** — `claim` is NOT NULL at the database
    level and required at the schema level, because that column IS the
    evidence-scope mechanism. Uniqueness is on (product, evidence,
    claim), so one lab report can independently support "Grade = A" and
    "no heavy metals" as two separately-verifiable links.
  - **`ProductRelation` (§29)** is its own table rather than an
    extension of Phase 2's `Relationship` — same reasoning recorded in
    ADR-014, plus this one needs a `confidence` column the shared table
    has no equivalent for. Relations are directional and never
    auto-mirrored.
  - **`TrustRecord` (§30)** has no score column of any kind and
    `evidence_id` is NOT NULL. §30's "Do not create a fake trust score
    that has no explainable evidence" is enforced by making an unbacked
    trust assertion structurally unrepresentable. See ADR-024.
  - **Verification is never automatic** for either product_evidence or
    trust_records: both are born UNVERIFIED; only an explicit human
    verify action sets VERIFIED and stamps `verified_at`.
  - Migration `0008` **closes the deferred `intents.product_id` FK**,
    honouring the commitment Phase 6's model docstring and migration
    both recorded in writing. Migration `0007` was not edited.

- **Evidence-scope guarantee, stated precisely (this is the phase's
  central safety claim, so it is worth being exact about what it does
  and does not do):** verifying a Phase 4 `Evidence` row does NOT
  verify the product-level claim that evidence is cited for. A
  VERIFIED, HIGH-strength study about Mannitol, linked to a Taranjabin
  product under the claim "relieves symptom X clinically", produces an
  UNVERIFIED product-evidence link. The system never makes that
  inferential leap itself. **What this does NOT guarantee:** software
  cannot stop a human from typing a false claim and a second human from
  verifying it. What it guarantees is that the leap requires two
  deliberate human acts, both audit-logged with actor and timestamp,
  and never happens as a side effect. Claiming more than that would
  overstate what schema design can achieve.

- tested — against the same real local PostgreSQL 16 + pgvector
  instance used for every phase before this one:
  - **346/346 pytest tests pass** (281 from before + 65 new):
    `test_products.py` (13 — CRUD, per-org sku/slug uniqueness,
    cross-resource tenant validation, the full publication lifecycle,
    and a test proving PATCH cannot change status),
    `test_product_evidence_and_trust.py` (13 **adversarial** tests —
    the Mannitol/Taranjabin case, unscoped-link rejection, independent
    per-claim verification, no-evidence trust rejection, cross-tenant
    trust attempts), `test_offers_and_relations.py` (12 — the
    NULL-vs-0 stock semantics, price-on-request, multiple simultaneous
    offers, non-mirroring of relations), and
    `test_phase7_tenant_isolation.py` (14 — the golden-suite pattern
    continued across all five new tables).
  - Full migration cycle verified via
    `scripts/verify_migration_cycle.sh`: `upgrade head → downgrade base
    → upgrade head`, confirming zero application tables at base and a
    clean rebuild including all five new tables, eight new enum types,
    and the newly-closed `intents.product_id` FK.
  - The database was fully dropped and recreated from scratch and the
    entire 346-test suite re-run against that from-zero database.
  - **No bugs surfaced during this phase's real-database validation.**
    Recorded explicitly, per the precedent set in Phases 3 and 5: the
    project's honest pattern is that real testing usually finds real
    bugs, so a clean run is worth stating plainly rather than leaving
    the absence of a bug report to be inferred.

- remaining: Recommendation Engine (Phase 8), WordPress/WooCommerce
  adapters (Phases 9-10), AI/REST interfaces (Phase 11), AI visibility
  (Phase 12), Rights layer (Phase 13), Dashboard (Phase 14). Specific
  to Commerce: no WooCommerce sync exists yet (`Product.external_id`
  and `ProductProvenance.WOOCOMMERCE` exist so a future sync has
  somewhere to write, but no sync job, mapping table, or
  conflict-resolution policy is implemented — that is Phase 10);
  provenance is per-row rather than per-field; `ProductEvidence.claim`
  is free text with no normalization; and there is no aggregate trust
  view, deliberately (ADR-024) — Phase 8 will have to decide how to
  compare trust across products, and whatever it builds must be an
  internal, documented decision score, never presented as an external
  or authoritative rating.

### Phase 7 post-review hardening

An independent review of the delivered Phase 7 artifact raised three
implementation defects and one packaging defect. All four are fixed;
recorded here rather than folded silently into the original STATUS
section above, because the original section claimed a clean
real-database run and that claim was true — these were behavioural and
packaging gaps that a passing test suite did not catch, which is
exactly the kind of thing worth naming.

1. **Explicit-null PATCH semantics** (`update_product`,
   `update_offer`): `if value is None: continue` made "clear this
   field" a silent no-op returning 200. Fixed — see ADR-026. 6 new
   tests.
2. **`OfferUpdate` was missing `external_id`, `condition`,
   `valid_from`**, making them write-once by accident. Fixed. 1 new
   test.
3. **No IntegrityError handling on offer create/update**: lowering
   `valid_until` below an existing `valid_from` is a plausible edit
   that violates `ck_offers_validity_window_ordered` and escaped as a
   raw database error. Both paths now return a 422 naming the
   constraint. 4 new tests.
4. **`.github/workflows/ci.yml` was absent from delivered ZIPs** — the
   packaging command's `-x "*.git*"` pattern matched `.github` as well
   as `.git`, so the reviewer could not verify CI existed even though
   it did. Packaging fixed; CI file itself was never missing from the
   repository.

Also corrected: `app/models/offer.py`'s docstring referred to a
non-existent `offer_service` module (the implementation lives in
`commerce_service`) — harmless to run, but misleading to a future
reader or coding agent.

**Result after hardening: 346/346 tests pass** (333 + 13 new), full
migration cycle re-verified, from-scratch database re-validated.

## STATUS — Phase 8

- implemented: the Recommendation Engine — CustomerContext (§32),
  Recommendation (§33), response-mode policy (§34), and the
  cross-domain read contract that makes the whole thing possible.
  - **`app/contracts/commerce.py` is the architectural centrepiece**,
    and it is owned by the COMMERCE domain, not by Recommendation
    (ADR-027). Phase 8 never imports Phase 7's ORM models and never
    writes a `select()` against `products`/`offers`/`product_evidence`/
    `trust_records`. Two Commerce business rules live in the contract
    where they belong: what counts as recommendable (PUBLISHED only)
    and what counts as purchasable (in stock/preorder/backorder, within
    validity window, and `stock_quantity IS NULL` meaning UNTRACKED
    rather than zero).
  - **Hard gates are structurally separate from soft signals.** A gate
    is a permission fact (wrong tenant, unpublished product, withdrawn
    consent, nothing purchasable) and NO score can overturn one,
    because gates run first and ineligible products never reach
    scoring. This is the structural answer to commercial bias: a
    profitable but irrelevant or unpublished product cannot buy its way
    in, since profitability is a soft signal and soft signals only
    order products that have already passed.
  - **UNKNOWN is not NEGATIVE** — the phase's most important semantic.
    Every evidence/trust signal carries a `SignalState` alongside its
    score (ADR-028). No evidence => UNKNOWN, scoring the neutral 0.5.
    Rejected evidence => NEGATIVE, scoring 0.1. The invariant is tested
    directly: a product with no evidence at all scores strictly higher
    than one whose claims were reviewed and rejected. Without this, a
    brand-new honest product would rank below one whose merchant
    uploaded paperwork nobody verified.
  - **Unverified claims buy nothing.** Five unverified product claims
    produce `evidence_state == "unknown"` and the neutral score, exactly
    as zero claims would — tested.
  - **Abstention is a first-class result.** EDUCATE and REASSURE modes
    produce NO_RECOMMENDATION no matter how good the catalogue is
    (§34: "Do not push products when the user's intent does not justify
    it"). So does a withdrawn-consent context, an empty catalogue, and
    a catalogue where nothing passes eligibility. All return HTTP 200 —
    declining is a successful answer, not an error.
  - **Rejections are returned, not discarded.** The response carries a
    `rejected` list with the named gate and a human-readable reason for
    every candidate that didn't make it, so "why NOT that product" is
    answerable. A pipeline that silently drops rejects structurally
    cannot answer it.
  - **`reason` is structured JSONB** (ADR-031), not prose: every
    signal's score, state and detail, plus caveats and policy version.
  - **Reproducibility**: `policy_version` is stamped on every row
    (ADR-029), ordering is deterministic (score, then product id as a
    stable tiebreak), and the policy module is pure functions with no
    I/O — so a past decision stays explainable after the weights change.
  - **Privacy**: CustomerContext stores no conversation transcript by
    design (§32) — `source` records the CHANNEL, never what was said.
    A fully anonymous context works. `withdraw-consent` clears identity
    fields and acts as a hard gate, not a ranking penalty.
  - Migration `0009`. No prior migration modified; Phase 7's tables are
    referenced by FK only.

- **Phase 7 correction made during this phase** (as instructed, rather
  than left as debt): Phase 7 had no contract surface, so any
  cross-domain consumer would have had to reach into its tables
  directly. `app/contracts/commerce.py` adds that surface **without
  changing a single Phase 7 semantic, model, or endpoint** — all 346
  Phase 0-7 tests still pass unchanged.

- tested — real local PostgreSQL 16 + pgvector:
  - **403/403 pytest tests pass at the time of the Phase 8 report** (346 + 57; later raised to 415 by the hardening below):
    `test_recommendation_policy.py` (26 pure unit tests, no DB — the
    UNKNOWN-vs-NEGATIVE invariants, gate impermeability, offer
    semantics, determinism), `test_recommendations.py` (19 integration
    and adversarial — draft product with verified evidence rejected,
    excellent-but-out-of-stock rejected, withdrawn consent blocking
    everything, unverified claims buying nothing, no-evidence
    outranking rejected-evidence), `test_phase8_tenant_isolation.py`
    (12 — including the two-hop case where Tenant B's heavily-verified
    evidence must not raise Tenant A's product's score).
  - One real bug found and fixed during test development: with
    `persist=False` the Recommendation objects were never flushed, so
    `id` and `created_at` were null and serialisation failed. Both
    paths now assign them explicitly. Recorded rather than quietly
    fixed, per this project's precedent.
  - Full migration cycle verified (`base → head → base → head`), and
    the entire suite re-run against a from-scratch database.

- remaining: WordPress (9), WooCommerce (10), AI/REST (11), AI
  Visibility (12), Rights (13), Dashboard (14). Specific to
  Recommendation: weights are untuned judgments; relevance is
  exact-match only (no semantic matching until a real embedding
  provider exists); domain boundaries are convention rather than
  lint-enforced; there is no feedback loop, so "is this policy any
  good?" is not answerable from inside the system yet.

## Phase 7 / Phase 8 post-review hardening — the two-layer verification invariant

An independent review found a defect more serious than anything the
original Phase 7 report identified, and the test suite did not catch it
because **the tests encoded the defective behaviour as correct**. That
is worth stating plainly: 346 passing tests did not make the
implementation right.

**The defect.** `ProductEvidence.verification_status` and
`TrustRecord.verification_status` could be VERIFIED while the
`Evidence` row beneath them was DRAFT or REJECTED. Nothing compared the
two. A recommendation engine reading only the link's own flag would
count a rejected study as verified support for a product claim —
exactly what sections 28 and 30 exist to prevent.

**The fix (ADR-032), enforced at two layers because neither suffices
alone:**

1. **Write time** — `verify_product_evidence` / `verify_trust_record`
   refuse to mark anything verified on top of unverified Evidence,
   returning 422 that names the Evidence's actual status.
2. **Read time** — `contracts/commerce.py` recomputes effective
   verification on every read by joining Evidence. This is the layer
   that catches the case a write-time check structurally cannot: the
   Evidence being rejected *after* the link was legitimately verified.

Either side being REJECTED makes the whole assertion rejected.

**Four existing tests were changed** because they asserted the old
behaviour (verifying links without ever verifying the Evidence
underneath). Those are behavioural corrections, listed here rather than
folded in silently:
`test_same_evidence_can_support_two_different_claims_independently`,
`test_verification_can_be_revoked_and_clears_verified_at`,
`test_verified_trust_is_filterable_so_trust_is_enumerable_not_scored`,
`test_verified_evidence_outranks_no_evidence`. Their helpers now verify
the Evidence first, which also makes the Mannitol/Taranjabin adversarial
test *stronger*: it now proves that even a fully VERIFIED study does not
verify the product-level clinical claim it is cited for.

**A claim from the earlier report is corrected.** It described an
"evidence scope guarantee". That was too strong. The accurate
formulation, now tested in `test_same_tenant_semantic_scope.py` and
recorded in ADR-033, is: **evidence scope is explicit and auditable,
not semantically guaranteed.** Within one organization, Product B's lab
report can be attached to Product A — every tenant check passes,
because it is a same-tenant semantic question the schema cannot answer.
What the system does guarantee is that the pairing is explicit, never
inferred, never auto-verified, and always attributed.

**Also recorded, not changed:** `Product`'s DRAFT → IN_REVIEW →
PUBLISHED lifecycle is an engineering policy derived by inference from
section 26's "normalized Product Knowledge Object", not a literal spec
mandate (ADR-034); `TrustSubjectType` is an MVP vocabulary that must
stay extensible (ADR-035); and database-level tenant integrity remains
incomplete — composite FKs would close it for the non-polymorphic
relationships but touch five tables across two frozen phases and
deserve their own reviewed migration (KNOWN_ISSUES).

**Result: 415/415 tests pass** (403 + 12 new: 8 invariant tests
including the post-hoc revocation case, 4 same-tenant scope tests).
Full migration cycle re-verified; from-scratch database re-validated.


## STATUS — Phase 9 (Core-side adapter boundary)

**Phase 9 is NOT complete.** Master spec §38's first line is literally
*"Create a WordPress plugin: ai-operating-layer"*, and lists nine
responsibilities for it. That plugin does not exist — `plugin/` holds a
32-line stub. What follows is the Core-side half of the phase; the
plugin half is outstanding, and Phase 9 remains **CONDITIONAL** until it
is built and verified. Phase 9 has deliberately NOT been split into
9a/9b: the Master Spec defines it as one phase and that definition
stands.

### Implemented (Core side)

- **Generic machine identity** (ADR-036): `Installation` +
  `InstallationCredential`. `AdapterType{wordpress,rest,mcp,other}`
  makes WordPress one value rather than the model, so an MCP adapter
  reuses this rather than needing a second identity system. Tenant
  resolves `credential → installation → organization` and is **never**
  accepted from a request — no Phase 9 request schema has an
  `organization_id` field.
- **`wordpress_mappings` is adapter state** (ADR-038), the only place a
  WordPress concept exists in the codebase. Idempotency is enforced by
  unique constraints, not handler logic.
- **Tenant-aware rate limiting** (ADR-039), ordered after identity and
  before Core work.
- **A3 closed at SQL level** (ADR-037): migration `0010` replaces eight
  single-column FKs with composite ones.
- **`DEBT_REGISTER.md`** introduced (ADR-040).

### Test results — exact, from a real run

```
pytest -q  ->  456 passed, 0 failed
```

Arithmetic, stated precisely because an earlier report got it wrong:

| Component | Count |
|---|---|
| Phase 8 hardened baseline | 415 |
| `test_phase9_machine_identity.py` | 22 |
| `test_sql_level_tenant_integrity.py` | 6 |
| B3 test appended to `test_recommendation_policy.py` | 1 |
| Subtotal | 444 |
| `test_redis_down_failopen.py` (added after the count correction) | 12 |
| **Verified total** | **456** |

An earlier report quoted "443 prior + 28 new", which sums to 471 and is
wrong twice over: 443 was an *intermediate* run taken before the B3
test existed, and it was mislabelled as the baseline. The real baseline
is 415. At the time of that report the true total was 444; it is now 456 after
the fail-open tests were added.

### Fail-open rate limiting — the trade-off, and its evidence

The limiter fails open when Redis is unreachable (ADR-039). That is a
deliberate availability-over-enforcement choice, and the conditions it
must satisfy are now tested rather than merely asserted
(`test_redis_down_failopen.py`): with Redis unavailable, requests
proceed, but **authentication, tenant derivation, and authorization are
all still enforced**, because each of them runs before and independently
of the limiter. Redis degradation is surfaced by `/health/ready` and
logged by the limiter.

### Outstanding for Phase 9

- **The WordPress plugin itself** — §38's nine responsibilities.
  Blocking; Phase 9 cannot be APPROVED without it.
- No webhook signature verification (only needed once the plugin sends
  WordPress-initiated events).

## Phase 9 — plugin implementation (completing the phase's second half)

The earlier Phase 9 STATUS section covered the Core-side boundary and stated
plainly that the plugin did not exist. It does now.

### What was built

21 PHP files under `plugin/ai-operating-layer/`:

| §38 responsibility | File | Status |
|---|---|---|
| authentication | `includes/class-aiol-credentials.php` | IMPLEMENTED |
| connection to Cloud Core | `includes/class-aiol-client.php` | IMPLEMENTED |
| content sync | `includes/class-aiol-hooks.php` | IMPLEMENTED |
| product sync | `includes/class-aiol-hooks.php` | IMPLEMENTED |
| schema rendering | `includes/class-aiol-schema.php` | IMPLEMENTED |
| WordPress hooks | `includes/class-aiol-hooks.php` | IMPLEMENTED |
| WooCommerce hooks | one identity hook only | PARTIAL — bounded by ADR-041 |
| status reporting | `includes/class-aiol-status.php` + admin views | IMPLEMENTED |
| cache | `includes/class-aiol-cache.php` | IMPLEMENTED |

One Core addition was required: `GET /adapter/catalog/{id}` (ADR-042),
because §38 mandates schema rendering and no read surface existed —
`AdapterScope.CATALOG_READ` was defined but unreachable.

### Three design decisions worth stating

**Schema rendering fails to silence, not to fallback.** If Core is
unreachable, no JSON-LD is emitted. Absent markup is merely uninformative;
stale markup is a false public claim about price or availability that a
merchant can be held to. The null-price/untracked-stock distinctions Phase 7
was careful about survive all the way into the rendered output — a missing
price is omitted, never rendered as `0`.

**Status is never collapsed into one indicator.** Each dependency reports
separately and the overall state is the worst of its parts. When Core's
Redis is down, the panel says Redis *and* rate limiting are degraded, because
ADR-039's fail-open policy means the system genuinely is working and
genuinely is missing a protection — both halves need saying.

**The design system extends WordPress admin rather than replacing it**
(ADR-043). The repo had zero CSS before this phase, so one was defined, but
deliberately small. The external Gold Standard reference's GSAP/WebGL/scroll
techniques were assessed and rejected for an admin settings screen; its
anti-pattern discipline was adopted in full (SVG not emoji, focus never
removed, colour never the only signal, reduced-motion respected).

### Test results — exact

```
Core:   pytest -q          ->  464 passed, 0 failed
Plugin: bash tests/run.sh  ->  68 assertions passed + php -l clean on 21 files
Total:  532
```

Reconciliation from the previous 456: +8 `test_adapter_catalog.py` = 464
Core; the 68 PHP assertions are new and were not in any prior count.

Migration cycle re-verified: `base -> head -> base -> head`.
The plugin suite was additionally re-run **from the extracted release ZIP**,
not only the working copy.

### ENVIRONMENT BLOCKED — stated precisely

- **No WordPress install.** Hooks firing, nonce/capability enforcement,
  admin rendering and `wp_remote_request` are unverified. The 68 tests cover
  every pure-logic path; they do not cover WordPress integration.
- **No browser.** Puppeteer installed; its Chrome download host is outside
  the network allow-list and the apt chromium candidate is a snap.
  No screenshot was taken and no rendered measurement was made (ADR-044).
  `tests/visual/` ships a harness that *measures* overflow, clipping,
  text size, target height and focus rendering — reproducible in ~2 minutes
  with network access.

### The one unresolved spec ambiguity

§38 lists "WooCommerce hooks" under Phase 9; §40/§62 assign WooCommerce to
Phase 10. Phase 9 implements identity projection only and builds no
`commerce_mappings`, order, cart or price sync (ADR-041). If the intent was
deeper Woo behaviour, that decision is yours and should be made before
Phase 10.

## Phase 9 — AI Access Toolkit absorption

The legacy AI Access Toolkit (25 files, 2,069 PHP LOC, 13 classes) has been
absorbed. It is not a separate product and does not persist as one.
Classification of all 23 capabilities:
[`AI_ACCESS_TOOLKIT_CAPABILITY_MAP.md`](ai-context/AI_ACCESS_TOOLKIT_CAPABILITY_MAP.md).

| Class | Count |
|---|---|
| REUSE | 2 |
| REFACTOR | 13 |
| REPLACE | 6 |
| DEPRECATE | 1 |
| DEFER (Phase 12) | 1 |

### The three capabilities that were replaced, not migrated

These are where the legacy plugin and this architecture genuinely disagreed.

**Structured data (ADR — see schema class).** The legacy module assembled
product schema from WordPress data. That path could publish an unverified
value as a public schema.org assertion. Replaced by `AIOL_Schema`, which
renders only what Core asserts, omits a missing price rather than rendering
`0`, and emits nothing at all when Core is unreachable.

**The AI Gateway (ADR-048).** 274 lines implementing a parallel canonical
API with its own keys, its own per-IP rate limiter and its own content
contract — three responsibilities Core already owns. **The plugin now
registers no REST routes at all**, asserted by test. Its transport role
survives as `/llms.txt` and `?aiol_format=md`, which serve WordPress's own
published content and claim no authority.

**The AI Readiness Score (ADR-047).** A single 0–100 number that could not
distinguish "checked and fine" from "could not check", implied a
relationship to real AI visibility that was never measured, and told a
merchant nothing actionable. Replaced by seven named dimensions; the five
the adapter genuinely cannot measure report UNKNOWN rather than a
fabricated zero.

### Capabilities that improved during absorption

- **Actor detection (ADR-046).** "AI bot" became six actor types with four
  confidence levels. `ChatGPT-User` is now correctly an *AI answering a
  user*, not a crawler. Nothing is ever marked VERIFIED, because
  verification is not implemented — a test enforces that.
- **Privacy narrowed.** No IP address is stored anywhere (a test greps the
  whole plugin for `REMOTE_ADDR`), no query strings, humans not logged, log
  cap 300 → 200.
- **Diagnostics gained UNKNOWN.** An unreachable robots.txt reported FAIL
  in the legacy plugin. It now reports "could not determine".
- **Invalidation widened (ADR-049).** Unpublishing a post left it listed in
  llms.txt until the cache expired; `transition_post_status` and
  `untrashed_post` now invalidate too.
- **HTTPS enforced for credentials (ADR-045).** Plain `http://` is refused
  except for an exactly-matched local host — `localhost.attacker.com` is
  refused, and a test asserts that bypass fails.

### Test results — exact

```
cloud-core:       pytest -q         ->  464 passed, 0 failed
wordpress-plugin: bash tests/run.sh ->  absorption: 42 · schema: 23 ·
                                        security: 33 · status: 12  = 110
                                        php -l clean across 26 files
migration:        base -> head -> base -> head  verified
```

The 42 absorption assertions are split deliberately between **positive**
(retained capability still works) and **negative** (replaced capability is
*provably absent*). The negative ones matter more: a capability map is a
claim, and those assertions are its evidence.

### One bug the tests caught

`AIOL_Actors::classify()` used `\b(crawler|spider|scraper)\b`, which fails
on `SomeRandomCrawler/1.0` — the concatenated form most crawler UAs actually
use. Fixed to a substring match for those tokens while keeping the word
boundary on `bot`, which needs it (otherwise "robot" and "abbot" match).
Recorded rather than silently corrected.

### Still ENVIRONMENT BLOCKED

Nothing in the absorption changes this: the plugin has never run inside
WordPress, and no pixel has been rendered. The 110 assertions cover pure
logic only.

## STATUS — Phase 10 (WooCommerce adapter)

### Phase 9 forensic reconciliation (performed first, as required)

Three real defects were found, all missed by Phase 9's own test suite:

| ID | Finding | Fix |
|---|---|---|
| **R1** | `aiol_mapping_changed` was listened for but **never fired anywhere** — a dead hook. ADR-049's claim that mapping changes invalidate representations was false. | Hook now fired on link-change and unlink; regression test asserts it is *fired*, not merely listened for (ADR-053) |
| **R2** | No `do_action` existed in the admin or hooks classes at all — corroborating R1 | Resolved with R1 |
| **R3** | `$this->cache::flush_all()` — legal PHP but misleading about ownership | Explicit static call |
| **P9-R1** | §38/§40 WooCommerce boundary was recorded as unresolved | **Resolved** by ADR-050 |

The R1 lesson generalises: nothing tested the *wiring* between publisher and
subscriber, so a hook that was never called passed every test.

### Implemented

- **`commerce_mappings`** (§40) and **`sync_jobs`** (§41), migration `0011`.
  Both born with composite tenant FKs (ADR-037) rather than retrofitted.
- **The directional rule** (ADR-050): WooCommerce writes price/stock/
  availability and nothing else. There is no adapter route to Product
  identity, status, evidence, trust or recommendations.
- **`UNIQUE NULLS NOT DISTINCT`** (ADR-052) so two simple products cannot
  claim the same Woo ID while a simple product and a variation still
  coexist.
- **`DEAD_LETTER`** (ADR-051) so "stopped retrying" is distinguishable from
  "will retry".
- **`AIOL_WooCommerce`** plugin class with the same recursion/dedup guards as
  `AIOL_Hooks`, and graceful degradation: if Core is unreachable, WooCommerce
  keeps selling. A shop that cannot transact because a knowledge service is
  down would be catastrophic coupling.

### Semantics preserved end-to-end

`manage_stock=false` → `stock_quantity=null` (untracked), never 0.
Empty price → `null` (on request), never 0. Managed 0 **with** backorders →
`backorder`, not `out_of_stock`. Each was stored in Phase 7, scored on in
Phase 8, rendered publicly in Phase 9 — collapsing any of them here would
have undone all three, so each has its own test.

### Test results — exact

```
cloud-core:       pytest -q         ->  483 passed, 0 failed
wordpress-plugin: bash tests/run.sh ->  absorption 46 · schema 23 · security 33
                                        status 12 · woocommerce 30  = 144
                                        php -l clean, 27 files
migration:        base -> head -> base -> head verified (0011 applied)
PostgreSQL:       16.15 - NULLS NOT DISTINCT supported
```

Reconciliation: 464 (Phase 9) + 19 Phase 10 Core = **483**. Plugin 110 + 30
WooCommerce + 4 reconciliation regressions = **144**. Total **627**.

### One test bug caught and fixed

`test-woocommerce.php` first grepped raw source for `verify` and failed on
the class docstring *explaining* that the adapter cannot verify. Replaced
with `token_get_all()`-based comment stripping so the assertion runs against
executable code only — the rigorous version.

### ENVIRONMENT BLOCKED — unchanged and still blocking

- **No WooCommerce install.** `woocommerce_update_product`,
  `woocommerce_product_set_stock`, variation handling and real
  `wc_get_product()` behaviour are **unverified**. `map_offer_state()` is
  tested as a pure function against synthesised WooCommerce state; it has
  never seen a real product object.
- **No WordPress install.** Unchanged from Phase 9.
- **No browser.** Unchanged from Phase 9.

### Phase 10 hardening (post-review)

**Bulk-sync guard (ADR-054).** The P0 gap: inline offer sync would issue one
HTTP call per product during a bulk import. Now budgeted at 20 per request,
with the remainder persisted and drained by cron. Both properties tested —
it stops, and it does not lose work.

**Wiring-integrity test (ADR-055).** Generalises R1 from "one dead hook
fixed" to "dead hooks cannot survive": every custom `aiol_*` hook must have
a publisher and a subscriber, and every array callback must name a real
method.

**Mutation testing** was used to verify the guards are load-bearing rather
than decorative:

| Mutation | Result |
|---|---|
| Comment out `do_action('aiol_mapping_changed')` (re-create R1) | wiring 2/8 FAILED ✅ |
| `should_defer()` always returns false | bulk-guard 3/17 FAILED ✅ |
| Defer without persisting (silent loss) | bulk-guard 4/17 FAILED ✅ |
| Remove the guard's call site | bulk-guard 1/17 FAILED ✅ |

**The wiring test failed its own first mutation test.** It scanned raw
source, so a commented-out `do_action` counted as a publisher — it could not
have caught R1. Fixed with tokenizer-based comment stripping. Recorded
because "the test passes" and "the test would fail if the bug returned" are
different claims.

**WooCommerce contract harness.** `map_offer_state()` was tested against
synthesised arrays, which proves the mapping but not the wiring to
WooCommerce's object API — a typo'd `get_stock_quanity()` would pass every
array test. A `Fake_WC_Product` returning WooCommerce's **real** return
types now drives the adapter's actual read path, pinning the method names
and catching the `''` price trap (`(float) '' === 0.0` would publish "free").

### Test results after hardening — exact

```
cloud-core:       pytest -q          ->  483 passed, 0 failed
wordpress-plugin: bash tests/run.sh  ->  absorption 46 · bulk-guard 17 · schema 23
                                         security 33 · status 12 · wiring 8
                                         woocommerce 30 · woocommerce-contract 24
                                         = 193 assertions, php -l clean (29 files)
migration:        base -> head -> base -> head verified
```

**676 total** (483 Core + 193 plugin).

## STATUS — Phase 11 (AI/REST interfaces)

### Phase 10 forensic reconciliation (performed first)

| Check | Result |
|---|---|
| §51 request IDs, structured errors | **Present** (`core/errors.py`) |
| §51 pagination, filtering, versioning | **Present** |
| **§51 sorting** | **MISSING across all 98 routes** — real gap, unnoticed since Phase 1 (ADR-056) |
| Phase 10 routes reachable | **5 registered**, verified by introspecting the live app |
| GET routes leaking raw models | **0** — every one has a `response_model` |
| Python-side dead wiring (the R1 class) | **Clean** — Celery task defined *and* dispatched; no orphaned enums |

The R1 discipline was applied to Core, not just the plugin: scanning for
defined-but-never-dispatched tasks and declared-but-never-referenced enums.
Core came back clean, which is worth stating because it was not assumed.

### Implemented

- **Sorting (ADR-056)** — closes the §51 gap. Allow-list validated;
  unknown field is a 422 naming the permitted values, never a silent
  fallback.
- **`/api/v1/ai/*`** — the agent-facing read interface: `knowledge/{id}`,
  `products/{id}/trust`, `ask`, `capabilities`.
- **`coverage` on every response (ADR-057)** — the Phase 8
  UNKNOWN-vs-NEGATIVE rule carried across the system boundary, which is
  where the claim actually gets repeated to a person.
- **Capability manifest (ADR-058)** — the seam an MCP server would wrap.
  §63 says MCP is future/secondary, so no MCP server was built.
- **No score leaves the building (ADR-059)** — rank position and states
  only, asserted by test.

### Structural guarantees, not conventions

- **Read-only:** no `ai:write` scope exists, and no `PUT`/`PATCH`/`DELETE`
  route exists under `/ai` — asserted by a test that introspects the router.
- **Two-layer verification reaches the edge:** `/trust` reuses
  `commerce_contract.get_trust_summaries()` rather than querying
  `TrustRecord` directly, so ADR-032's rule has exactly one implementation.
  A trust record verified over *unverified* evidence is not listed.
- **Abstention is a 200:** `answerable: false` is a complete answer. An
  interface that cannot refuse will always suggest something.

### Test results — exact

```
cloud-core:       pytest -q          ->  504 passed, 0 failed
wordpress-plugin: bash tests/run.sh  ->  193 assertions, php -l clean
migration:        base -> head -> base -> head verified
```

483 + 21 Phase 11 = **504 Core**. **697 total.**

### ENVIRONMENT BLOCKED — unchanged

No WordPress, no WooCommerce, no browser. Phase 11 is Core-only, so it adds
no new blocked items — but it does not clear any either.

## Phase 11 close-out

### P11-sort-rollout — CLOSED

39 of 41 collection routes; 2 documented exclusions asserted by test.
Route inventory corrected: **150** `/api` routes, not 98 (the earlier
figure counted unique paths, not method×path).

### Regression found by the close-out run

The rollout introduced **5 route-wiring defects**, all found by running the
full suite *after* the last change rather than trusting the earlier green
result:

- 2 routes passed `sort=sort` without accepting it → `NameError` 500
- 3 routes accepted `sort` and silently dropped it → 200 with default order

Additionally, a `git checkout` used to undo a mutation test reverted more
than intended and had to be repaired — noted because it is a real hazard
when mutation-testing a file with uncommitted work.

### Test results — exact, after the final change

```
cloud-core:       pytest -q          ->  529 passed, 0 failed
wordpress-plugin: bash tests/run.sh  ->  193 assertions, php -l clean
migration:        base -> head -> base -> head verified
```

504 + 25 sorting = **529 Core**. **722 total.**

### Mutation results — 6/6 caught

| Mutation | Tests failed |
|---|---|
| Allow-list bypassed | 7 |
| Silent fallback instead of 422 | 7 |
| Stable tiebreak removed | 1 |
| `sort_dir` ignored | 4 |
| `secret_hash` added to allow-list | 1 |
| Route drops `sort` (the new regression class) | 3 |

### MarkItDown

Audited separately: **NOT IMPLEMENTED** (`docs/audits/MARKITDOWN_AUDIT.md`).
Not a Phase 11 defect — it is deferred Phase 3 ingestion work, and
MarkItDown appears nowhere in the Master Spec. No code was written for it.

### ENVIRONMENT BLOCKED — unchanged, none cleared

WordPress runtime · WooCommerce runtime · WC_Product behaviour · variation
handling · currency resolution · WordPress hooks · WP-Cron runtime ·
browser/visual verification · RTL visual verification.

Phase 11 is Core-only and clears none of these.

## STATUS — Phase 12 (AI Visibility, §31)

### Forensic reconciliation (performed first)

| # | Check | Result |
|---|---|---|
| F1 | Dead wiring in Core | CLEAN |
| F2 | Unregistered routers | CLEAN — 20/20, 150 routes |
| F3 | Query/Intent/QueryGroup reusable | PRESENT — referenced, never duplicated |
| F4 | `SyncJobType` reusable | commerce-only; Phase 12 has its own status enum |
| F5 | Composite tenant-FK pattern | established; adopted at creation |
| F6 | Rate limiting | present |
| **F7** | **Cost / budget guard** | **ABSENT — the material finding** |
| F8 | `AdapterScope` extensible | yes |

### Implemented

- **`visibility_tests`** (§31 table name kept for spec fidelity; rows are
  *observations*) and **`visibility_budgets`**, migration `0012`.
- **Tri-state signals (ADR-061)** — NOT_CHECKED ≠ ABSENT.
- **Click and Purchase deliberately absent (ADR-062)** — unobservable from
  a platform response.
- **Budget guard (ADR-063)** — closes F7; checked before the probe;
  missing budget means zero, not unlimited.
- **Summary without a score (ADR-064)** — counts, honest denominator,
  caveats.
- Migration `0012` also adds `uq_queries_id_organization_id`, which
  migration 0010 had not needed; it is what lets `visibility_tests` carry a
  composite tenant FK.

### Two defects found during the phase

**Cross-tenant reference escaped as a 500.** The composite FK fired
correctly — it is the real guarantee — but the service let the
`IntegrityError` propagate, which told an API caller nothing and looked
like a server fault. Now validated in the service for a clean 404, with the
constraint underneath as backstop.

**Mutation M6 was not caught by the first test suite.** Flipping the
model's signal default from NOT_CHECKED to ABSENT passed all 28 tests,
because the Pydantic schema always supplies an explicit value and the
column default was never exercised. That left the real database default
unguarded: a direct service call or raw INSERT would have silently produced
fabricated "absent" findings. Two tests now exercise the ORM default and
the DDL `column_default` directly.

### Test results — exact, after the final change

```
cloud-core:       pytest -q          ->  559 passed, 0 failed
wordpress-plugin: bash tests/run.sh  ->  193 assertions, php -l clean
migration:        base -> head -> base -> head verified (0012 included)
```

529 + 30 Phase 12 = **559 Core**. **752 total.**

### Mutation results — 7/7 caught

| Mutation | Tests failed |
|---|---|
| NOT_CHECKED treated as ABSENT | 2 |
| Denominator inflated to all observations | 2 |
| Budget guard removed | 4 |
| Missing budget defaults to unlimited | 5 |
| Tenant filter removed from summary | 1 |
| Signal default flipped to ABSENT | 1 *(after the gap was closed)* |
| `tested_at` overwritten with now() | 1 |

### Deliberately NOT built

No platform provider adapters, no scheduled monitoring worker, no SERP
scraping, no competitor discovery, no MCP. §31 defines the observation
record; automated collection needs provider credentials and terms review
that do not exist here. `collection_method` defaults to MANUAL_PASTE
precisely because that is the honest expectation today.

### MarkItDown

**NOT IMPLEMENTED** (`docs/audits/MARKITDOWN_AUDIT.md`). Phase 12 records
this and builds no parallel parser, per its own §32.

### ENVIRONMENT BLOCKED — none cleared

WordPress runtime · WooCommerce runtime · `WC_Product` · variations ·
currency resolution · WordPress hooks · WP-Cron · browser/visual · RTL.
No platform API was called; no observation in this codebase came from a
real AI platform.

## Phase 3 Document Intelligence — completed retroactively

The Phase 0–12 audit found the document chain entirely unimplemented
(G1–G10): `Document.content` accepted plain text from a JSON body, and
nothing else existed. It is the backbone of §60's architecture, so it was
built rather than deferred — and it was buildable, because MarkItDown and
tesseract both install in this environment.

### What MarkItDown does and does not do (measured, ADR-065)

| Capability | MarkItDown 0.1.7 | Our layer |
|---|---|---|
| PDF/DOCX/XLSX → text | **works** | — |
| DOCX/XLSX tables | **works** | — |
| Persian / mixed script | **works** | — |
| **PDF tables** | **flattens them** | pdfplumber, `lines`→`text` |
| **PDF embedded images** | **silently drops them** | pypdf |
| **OCR of images** | **0 chars returned** | tesseract, Level 3 |
| **Malformed PDF** | returns the string `"None"` | guarded → `EMPTY` |

### Implemented

`app/ingestion/` — `converter.py` (boundary + MarkItDown), `extractors.py`
(tables/images/OCR, bounded), `pipeline.py` (canonical artifact assembly).
`ingestion_service.py` — validation, quarantine, dedup. Migration `0013`:
`document_conversions`, `document_tables`, `document_assets`.
Endpoints: `POST /documents/upload`, `GET /documents/{id}/markdown`,
`GET /documents/{id}/artifacts`.

**Machine representations (ADR-067):** `/knowledge/{id}/markdown`,
`/representation`, `/jsonld`, all from the canonical Knowledge Object.

### Two weak tests that mutation testing exposed

**D9** — my traversal test asserted
`safe_extension("../../etc/passwd.pdf") == ".pdf"`, which is true whether or
not the guard exists, because `Path.suffix` already ignores directories. It
**could not fail**. Replaced with a behavioural test that uploads a
traversal filename and asserts nothing is written outside quarantine.

Earlier, **M6** in Phase 12 had the same shape: the schema always supplied a
value, so the column default was never exercised.

Both are the same lesson: *a test that cannot fail is not a test.*

### Test results — exact, after the final change

```
cloud-core:       pytest -q          ->  598 passed, 0 failed
migration:        base -> head -> base -> head verified (0013 included)
```

559 + 31 document intelligence + 8 representation = **598 Core**.

### Mutation results — 9/9 caught

malformed guard (3) · table extraction (7) · image extraction (3) ·
unreadable-image declaration (1) · magic bytes (1) · extension allow-list
(1) · dedup version (1) · OCR provenance (1) · quarantine naming (1, after
the weak test was replaced).

**All mutation restores used isolated file backups. No Git operation was
used** (§0.2) — the Phase 11 incident where `git checkout` reverted
unrelated work is not repeated.

### Deliberately NOT built

Level 4 vision interpretation · scanned-page full-page OCR · original file
retention (bytes are discarded after conversion; `storage_path` is NULL) ·
async ingestion via Celery (upload is synchronous) · benchmark corpus at
50/200/1000 documents. Each has an owner in the debt register.

## Phase 12 — P12-18 / P12-19 closeout

### Implemented
Visibility Project/Run/Snapshot/Competitor/Event (migration 0015), provider
boundary at `app/integrations/visibility/`, async run execution via the
canonical `SyncJob`, snapshot and event derivation, sample-based rates with
denominators. Search intelligence: `SearchObservation` (append-only),
Search Console + SERP provider boundaries with realistic fixtures,
normalization reusing Phase 6.

### Verification levels — kept explicitly distinct

| Level | Result |
|---|---|
| **Unit / contract** | 46 tests (23 P12-18 + 23 P12-19) |
| **Fixture-level E2E** | route → service → fixture provider → observation → snapshot → event |
| **REAL Celery + Redis runtime E2E** | **PASS** — dispatch through Redis to a live worker; `visibility.execute_run` received and succeeded; 2 observations, 1 snapshot, 1 event persisted; redelivery returned `repeated: True` with no duplicates |
| **Live AI provider execution** | **ENVIRONMENT BLOCKED** — no platform credentials |
| **Live Search Console / SERP execution** | **ENVIRONMENT BLOCKED** — no Google credentials |

The fixture provider exercises the runtime chain; it does **not** prove
live provider access, and every fixture observation carries `is_fixture=True`
so the two can never be confused in stored data.

### Test results — exact

```
python -m pytest -q          ->  759 passed, 0 failed  (314.08s)
migration cycle              ->  base -> head -> base -> head (0015, fresh DB)
mutation (P12-18/19)         ->  9/9 caught
real Celery+Redis E2E        ->  PASS
```

### One test defect found and fixed

The sort-wiring test flagged the new visibility routes: they pass `sort`
positionally to `apply_sort(...)` rather than as a keyword, and the check
only looked for keywords. Relaxed to detect either form — then re-verified
that a genuinely dropped `sort` still fails it (3 failures), so it was not
weakened into uselessness.

