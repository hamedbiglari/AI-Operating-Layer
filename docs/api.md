# API

Base path: `/api/v1` (configurable via `API_V1_PREFIX`).

## Health endpoints (Phase 0, revised Phase 1)

| Method | Path                | Description                                              |
|--------|---------------------|-----------------------------------------------------------|
| GET    | `/`                 | Service banner (name/env/api prefix)                       |
| GET    | `/api/v1/health/live`  | Liveness only — never touches the database               |
| GET    | `/api/v1/health/ready` | Readiness — checks the database, returns 503 if degraded |
| GET    | `/api/v1/health`      | Legacy alias for `/health/ready` (kept for compatibility) |

Every response includes an `X-Request-ID` header (generated, or echoed
back if the caller supplied a valid one — see `app/core/middleware.py`
for the validation rules).

## Authentication (Phase 1)

| Method | Path                              | Auth required | Description                                    |
|--------|-----------------------------------|----------------|-------------------------------------------------|
| POST   | `/api/v1/auth/register-organization` | none        | Bootstrap a new tenant: creates Organization + OWNER user |
| POST   | `/api/v1/auth/login`              | none           | OAuth2 password flow (`username`=email, `password`) → JWT |
| GET    | `/api/v1/auth/me`                 | bearer token   | Current user + their organization                |

`POST /auth/login` uses `application/x-www-form-urlencoded` (standard
OAuth2 password grant), not JSON — this is what makes the Swagger UI
"Authorize" button work out of the box.

## Organizations (Phase 1)

| Method | Path                       | Auth required        | Description                    |
|--------|----------------------------|------------------------|----------------------------------|
| GET    | `/api/v1/organizations/me` | any authenticated user | Read the caller's own organization |
| PATCH  | `/api/v1/organizations/me` | OWNER or ADMIN         | Update the caller's own organization |

There is deliberately no `/organizations/{id}` for arbitrary IDs — an
authenticated user can only ever see their own organization (no
superadmin/cross-tenant listing in MVP, per master spec section 58).

## Users (Phase 1, tenant-scoped)

| Method | Path                  | Auth required           | Description                          |
|--------|-----------------------|---------------------------|----------------------------------------|
| GET    | `/api/v1/users`       | any authenticated user    | Paginated list of users in caller's org |
| POST   | `/api/v1/users`       | OWNER or ADMIN            | Create a teammate in caller's org        |
| GET    | `/api/v1/users/{id}`  | any authenticated user    | Read a user — 404 if in another org      |
| PATCH  | `/api/v1/users/{id}`  | OWNER or ADMIN            | Update name/role/status — 404 if in another org |

## Sites (Phase 1, tenant-scoped)

| Method | Path                  | Auth required           | Description                             |
|--------|-----------------------|---------------------------|--------------------------------------------|
| GET    | `/api/v1/sites`       | any authenticated user    | Paginated list of sites in caller's org     |
| POST   | `/api/v1/sites`       | OWNER or ADMIN            | Create a site                                |
| GET    | `/api/v1/sites/{id}`  | any authenticated user    | Read a site — 404 if in another org          |
| PATCH  | `/api/v1/sites/{id}`  | OWNER or ADMIN            | Update a site — 404 if in another org        |
| DELETE | `/api/v1/sites/{id}`  | OWNER or ADMIN            | Archive (soft-delete) a site — 404 if in another org |

List endpoints accept `?limit=` (1–200, default 50) and `?offset=`
(default 0), and respond with the shared pagination envelope:

```json
{"items": [...], "total": 42, "limit": 50, "offset": 0}
```

## Error envelope (Phase 1)

Every error response (validation, HTTP exceptions, unhandled) has the
same shape:

```json
{
  "error": {"code": "NOT_FOUND", "message": "Site not found"},
  "request_id": "..."
}
```

`VALIDATION_ERROR` responses additionally include a `details` array
with per-field Pydantic error info.

## Design principles (apply to every endpoint added from here on)

- Typed Pydantic request/response schemas (`app/schemas/`) — ORM models
  are never returned directly.
- Tenant isolation enforced in the service layer via
  `app.security.tenant.get_tenant_scoped_or_404` for every tenant-owned
  resource; cross-tenant access is 404, never 403 (see
  `docs/database.md` for why).
- Pagination via `app.schemas.common.Page`/`PaginationParams`, reused
  by every list endpoint.
- Consistent error envelope via `app/core/errors.py`.
- Authentication via JWT bearer tokens (`app/security/tokens.py`,
  `app/security/dependencies.py`).

## Planned API groups (master spec section 50, Phase 9+)

`/products`, `/recommendations`, `/context`, `/commerce` — each
introduced in the phase that implements its underlying domain model
(see `docs/development.md`).

## Recommendation & Customer Context (Phase 8)

Reads open to any authenticated user in the org; writes require
`KNOWLEDGE_EDITOR_ROLES`.

**`POST /recommendations` returns HTTP 200 even when the answer is
`no_recommendation`.** Declining to recommend is a successful,
meaningful result (§34: "Do not push products when the user's intent
does not justify it"), not an error. Callers must read `status`, not
just check whether the list is empty.

### Customer Context

| Method | Path | Description |
|--------|------|--------------|
| POST | `/api/v1/context` | *(§50 literal)* Create. Every field optional — an empty body creates a valid fully-anonymous context. No conversation transcript is ever stored (§32) |
| GET | `/api/v1/context` | Paginated; filter by `?customer_id=`, `?session_id=` |
| GET | `/api/v1/context/{id}` | *(§50 literal)* Read one |
| PATCH | `/api/v1/context/{id}` | Field edits; explicit-null clears (same semantics as ADR-026) |
| POST | `/api/v1/context/{id}/withdraw-consent` | Privacy action: clears identity fields and **blocks this context from producing any further recommendations** — a hard gate, not a score penalty |

`POST /context/query` from §50 is not a separate path — its capability
is `POST /recommendations` with a `customer_context_id`. See ADR-030.

### Recommendations

| Method | Path | Description |
|--------|------|--------------|
| POST | `/api/v1/recommendations` | *(§50 literal)* Generate. Body: `response_mode` (required) plus optional `customer_context_id`, `query_id`, `knowledge_object_id`, `category`, `brand`, `product_ids`, `limit`, `persist` |
| GET | `/api/v1/recommendations` | Paginated; filter by `?customer_context_id=`, `?product_id=`, `?status=` |
| GET | `/api/v1/recommendations/{id}` | *(§50 literal)* Read one persisted decision, including its full structured `reason` and `policy_version` |

**Response shape.** Alongside `recommendations`, the response carries a
`rejected` list naming, for every candidate that didn't make it, the
gate it failed and why — so "why *not* that product?" is answerable.

**Scores are internal decision signals, not ratings.** §33 is explicit
that they are not Google ranking, ChatGPT ranking, or AI ranking, and
they must never be presented to an end user as a rating of the product.
Each of `relevance_score`/`evidence_score`/`trust_score`/
`availability_score` is 0–1 and is accompanied, for evidence and trust,
by a `SignalState`:

| State | Meaning |
|-------|---------|
| `unknown` | Nothing established yet — **not** a negative judgment |
| `partial` | Some verified support, not comprehensive |
| `established` | Verified support present |
| `conflicting` | Verified and rejected records both exist |
| `negative` | Reviewed and rejected |

`unknown` scores the neutral 0.5; `negative` scores 0.1. A product with
no evidence therefore ranks strictly above one whose claims were
rejected — see ADR-028.

**Response modes** (§34) gate whether product recommendation happens at
all: `educate` and `reassure` always return `no_recommendation`;
`compare`, `recommend` and `transact` proceed to scoring.

## Commerce & Product Knowledge (Phase 7)

Reads open to any authenticated user in the org; writes require
`KNOWLEDGE_EDITOR_ROLES`. Section 50's five literal product paths are
implemented exactly as written; the write endpoints are a documented
addition (see `docs/DECISIONS.md` ADR-023).

### Products

| Method | Path | Description |
|--------|------|--------------|
| GET | `/api/v1/products` | *(§50 literal)* Paginated; filter by `?status=`, `?category=`, `?brand=`, `?knowledge_object_id=` |
| GET | `/api/v1/products/{id}` | *(§50 literal)* Read one |
| POST | `/api/v1/products` | Create — always starts `DRAFT`; 404 if `site_id`/`knowledge_object_id` belong to another org; 409 on duplicate sku/slug within the org |
| PATCH | `/api/v1/products/{id}` | Field edits only — **cannot change `status`** |
| POST | `/api/v1/products/{id}/status` | The only path that changes status. `DRAFT → IN_REVIEW → PUBLISHED → ARCHIVED`; a direct DRAFT→PUBLISHED jump returns 422 |

There is no product DELETE — `ARCHIVED` covers retirement, and hard
deletion would destroy evidence/trust audit trail (ADR-023).

### Offers

| Method | Path | Description |
|--------|------|--------------|
| GET | `/api/v1/products/{id}/offers` | *(§50 literal)* Filter by `?availability=` |
| POST | `/api/v1/products/{id}/offers` | Create. `price: null` = "price on request"; `stock_quantity: null` = "untracked", which is **not** the same as `0` |
| PATCH | `/api/v1/offers/{offer_id}` | Update price/availability/stock/url |

### Product Evidence

| Method | Path | Description |
|--------|------|--------------|
| GET | `/api/v1/products/{id}/evidence` | *(§50 literal)* Filter by `?verification_status=` |
| POST | `/api/v1/products/{id}/evidence` | Link a Phase 4 Evidence row to this product **for one stated `claim`** — `claim` is required (422 without it). Always created `UNVERIFIED`. 409 if the same (evidence, claim) pair is already linked |
| POST | `/api/v1/product-evidence/{link_id}/verify` | The only path to `VERIFIED`; stamps `verified_at`, cleared again if later rejected. **Returns 422 if the underlying `Evidence` row is not itself VERIFIED** (ADR-032) |

**Two-layer verification invariant (ADR-032).** Verification runs in
both directions and neither implies the other:

- Verifying the `Evidence` row via `/evidence/{id}/review` does **not**
  verify the product-level claim it is cited for.
- Verifying the *link* is **refused** (422) while the Evidence beneath
  it is DRAFT, PENDING_REVIEW or REJECTED.
- If the Evidence is rejected **after** the link was verified, the link
  stops counting as verified from the next read onward — effective
  verification is recomputed, never read from a stored flag.

The first point below remains the core scope rule: That separation is what preserves evidence scope — a
verified study about a compound is not a verified claim about a
product (ADR-025).

### Product Relations

| Method | Path | Description |
|--------|------|--------------|
| GET | `/api/v1/products/{id}/related` | *(§50 literal)* Filter by `?relation_type=` |
| POST | `/api/v1/products/{id}/related` | Create a directional relation (alternative / complementary / similar / frequently_bought_together / replacement). **Never auto-mirrored** — "B replaces A" does not create "A replaces B". 422 on self-relation, 409 on duplicate |

### Trust Records

| Method | Path | Description |
|--------|------|--------------|
| GET | `/api/v1/trust-records` | Filter by `?subject_type=`, `?subject_id=`, `?trust_type=`, `?verification_status=` |
| POST | `/api/v1/trust-records` | `evidence_id` is **required** — a trust assertion with no evidence returns 422. Always created `UNVERIFIED`. Subject may be your own organization, a product, or a claim |
| GET | `/api/v1/trust-records/{id}` | Read one |
| POST | `/api/v1/trust-records/{id}/verify` | The only path to `VERIFIED`. **Returns 422 if the underlying `Evidence` row is not itself VERIFIED** (ADR-032) |

**There is deliberately no trust score anywhere in this API.** "How
trusted is this product" is answered by
`GET /trust-records?subject_id={product_id}&verification_status=verified`
— a list of auditable records, each with a claim, evidence and
verification date (§30, ADR-024).

## Query Engine (Phase 6)

Reads are open to any authenticated user; writes require
`KNOWLEDGE_EDITOR_ROLES` — the same split every resource in this API
uses. Endpoint surface reconciled against section 50's literal
4-line list (`POST /queries/import`, `GET /queries`,
`POST /queries/cluster`, `GET /query-groups`); every addition beyond
those 4 lines below is a conventional complement (by-id reads,
lifecycle actions), reasoned about explicitly rather than silent
scope creep — see `docs/DECISIONS.md` ADR-015 through ADR-018.

### Queries

| Method | Path | Description |
|--------|------|--------------|
| POST | `/api/v1/queries/import` | CSV or Excel (`.xlsx`) file (`multipart/form-data`, fields `source` + `file` — format auto-detected from the filename extension / content-type) OR a JSON row batch (fields `source` + `rows_json`, a JSON-encoded list). Manual single-entry reuses this same path with `source=manual` and a one-row batch. Deduplicates against existing queries by `normalize_query()` — a match appends a `QueryProvenance` occurrence instead of creating a duplicate `Query`. |
| GET | `/api/v1/queries` | Paginated list; filter by `?status=`, `?source=`, `?intent_type=` |
| GET | `/api/v1/queries/{id}` | Read one |
| PATCH | `/api/v1/queries/{id}` | Update `search_volume`/`commercial_value`/`priority` only (does not change `status`) |
| POST | `/api/v1/queries/{id}/archive` | `DISCOVERED`/`CLASSIFIED` → `ARCHIVED`; 422 if already archived |

### Intent

| Method | Path | Description |
|--------|------|--------------|
| GET | `/api/v1/queries/{id}/intents` | List every Intent for a query |
| POST | `/api/v1/queries/{id}/intents` | Manual/human-override classification (`classification_source=manual`) — always adds a new row, never edits an existing one |
| POST | `/api/v1/queries/{id}/classify` | Runs the rule engine on this one query; auto-transitions `DISCOVERED` → `CLASSIFIED` if it produces any match |
| POST | `/api/v1/queries/classify` | Bulk: runs the rule engine over every still-`DISCOVERED` query in the org |

### Clustering

| Method | Path | Description |
|--------|------|--------------|
| POST | `/api/v1/queries/cluster` | (Re)clusters every active (non-archived) query in the org — word n-gram Jaccard similarity, v1 (see ADR-016). Wholesale replace, not additive. |
| GET | `/api/v1/query-clusters` | Paginated list |
| GET | `/api/v1/query-clusters/{id}` | Read one |
| GET | `/api/v1/query-clusters/{id}/members` | Member queries + similarity score |

### Query Groups

| Method | Path | Description |
|--------|------|--------------|
| GET | `/api/v1/query-groups` | Paginated list; filter by `?primary_intent=`, `?priority=` |
| POST | `/api/v1/query-groups` | Create — 404 if `target_entity_id` belongs to another org |
| GET | `/api/v1/query-groups/{id}` | Read one |
| PATCH | `/api/v1/query-groups/{id}` | Update `name`/`priority` only |
| GET | `/api/v1/query-groups/{id}/members` | List member queries |
| POST | `/api/v1/query-groups/{id}/members` | Add a query — 404 if either side belongs to another org (two-hop), 409 if already a member |
| DELETE | `/api/v1/query-groups/{id}/members/{membership_id}` | Remove a member |
| GET | `/api/v1/query-groups/{id}/knowledge-need-assessment` | A **computed, read-only judgment** (never a persisted row — see ADR-017): is this group's `target_entity_id` adequately covered by existing Claims/Evidence right now? If the answer is "no", acting on it means calling the *existing* `POST /knowledge-gaps` (Phase 2) yourself — this endpoint never creates a gap. |

## Research Engine (Phase 5)

All endpoints are tenant-scoped; reads are open to any authenticated
user, writes require `KNOWLEDGE_EDITOR_ROLES` (OWNER, ADMIN,
RESEARCHER, or EDITOR) — no separate "execute" permission tier exists,
since no prior phase in this API distinguishes write from execute more
finely than that.

### Research Projects

| Method | Path                                          | Description                                    |
|--------|------------------------------------------------|--------------------------------------------------|
| GET    | `/api/v1/research/projects`                     | Paginated list; filter by `?mode=`, `?status=`, `?knowledge_gap_id=` |
| POST   | `/api/v1/research/projects`                      | Create — 422 if `mode=gap_driven` with no `knowledge_gap_id`, 404 if the gap belongs to another org |
| GET    | `/api/v1/research/projects/{id}`                 | Read one                                           |
| PATCH  | `/api/v1/research/projects/{id}`                 | Update `name`/`objective` only (does not change `status`) |
| POST   | `/api/v1/research/projects/{id}/transition`      | The only path that changes `status` — 422 if the transition isn't in the validated table (see `docs/database.md`) |

### Research Tasks

| Method | Path                                            | Description                                    |
|--------|---------------------------------------------------|--------------------------------------------------|
| GET    | `/api/v1/research/tasks`                          | Paginated list; filter by `?research_project_id=`, `?status=` |
| POST   | `/api/v1/research/tasks`                           | Create under a project — 404 if `research_project_id` belongs to another org |
| GET    | `/api/v1/research/tasks/{id}`                      | Read one                                           |
| PATCH  | `/api/v1/research/tasks/{id}`                      | Update `task_type`/`query` — 409 once the task is past `PENDING` |
| POST   | `/api/v1/research/tasks/{id}/queue`                | `PENDING` → `QUEUED`, dispatches the Celery job that runs the configured `ResearchProvider` |
| POST   | `/api/v1/research/tasks/{id}/cancel`               | Cancel — 422 if the task is already in a terminal state |
| GET    | `/api/v1/research/tasks/{id}/references`           | The task's provenance trail — every Source/Document/Evidence/Claim/KnowledgeObject/KnowledgeGap it referenced or discovered |

**Important caveat, same spirit as Phase 3's embedding-provider note:**
no real `ResearchProvider` is configured in this delivery (see
`app/integrations/research/base.py`) — every task that gets queued will
honestly complete in `FAILED` status with
`result.outcome_status == "not_configured"`. This proves the queue →
worker → status-update pipeline works end-to-end (verified against a
real Redis broker and a real `celery worker` process, not just tests —
see `docs/development.md`'s Phase 5 STATUS section), not that any
research actually happens yet.

## Evidence & Claim/Evidence (Phase 4)

All endpoints are tenant-scoped; writes require `KNOWLEDGE_EDITOR_ROLES`
(OWNER, ADMIN, RESEARCHER, or EDITOR).

### Evidence

| Method | Path                            | Description                                    |
|--------|----------------------------------|--------------------------------------------------|
| GET    | `/api/v1/evidence`                | Paginated list; filter by `?source_id=`, `?document_id=`, `?study_type=`, `?status=` |
| POST   | `/api/v1/evidence`                 | Create — 404 if `source_id`/`document_id` belong to another org, 422 if the chain is mismatched (e.g. `document_id` not actually under `source_id`) |
| GET    | `/api/v1/evidence/{id}`            | Read one                                           |
| PATCH  | `/api/v1/evidence/{id}`            | Update fields (does not change `status`)           |
| POST   | `/api/v1/evidence/{id}/review`     | The only path that changes `status` — sets `human_reviewed=True` and recomputes every linked Claim's aggregate |

### Claim/Evidence links

A flat top-level resource — same shape as `/relationships` (Phase 2's
generic graph-edge table) — rather than nested under either
`/claims` or `/evidence`, since a link genuinely belongs to neither
side more than the other.

| Method | Path                            | Description                                    |
|--------|----------------------------------|--------------------------------------------------|
| GET    | `/api/v1/claim-evidence`          | Paginated list; filter by `?claim_id=`, `?evidence_id=` |
| POST   | `/api/v1/claim-evidence`           | Create a link — 404 if either `claim_id` or `evidence_id` belongs to another org, 409 if the pair is already linked |
| GET    | `/api/v1/claim-evidence/{id}`      | Read one link                                      |
| PATCH  | `/api/v1/claim-evidence/{id}`      | Update `relation`/`weight`/`notes` — recomputes the claim's aggregate |
| DELETE | `/api/v1/claim-evidence/{id}`      | Unlink — recomputes the claim's aggregate afterward |

Creating, updating, or deleting a link (and reviewing the Evidence on
either end of one) all trigger
`claim_evidence_service.py::recompute_claim_aggregate`, which may
change the linked Claim's `evidence_strength` and — if a genuine,
verified conflict is detected on a currently-`APPROVED` claim —
auto-downgrade its `status` to `DISPUTED`. See `docs/database.md` for
the full aggregation rules.

## Sources & Documents (Phase 3)

All endpoints are tenant-scoped; writes require `KNOWLEDGE_EDITOR_ROLES`
(OWNER, ADMIN, RESEARCHER, or EDITOR).

### Sources

| Method | Path                            | Description                                    |
|--------|----------------------------------|--------------------------------------------------|
| GET    | `/api/v1/sources`                | Paginated list; filter by `?source_type=`         |
| POST   | `/api/v1/sources`                 | Create                                             |
| GET    | `/api/v1/sources/{id}`            | Read one                                           |
| PATCH  | `/api/v1/sources/{id}`            | Update                                             |
| GET    | `/api/v1/sources/{id}/documents`  | Documents attached to this source                  |

No DELETE endpoint — see `docs/database.md` for why (no lifecycle
`status` field is in the master spec's field list for Source).

### Documents

| Method | Path                                | Description                                    |
|--------|--------------------------------------|--------------------------------------------------|
| GET    | `/api/v1/documents`                  | Paginated list; filter by `?source_id=`            |
| POST   | `/api/v1/documents?source_id=...`     | Create — 404 if `source_id` belongs to another org  |
| GET    | `/api/v1/documents/{id}`             | Read one                                           |
| PATCH  | `/api/v1/documents/{id}`              | Update — editing `content` bumps `version`, rehashes, and deletes existing chunks |
| POST   | `/api/v1/documents/{id}/process`      | Chunk + embed synchronously (idempotent — replaces existing chunks, doesn't duplicate) |
| GET    | `/api/v1/documents/{id}/chunks`       | Paginated chunk list, without embedding vectors     |
| GET    | `/api/v1/documents/{id}/chunks/{id}`  | One chunk, including its embedding vector           |
| GET    | `/api/v1/documents/chunks/search`     | pgvector nearest-neighbor search — `?q=`, optional `?document_id=`, `?limit=` |

**Important caveat on `/documents/chunks/search`:** the embedding
provider in this delivery (`DeterministicHashEmbeddingProvider`) is a
documented placeholder with no semantic understanding of text — it
proves the storage/indexing/query mechanism works end-to-end (an exact
text match returns cosine distance `0.0`), not that results are
semantically meaningful. See
`app/integrations/embeddings/deterministic.py`'s docstring before using
this for anything beyond verifying the pipeline.

## Knowledge Core (Phase 2)

All endpoints below are tenant-scoped: every lookup by ID uses
`get_tenant_scoped_or_404`, so an ID belonging to another organization
always returns 404. Writes require a `KNOWLEDGE_EDITOR_ROLES` role
(OWNER, ADMIN, RESEARCHER, or EDITOR) — ANALYST and VIEWER are
read-only for this domain.

### Knowledge Objects

| Method | Path                          | Description                                    |
|--------|-------------------------------|--------------------------------------------------|
| GET    | `/api/v1/knowledge`           | Paginated list; filter by `?search=`, `?object_type=`, `?status=` |
| GET    | `/api/v1/knowledge/search`    | Text search alias (`?q=`), same filters as above  |
| POST   | `/api/v1/knowledge`           | Create (status starts at `draft`, slug auto-generated and de-duplicated) |
| GET    | `/api/v1/knowledge/{id}`      | Read one                                          |
| PATCH  | `/api/v1/knowledge/{id}`      | Update — **automatically writes a new KnowledgeVersion** |
| POST   | `/api/v1/knowledge/{id}/publish` | Sets `status=published`, `public_visibility=true` |
| DELETE | `/api/v1/knowledge/{id}`      | Archives (`status=archived`) — soft delete, not destructive |
| GET    | `/api/v1/knowledge/{id}/entities`  | Entities attached to this object            |
| GET    | `/api/v1/knowledge/{id}/claims`    | Claims attached to this object              |
| GET    | `/api/v1/knowledge/{id}/relations` | Relationship edges where this object is either endpoint (single correctly-paginated query — see `docs/development.md`) |
| GET    | `/api/v1/knowledge/{id}/versions`  | Full version history, most recent first     |
| GET    | `/api/v1/knowledge/{id}/gaps`      | Knowledge gaps attached to this object      |

`GET /knowledge/{id}/evidence` from the master spec's section 50 list is
**not implemented yet** — it depends on the Evidence model, which
arrives in Phase 4.

Every `PATCH` accepts an optional `change_summary` field, stored on the
resulting `KnowledgeVersion` row (not on the object itself).

### Entities

| Method | Path                    | Description                                          |
|--------|-------------------------|----------------------------------------------------------|
| GET    | `/api/v1/entities`      | Paginated list; filter by `?knowledge_object_id=`         |
| POST   | `/api/v1/entities`      | Create under a knowledge_object_id (404 if it's another org's) |
| GET    | `/api/v1/entities/{id}` | Read one                                                   |
| PATCH  | `/api/v1/entities/{id}` | Update `entity_type`/`canonical_name`/`aliases`/`external_ids`/`language` |

### Claims

| Method | Path                          | Description                                     |
|--------|-------------------------------|----------------------------------------------------|
| GET    | `/api/v1/claims`              | Paginated list; filter by `?knowledge_object_id=`, `?status=` |
| POST   | `/api/v1/claims`               | Create — requires **exactly one** of `object_entity_id`/`object_value` (XOR, not "at least one") |
| GET    | `/api/v1/claims/{id}`          | Read one                                            |
| PATCH  | `/api/v1/claims/{id}`          | Edit predicate/object/claim_type/confidence — **cannot** change `status` |
| POST   | `/api/v1/claims/{id}/review`   | The only path that changes `status`; always sets `human_reviewed=true` |

`ClaimUpdate` has no `status` field at all — this is a schema-level
guarantee, not just a convention, that a plain edit can never bypass
the review gate.

**PATCH semantics for `object_entity_id`/`object_value`** (the two
fields are mutually exclusive — see `docs/database.md`):
- Omit a field entirely → left unchanged.
- Send a non-null value → that representation is set, and the other is
  **automatically cleared** (this is how you switch a claim from a
  literal value to an entity reference, or vice versa, in one call).
- Send `null` explicitly → that representation is cleared, which is
  only valid if the other one is being set in the same request or is
  already set on the claim — otherwise the claim would end up with
  neither, and the request is rejected with `422`.
- Sending both as non-null in the same request is always rejected with
  `422`, never silently resolved in favor of one side.

### Relationships (graph edges)

| Method | Path                             | Description                                  |
|--------|-----------------------------------|--------------------------------------------------|
| GET    | `/api/v1/relationships`           | Paginated list; filter by `?subject_id=`, `?object_id=` |
| POST   | `/api/v1/relationships`            | Create — `subject_type`/`object_type` is `entity` or `knowledge_object` |
| GET    | `/api/v1/relationships/{id}`       | Read one                                          |
| PATCH  | `/api/v1/relationships/{id}`       | Update `confidence`/`status`                       |

### Knowledge Gaps

| Method | Path                              | Description                                 |
|--------|-------------------------------------|-------------------------------------------------|
| GET    | `/api/v1/knowledge-gaps`             | Paginated list; filter by `?knowledge_object_id=`, `?status=` |
| POST   | `/api/v1/knowledge-gaps`              | Create under a knowledge_object_id           |
| GET    | `/api/v1/knowledge-gaps/{id}`         | Read one                                      |
| PATCH  | `/api/v1/knowledge-gaps/{id}`         | Update description/priority/status/recommended_action |


## Official client suite (ADR-137)

Native clients (Windows, macOS, Android, iOS) authenticate with the methods the website and dashboard
already use, and keep the long-lived half of the session in the operating system's secure storage.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/auth/native/session` | none | `{grant: "login_code", email, code}` or `{grant: "password", email, password}` → `{access_token, expires_in_minutes, refresh_token, refresh_expires_at}`. Same throttles, lockout and indistinguishable failures as `/auth/login-code/verify` and `/auth/login`. Never sets a cookie. |
| POST | `/api/v1/auth/native/session/refresh` | none (refresh token in body) | Rotates the refresh secret. A secret rotated away more than 30 s ago revokes the whole session (`reuse_detected`). 401 on every failure. |
| POST | `/api/v1/auth/native/session/end` | none (refresh token in body) | Sign out. Idempotent, always 204. Does not touch conversations. |
| GET | `/api/v1/clients/config?platform=` | none | Operator-configured links (`help`, `learn_more`, `privacy`, `terms`, `docs`, `report_problem`; `null` when unset), `upgrade {url, state}` (`available` · `not_configured` · `not_offered_on_platform`), published `releases`, `languages`, Device Intelligence switch and retention. No tenant data. |

The refresh token is the same `auth_sessions` secret the browser keeps in its HttpOnly cookie
(ADR-129): HMAC-only storage, rotation, reuse detection, absolute lifetime.

**Chat idempotency.** `POST /chat/conversations/{id}/messages` accepts an optional
`client_request_id` (`[A-Za-z0-9_-]{8,64}`). Re-sending the same key returns the stored assistant
turn with `200` and `Idempotent-Replay: true`; a key whose question is stored but not yet answered
is `409` with `error.reason = "request_in_progress"`. Requests without a key behave as before.
Message objects now include `client_request_id`.

**Structured error reasons.** When a route raises a detail of the form `{code, message}`, the error
envelope keeps its shape and adds `error.reason` (a stable machine code). String details are
unchanged.

## Device Intelligence (ADR-138)

Installation-continuity evidence. Every route requires a session; admin routes require owner or admin.
Errors carry `error.reason`. A client must never block sign-in on any of these.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/devices/challenges` | `{purpose: "register" \| "verify", credential_id?}` → `{challenge_id, nonce, expires_at, signing_input}`. Single use, 120 s, bound to (organization, user, purpose, credential). 30/min per user. |
| POST | `/api/v1/devices/credentials` | Register: `{challenge_id, nonce, public_key (base64 DER SPKI, P-256), signature (ES256, DER or P1363), platform, key_storage, app_version?, os_family?, os_version?}`. 201 created · 200 already registered (and this account linked). Reasons: `bad_signature` (401), `challenge_replayed` / `challenge_expired` / `challenge_invalid` / `credential_revoked` / `provenance_mismatch` (409), `unsupported_key` (422). |
| POST | `/api/v1/devices/credentials/{id}/verify` | Continuity check with a `verify` challenge. 404 unless the caller's account is linked to the credential. |
| GET | `/api/v1/devices/credentials` | Installations linked to the caller's account. |
| DELETE | `/api/v1/devices/credentials/{id}` | Unlink the caller; revokes the credential when no account remains. 204. |
| GET | `/api/v1/devices/admin/credentials` | Admin. Paginated, `state=active\|revoked`. Each item carries `assessment {categories, reason_codes, algorithm_version, evidence}`. |
| GET | `/api/v1/devices/admin/credentials/{id}` | Admin. Linked accounts and the last 100 observations with truncated network pseudonyms. Every read is audit-logged (`device_intelligence.viewed`). |
| POST | `/api/v1/devices/admin/credentials/{id}/revoke` | Admin. Audited (`device.credential_revoked`). 409 when already revoked. |

`signing_input` is `AIOL-DEVICE-v1\n<purpose>\n<challenge_id>\n<nonce>\n<organization_id>\n<user_id>\n<credential_id or ->`;
the server rebuilds it from its own record. Assessment categories (algorithm `di-assess-v1`):
`DEVICE_CREDENTIAL_REVOKED`, `SAME_REGISTERED_INSTALLATION`, `CONFLICTING_EVIDENCE`,
`SHARED_NETWORK_ONLY`, `INSUFFICIENT_EVIDENCE`. None of them is a person-level conclusion, and no route
enforces on them.
