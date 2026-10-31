# Architecture Decisions

## ADR-001
Cloud Core is the source of truth.

## ADR-002
WordPress is a thin adapter.

## ADR-003
PostgreSQL is the primary database.

## ADR-004
pgvector is used initially instead of a separate vector database.

## ADR-005
The system uses a modular monolith for MVP.

## ADR-006
Knowledge Object is the canonical knowledge abstraction.

## ADR-007
Evidence is separate from Claims.

## ADR-008
Product is separate from Offer.

## ADR-009
Query is separate from Intent.

## ADR-010
Customer Context is separate from raw conversation.

## ADR-011
Rights are separate from Discovery.

## ADR-012
Commerce transactions happen on the merchant website.

## ADR-013
`docs/master-spec/MASTER_SPEC.md` did not exist in this repository as
of the Phase 5 implementation session (confirmed via `git log --all` —
no commit had ever added it). Phase 5's implementation instructions
named it as the canonical spec and quoted its section 22 (Research
Engine) and section 62 (development order) directly in the
instruction text; that quoted text was treated as the authoritative
source for Phase 5 at the time, and the gap was recorded here per the
"identify the conflict, document the resolution" rule.

**Resolved:** the canonical file was supplied afterward and added at
`docs/master-spec/MASTER_SPEC.md` (verified byte-for-byte against the
supplied copy — 2237 lines, sections 1-66). Cross-checked against the
Phase 5 implementation: section 22's literal field lists for
`research_projects`/`research_tasks`, the four research modes, and the
"traceable results"/"preserve the research trail" requirements match
what was already built, with zero contradiction found. Section 62's
development order (Phase 5 = Research Engine, Phase 6 = Query Engine/
Intent/Query Clustering) also matches. No destructive or retroactive
change to Phase 5 was required as a result of adding this file.

## ADR-014
Research-task provenance (`research_task_references`) is a new,
Phase-5-scoped table with its own `research_reference_type` enum,
rather than an extension of `Relationship`/`graph_node_type` (Phase
2's generic graph-edge table). `Relationship`'s own docstring
anticipates "eventually Product/Source/etc." as node types, which made
reuse tempting, but altering a shared enum/table already exercised by
Phases 2-4's tests for a Phase-5-only need (task execution provenance,
not domain-knowledge graph edges) was judged riskier than adding one
small, independently-scoped table. See
app/models/research_task_reference.py's docstring for the full
reasoning.

## ADR-015
Query model reconciled with section 23's literal field list via three
distinct, non-overlapping roles rather than one field doing double
duty: `query` (section-23-literal, canonical/immutable),
`normalized_query` (additive, deterministic dedup key — same
justification pattern as `Document.content_hash`), and `raw_query`
(lives on the new, additive `QueryProvenance` table, one row per
occurrence/import event, never on `Query` itself). No spec field was
renamed, dropped, or silently repurposed. `intents.product_id` is a
plain nullable UUID with no FK constraint (products doesn't exist
until Phase 7) — this mirrors the already-shipped
`relationships.source_id` deferred-FK pattern from Phase 2->3
(migration `0004` added that FK once `sources` existed; a future Phase
7 migration will do the same for `intents.product_id` via
`op.create_foreign_key`, never by editing migration `0007`). See each
model's own module docstring (`app/models/query.py`,
`query_provenance.py`, `intent.py`, `query_group.py`,
`query_group_membership.py`) for the full field-by-field reasoning.

## ADR-016
Query clustering v1 uses word n-gram (unigram + bigram) Jaccard
similarity over `normalized_query`, computed entirely in Python with no
new dependency — NOT pgvector-embedding-based. Reason: the only
embedding provider that exists in this codebase
(`DeterministicHashEmbeddingProvider`, Phase 3) is explicitly
documented as producing vectors with no real semantic meaning;
clustering on top of that placeholder would look numerically
legitimate while having no genuine semantic basis, which is worse than
an honestly-limited token-overlap method. `QueryClusterMembership.score`
is intentionally provider-agnostic (just a similarity float) so a
future embedding-based clustering function can populate the same
column without any schema change. See
app/services/query_cluster_service.py's module docstring.

## ADR-017
Knowledge Need (master spec section 24's pipeline diagram) is
implemented as a service-level computed judgment
(`query_group_service.assess_knowledge_need`, returning a Pydantic
value object), never a persisted database row, and explicitly NOT
represented by `QueryGroup` itself. A `QueryGroup` is a curated bucket
of queries (persisted, section-25-defined); a Knowledge Need is the
answer to "is this bucket adequately served by existing
Knowledge/Evidence right now" — an answer that can change every time a
Claim or Evidence row is added elsewhere in the system, without anyone
touching the QueryGroup. Treating QueryGroup as the Knowledge Need
would mean every group automatically implies a content gap, which is
false. If the assessment concludes a gap exists, Phase 6 never creates
one itself — gap creation stays exclusively on the existing
`knowledge_gap_service.create_knowledge_gap` / `POST /knowledge-gaps`
(Phase 2). See app/services/query_group_service.py's module docstring.

## ADR-018
`research_reference_type` (Phase 5's enum) is additively extended with
`query`/`query_group` values (migration `0007`) so a
`ResearchTaskReference` can trace a research effort back to the demand
signal that motivated it — reusing Phase 5's existing provenance table
rather than Phase 6 inventing a parallel one. This is the only place
Phase 6 touches a prior phase's migration surface, and it is additive
only: migration `0006` itself is never edited, and the downgrade path
correctly rebuilds the original Phase 5 enum value set (Postgres has
no `DROP VALUE`, so this uses the standard rename-recreate-repoint-drop
sequence, verified via `scripts/verify_migration_cycle.sh`).

## ADR-019
`docs/strategy/AI_COMMERCE_VISION_2035.md` has been added to the
repository — a strategic-direction document, not an architecture
specification. Per its own stated relationship to the canonical spec
("این سند جایگزین Master Spec نیست؛ جهت‌گیری محصول و معیار تصمیم‌گیری
برای تکامل Master Spec است" — "this document does not replace the
Master Spec; it is product direction and a decision criterion for the
Master Spec's evolution"), `docs/master-spec/MASTER_SPEC.md` remains
the sole authoritative source for what gets implemented in any given
phase. This vision document informs FUTURE Master Spec evolution and
longer-range architectural judgment calls (e.g. which Phase 7+
capabilities to prioritize, how to think about agentic-commerce
readiness), but does not itself authorize implementing anything not
already in the Master Spec, and no existing implementation was changed
as a result of adding it.

## ADR-020
Excel (`.xlsx`) import was added to Phase 6, resolving a real,
independently-verified spec deviation: master spec section 23 states
"The system must accept manually uploaded Excel/CSV query lists" — a
literal MUST covering both formats, not just CSV. Phase 6's original
v1 shipped CSV-only (a scope decision approved at the time, but one
that left the spec's Excel requirement genuinely unmet, not merely
deferred as a "nice to have"). Resolution: `openpyxl==3.1.5` added to
`requirements.txt` (pure-Python, no compiled-extension supply-chain
risk); `query_service.parse_excel_rows` added alongside the existing
`parse_csv_rows`, sharing the same row-validation rules via a common
`_build_import_row` helper so the two formats can never silently
diverge in what they accept; `POST /queries/import` dispatches between
them based on the uploaded file's extension/content-type. No schema
change was needed — `QuerySource.EXCEL` already existed
(`app/models/enums.py`, present since migration `0007`), since
section 23's `source` vocabulary always included `excel` even before
this fix. `pandas` was considered and rejected in favor of `openpyxl`
alone: pandas would pull in numpy and a substantially larger
dependency surface for a need `openpyxl` alone fully covers (reading a
simple query-list worksheet), and `openpyxl` is the same library
`pandas.read_excel` itself uses under the hood for `.xlsx` files.

## ADR-021
**FACT:** Master Spec section 26's literal `products` field list does not
include a provenance column. **FACT:** the Phase 7 brief requires the
system to distinguish merchant input from WooCommerce sync from
supplier data, and to "not represent all information as equally
authoritative". **INFERENCE:** without a stored origin, that
distinction is unrecoverable once a row is written — nothing else on
the row records where its data came from. **DECISION:** add
`Product.provenance` (merchant / woocommerce / supplier /
imported_document / research / external) as an additive column.
**TRADE-OFF:** one column beyond the literal spec list, in exchange for
an authority distinction the brief explicitly requires.
**KNOWN LIMITATION:** provenance is per-ROW, not per-FIELD. A product
created by a merchant and later partially updated by a WooCommerce sync
carries a single provenance value that cannot express "name is
merchant-authored, price is Woo-synced". Field-level provenance is
future work if it turns out to be needed.

## ADR-022
**FACT:** sections 27 (`offers`), 28 (`product_evidence`), 29
(`product_relations`) list no `organization_id`; only `products` (26)
and `trust_records` (30) do. **FACT:** every tenant-owned child table
already shipped in this codebase (KnowledgeVersion, DocumentChunk,
ClaimEvidence, ResearchTask, QueryProvenance, QueryGroupMembership...)
carries its own `organization_id`, per section 8's blanket rule.
**INFERENCE:** the spec's field lists are conceptual minimums, not
exhaustive DDL — section 18's `claim_evidence` list was similarly
partial and Phase 4 added id/organization_id/timestamps for the same
reason. **DECISION:** add `organization_id` to offers,
product_evidence, and product_relations, and validate it against the
parent Product's own organization in the service layer before insert.
**TRADE-OFF:** three columns beyond the literal lists, in exchange for
tenant scoping that never depends on a join being remembered —
directly serving the Phase 7 brief's "do not rely only on API-level
checks where database constraints can reasonably provide
defense-in-depth". **KNOWN LIMITATION:** the database still cannot by
itself enforce `offer.organization_id == product.organization_id`
(that would need a composite FK); the service layer enforces it and
tests cover it. This is the same defense-in-depth gap already recorded
for research_tasks in the Phase 5 review.

## ADR-023
**FACT:** section 50 lists exactly five product endpoints, all GET
(`/products`, `/products/{id}`, `/products/{id}/offers`,
`/products/{id}/evidence`, `/products/{id}/related`). **FACT:** it
lists no POST/PATCH for products. **INFERENCE:** a merchant must be
able to create a product somehow, and section 50 reads as a
read-surface sketch of what consumers query rather than a prohibition
on writes — the same reasoning Phase 6 applied to by-id reads.
**DECISION:** implement all five literal GET paths exactly as written,
plus write endpoints (POST/PATCH, `/products/{id}/status`, offer and
evidence and relation creation, `/trust-records`, and the two verify
actions) following this project's existing conventions.
**TRADE-OFF:** more endpoints than section 50 lists, all documented
here rather than added silently. **KNOWN LIMITATION:** there is no
product DELETE endpoint — ARCHIVED status covers retirement, and hard
deletion of a product with evidence and trust history attached would
destroy audit trail. Same reasoning already applied to Source and
Document in Phase 3.

## ADR-024
**FACT:** section 30 says "Do not create a fake 'trust score' that has
no explainable evidence", and its `trust_records` field list contains
no score column. **DECISION:** `TrustRecord` has no score field of any
kind, and `evidence_id` is NOT NULL. "How trusted is this product" is
answered by enumerating that product's VERIFIED trust records — a
query that returns rows a human can open and audit, each with a claim,
a piece of evidence and a verification date.
**INFERENCE:** a stored score would survive independently of the
evidence beneath it — it can be cached, drift, be displayed after its
supporting evidence is rejected, and be quoted as if it meant
something externally verifiable. Enumeration cannot drift from its own
evidence because it IS its evidence.
**TRADE-OFF:** consumers wanting a single number must compute one
themselves from the records, and must decide their own weighting —
which is the point: any such weighting is a product decision that
should be visible, not buried in this table.
**KNOWN LIMITATION:** this defers rather than solves the ranking
question that Phase 8 (Recommendation Engine) will face. Phase 8 will
need SOME way to compare trust across products; whatever it builds
must be an internal, documented decision score, never presented as an
external or authoritative rating.

## ADR-025
**FACT:** the Phase 7 brief states the critical rule: evidence about a
compound (Mannitol) must not become evidence of a product's clinical
effect (Taranjabin). **FACT:** section 28's `product_evidence` includes
a `claim` field, and its examples always pair evidence with a specific
stated claim. **DECISION:** `ProductEvidence.claim` is NOT NULL at the
database level and required with `min_length=1` at the schema level, so
an unscoped evidence link is unrepresentable at every layer. Uniqueness
is on (product, evidence, claim) so the same lab report can
independently support several different claims, each separately
verifiable.
**INFERENCE:** this makes the unsafe conversion *visible and
attributable* rather than impossible — a human must literally type the
clinical claim next to the composition document, and a second human
must verify it, and both acts are audit-logged.
**KNOWN LIMITATION — stated plainly:** software cannot stop a human
from writing a false claim. What this design guarantees is narrower:
the system itself never makes the inferential leap, verification is
never automatic, and if a bad claim is ever verified there is a
recorded actor and timestamp for it. Claiming more than that would
overstate what schema design can do.

## ADR-026
**FACT:** an earlier Phase 7 revision's `update_product`/`update_offer`
both did `if value is None: continue`, which made an explicit
`{"origin": null}` a silent no-op that still returned 200.
**FACT:** `OfferUpdate` omitted `external_id`, `condition` and
`valid_from`, making those columns write-once by accident.
**FACT:** `update_offer` had no IntegrityError handling, so a plausible
edit (lowering `valid_until` below an existing `valid_from`) escaped as
a raw database error.
**INFERENCE:** because the API layer already passes
`model_dump(exclude_unset=True)`, "key absent" and "key present with
value null" are genuinely distinguishable — the information was there
and was being thrown away.
**DECISION:** `PATCH {}` leaves a field alone; `PATCH {"field": null}`
clears it. Nulling a NOT NULL column returns 422 naming the field,
rather than failing later as a database error. `OfferUpdate` now
covers every mutable column. Both create and update paths on Offer map
CHECK-constraint violations to a 422 that names what the caller did
wrong (`_offer_constraint_message`).
**TRADE-OFF:** two small allow-lists of non-nullable updatable fields
must be kept in step with the models. A schema-derived check would be
more automatic, but also more magic; explicit lists are greppable and
fail visibly in tests if a column's nullability changes.
**KNOWN LIMITATION:** this fixes Phase 7's own endpoints only. Earlier
phases' update services still use the skip-None pattern, so the same
"cannot clear a nullable field" gap exists there — recorded in
KNOWN_ISSUES rather than fixed silently across phases that are already
frozen and independently reviewed.

## ADR-027
**FACT:** before Phase 8, every domain read only its own tables, so
direct `select(Model)` was harmless. **FACT:** Recommendation is the
first genuinely cross-domain consumer — it needs Product, Offer,
ProductEvidence and TrustRecord simultaneously. **INFERENCE:** letting
it query those tables directly would mean (a) any Phase 7 schema change
silently breaks Phase 8, and (b) Commerce business rules — what counts
as purchasable, what counts as recommendable — would end up inside
Recommendation, where they do not belong. **DECISION:** introduce
`app/contracts/commerce.py`, a read-contract layer **owned by the
Commerce domain**, exposing narrow dataclasses
(`ProductReadModel`, `OfferReadModel`, `ProductEvidenceSummary`,
`TrustSummary`) and org-scoped query functions. `recommendation_service`
imports only from this module and never from Phase 7's ORM models.
**TRADE-OFF:** one indirection layer, and read models that must be
extended when a consumer genuinely needs a new field. In exchange,
adding a Product column requires no Phase 8 change at all.
**KNOWN LIMITATION:** this is a convention, not an enforced boundary —
nothing stops a future author importing `Product` directly into a
Recommendation module. A lint rule (e.g. import-linter) would enforce
it mechanically; not added now to avoid new tooling in a phase that
already introduces a lot.

## ADR-028
**FACT:** the Phase 8 brief requires that missing evidence not be
treated as negative evidence, and missing trust not as distrust.
**INFERENCE:** a single numeric score cannot express this — "no
evidence" and "evidence rejected" would both have to be low numbers,
and whichever value is chosen is wrong for one of them.
**DECISION:** every evidence/trust signal carries a `SignalState`
(UNKNOWN / PARTIAL / ESTABLISHED / CONFLICTING / NEGATIVE) alongside
its score, persisted on the Recommendation row as `evidence_state` and
`trust_state`. UNKNOWN scores the neutral 0.5; NEGATIVE scores 0.1.
**TRADE-OFF:** two extra columns and a slightly more complex consumer
contract. **KNOWN LIMITATION:** the neutral value (0.5) and the
negative value (0.1) are documented judgments, not tuned constants —
there is no recommendation outcome data to tune against yet, and
inventing precision would be dishonest. Recorded in KNOWN_ISSUES.

## ADR-029
**FACT:** master spec section 33's `recommendations` field list has no
`policy_version` and no `offer_id`. **INFERENCE:** without
`policy_version`, a historical recommendation becomes unexplainable the
moment scoring weights change — the reproducibility requirement cannot
be met. Without `offer_id`, an availability decision cannot be
explained afterwards, because §27 puts price and stock on Offer and a
product may have many. **DECISION:** add both. `policy_version` is
stamped from `recommendation_policy.POLICY_VERSION`, which MUST be
bumped whenever weights or thresholds change.
**TRADE-OFF:** two columns beyond the literal spec list.
**KNOWN LIMITATION:** nothing mechanically enforces bumping
POLICY_VERSION when weights change — it is a discipline, and a stale
version would silently mislabel decisions.

## ADR-030
**FACT:** section 50 lists `POST /context/query` as a separate
endpoint. **INFERENCE:** its capability — recommend against an existing
context — is fully expressed by `POST /recommendations` with an
optional `customer_context_id`. A second path would be a synonym, and
two endpoints that must stay behaviourally identical drift.
**DECISION:** implement the capability once, on `POST
/recommendations`. All other §50 paths (`POST /recommendations`, `GET
/recommendations/{id}`, `POST /context`, `GET /context/{id}`) are
implemented literally. **TRADE-OFF:** a caller following §50 verbatim
will find `/context/query` missing; documented here and in api.md
rather than left to be discovered.

## ADR-031
**FACT:** `Recommendation.reason` is JSONB, not text.
**INFERENCE:** section 33 names a `reason` field; a free-text reason
would be unparseable by the AI agents and dashboards that later phases
(11, 14) are meant to build on, and would rot into a dumping ground.
**DECISION:** `reason` holds a structured object whose shape is defined
by `RecommendationReason` — every signal's score, state and
human-readable detail, plus caveats and the policy version.
**TRADE-OFF:** JSONB is not schema-enforced at the database level; the
Pydantic model is the contract. **KNOWN LIMITATION:** older rows keep
whatever shape was current when they were written. Because
`policy_version` is stored alongside, a reader can tell which shape to
expect — which is the reason that field is not optional.

## ADR-032
**FACT:** as originally delivered, `ProductEvidence.verification_status`
and `TrustRecord.verification_status` could be VERIFIED while the
`Evidence` row they point at was DRAFT, PENDING_REVIEW or REJECTED.
Nothing checked the two against each other. **FACT:** this was found by
independent review, not by the test suite — the Phase 7 tests verified
links without ever verifying the underlying Evidence, so they encoded
the defective behaviour as correct.
**INFERENCE:** a recommendation engine reading only the link's own flag
would treat a rejected study as verified support for a product claim —
precisely the failure sections 28 and 30 exist to prevent.
**DECISION:** establish the **two-layer verification invariant**. A
product-evidence link or trust record is EFFECTIVELY VERIFIED only when
its own `verification_status` is VERIFIED **and**
`Evidence.status == VERIFIED`. Enforced in two places, deliberately:
1. **Write time** (`commerce_service.verify_product_evidence` /
   `verify_trust_record`): refuses to mark something verified on top of
   unverified Evidence, returning 422 naming the Evidence's actual
   status.
2. **Read time** (`contracts/commerce.py::get_evidence_summaries` /
   `get_trust_summaries`): recomputes effective verification on every
   read by joining Evidence.
**Why both:** the write-time check alone is insufficient, because
Evidence can be rejected AFTER a link was legitimately verified.
Only the read-time computation catches that revocation. The read-time
check alone would allow the contradictory state to be stored and read
back confusingly. Either side being REJECTED makes the whole assertion
rejected: a rejected study cannot support a claim, and a rejected claim
is not rescued by a good study.
**TRADE-OFF:** the summary queries now join Evidence, and four existing
tests had to be updated because they asserted the old behaviour. Those
changes are behavioural corrections, documented in development.md's
Phase 7 hardening section rather than made silently.
**KNOWN LIMITATION:** effective verification is computed, not stored,
so there is no materialised "effectively verified" flag to query
directly in SQL. For current data volumes this is the right trade
(correctness over denormalisation); at scale a materialised view may
be warranted.

## ADR-033
**FACT:** nothing in the schema binds an `Evidence` row to a particular
product. Within one organization, Product B's lab report can be
attached to Product A as evidence for a claim about Product A, and
every tenant check passes because both rows are legitimately owned by
the same tenant. **FACT:** cross-tenant tests cannot catch this; it is
a same-tenant semantic problem.
**INFERENCE:** the system cannot判断 what a free-text evidence summary
is "about" without semantic understanding it does not have, and
building a semantic validator into Phase 7 would be both unreliable and
far outside its scope.
**DECISION:** do not attempt to prevent it. Instead, state the actual
guarantee precisely and test it:
- the pairing is always EXPLICIT (a human must write the claim),
- never INFERRED (the system makes no leap on its own),
- never AUTO-VERIFIED (links are born UNVERIFIED and contribute
  nothing until reviewed),
- and always ATTRIBUTED (verification is audit-logged with actor and
  timestamp).
`tests/test_same_tenant_semantic_scope.py` pins this down as a
documented limit rather than leaving it to be discovered later.
**KNOWN LIMITATION — stated plainly:** an earlier report described this
as an "evidence scope guarantee", which was too strong. The accurate
formulation is: **evidence scope is explicit and auditable, not
semantically guaranteed.** Software cannot stop a human from writing a
false claim and verifying it; it can refuse to do so itself, and record
who did.

## ADR-034
**FACT:** `Product.status`'s DRAFT → IN_REVIEW → PUBLISHED lifecycle,
and the refusal of a direct DRAFT → PUBLISHED jump, are not specified
in master spec section 26 — it lists a `status` field without
enumerating values or transitions.
**INFERENCE:** section 26 calls a Product "a normalized Product
Knowledge Object", and KnowledgeObject already has exactly this
lifecycle with section 44's never-auto-publish discipline behind it.
**DECISION / CLASSIFICATION:** this is an **engineering policy derived
by inference**, not a literal Master Spec requirement. Recorded as such
so a future reader does not mistake it for a spec mandate that cannot
be revisited.

## ADR-035
**FACT:** `TrustSubjectType` currently has three values (ORGANIZATION,
PRODUCT, CLAIM). **FACT:** section 30's trust chain names far more
subjects: website, business identity, supplier, origin, product,
quality evidence, testing, reviews, policies, customer experience.
**DECISION:** keep the three-value MVP vocabulary for now — modelling
all ten would be speculative — but record explicitly that
`TrustSubjectType` is an **MVP vocabulary that must remain
extensible**, not a settled architectural boundary. If SITE, SUPPLIER,
OFFER, REVIEW or POLICY subjects are genuinely needed later, the choice
between extending the enum and reshaping the subject model should be
made then, on evidence.

## ADR-036
**FACT:** master spec §38 says the WordPress plugin "should handle
authentication" but specifies no mechanism. **FACT:** the codebase had
only JWT user authentication; a WordPress installation is a machine,
not a user. **INFERENCE:** building a WordPress-shaped API-key table
would mean building a second one for MCP and a third for the next CMS.
**DECISION:** a generic `Installation` + `InstallationCredential`
model. `AdapterType` (wordpress/rest/mcp/other) makes WordPress one
value, not the model. Resolution chain is
`credential -> installation -> organization`; **tenant is derived, never
client-supplied** — no request schema in Phase 9 accepts an
`organization_id`. Secrets are bcrypt-hashed via the existing
`security/passwords.py` (no second hashing scheme), returned once,
never recoverable. Rotation retires rather than deletes, so audit
entries referencing old keys still resolve. Revocation is terminal.
All authentication failures return one generic 401 to prevent key_id
enumeration, with a timing-equalisation hash on the not-found path.
**TRADE-OFF:** more model than a WordPress-only key would need.
**KNOWN LIMITATION:** no webhook signature verification — unnecessary
for client-initiated calls over TLS, necessary if Phase 10 adds
WordPress-initiated webhooks.

## ADR-037
**FACT:** since Phase 5, children carried `organization_id` and a parent
FK as two independent constraints; the database could not reject
`Offer.organization_id != Product.organization_id`. Deferred twice.
**INFERENCE:** adding `wordpress_mappings` with the same shape would
make it a fifth instance of a known defect.
**DECISION:** migration `0010` adds `UNIQUE (id, organization_id)` to
each parent (semantically a no-op, existing only as a composite FK
target) and replaces each child's single-column FK with a composite
one, covering offers, product_evidence (×2), product_relations (×2),
recommendations (×3), and the new Phase 9 tables.
**TRADE-OFF:** eight FK replacements in one migration; downgrade must
restore them in strict reverse order (verified).
**KNOWN LIMITATION:** polymorphic pointers (`trust_records.subject_id`,
`research_task_references.reference_id`, `wordpress_mappings.object_id`)
cannot be closed this way — SQL has no FK to "one of several tables".
They remain service-enforced and are tracked as `P1-poly`.

## ADR-038
**FACT:** §38 requires WordPress to remain thin with Cloud Core as
source of truth. **DECISION:** `wordpress_mappings` is the ONLY place a
WordPress concept (`wordpress_post_id`, `wordpress_post_type`,
`wordpress_url`) exists in this codebase. No Core model gains a
WordPress field. Nothing in Core reads the mapping table to decide
anything about a product or knowledge object — it records where a Core
object was *projected*, never what it *is*.
**Idempotency is structural:** `UNIQUE (site_id, object_type,
object_id)` and `UNIQUE (site_id, wordpress_post_id)` mean a webhook
delivered five times yields one row because the database says so, not
because the handler remembered. Remapping an object to a *different*
post returns 409 rather than silently overwriting — losing the record
of where it used to be would be a silent truth change.
**KNOWN LIMITATION:** the PHP plugin itself is not built; Phase 9
delivers the Core-side boundary only.

## ADR-039
**FACT:** no rate limiting existed anywhere. **DECISION:** Redis fixed-
window counter keyed by `installation_id`, applied to `/adapter/**`
only. **Ordering is the design:** authenticate (cheap) → rate limit
(one INCR) → Core work. Limiting before authentication would mean
limiting by IP, ineffective for a plugin on shared hosting; limiting
after Core work would defeat the purpose. This is what makes "cheap →
deterministic → filtered → expensive only when necessary" enforceable
rather than aspirational.
**TRADE-OFF — fail-open:** if Redis is unreachable the request
proceeds. A cache outage becoming a total integration outage is the
worse failure, and Redis is not a hard dependency elsewhere in the
request path. `/health/ready` reports Redis degradation so it is
visible. The decision point is isolated in one module if this needs to
become fail-closed.
**KNOWN LIMITATION:** fixed window, not sliding — sufficient for burst
protection, less precise about burst shape.

## ADR-040
**FACT:** the Phase 0 known-issue "live and ready health checks need
separate implementation" was **stale**: they were already separate,
implemented in Phase 1. It survived four review cycles and was nearly
re-implemented in Phase 9.
**DECISION:** introduce `docs/ai-context/DEBT_REGISTER.md` as the
single authoritative lifecycle record for carried-forward debt, with
stable IDs traceable into ADRs and test names, and mark
`KNOWN_ISSUES.md` as descriptive rather than authoritative.
**INFERENCE:** a debt list that is only ever appended to will
accumulate items that are already fixed, and a reader cannot tell which
are real. Ownership and status must be tracked, not just description.

## ADR-041
**FACT:** master spec §38 lists "WooCommerce hooks" among the WordPress
plugin's responsibilities, while §62 assigns WooCommerce to Phase 10, and
§40 defines `commerce_mappings` as Phase 10 work. The two sections are in
tension. **DECISION:** Phase 9 registers exactly ONE WooCommerce hook,
`woocommerce_update_product`, and routes it to the same product-identity
mapping path a normal `save_post` uses. **What is deliberately NOT built:**
`commerce_mappings`, order/cart/checkout hooks, price or stock
synchronisation, and any Woo-specific data model. **INFERENCE:** a Woo
product is a WP post; refreshing its mapping is §38's "product
synchronisation", whereas *commerce* synchronisation (price, stock, orders)
is the thing §40 reserves for Phase 10. **TRADE-OFF:** a reader of §38 alone
may expect deeper Woo behaviour in Phase 9. **KNOWN LIMITATION:** if you
intend §38's "WooCommerce hooks" to mean more than identity projection, this
interpretation needs revisiting before Phase 10 — it is the one genuine
spec ambiguity in Phase 9 and is recorded rather than silently resolved.

## ADR-042
**FACT:** §38 requires schema rendering; no Core read endpoint existed for
it, and `AdapterScope.CATALOG_READ` was defined but unreachable.
**DECISION:** add `GET /adapter/catalog/{product_id}` returning product
identity plus at most one chosen offer. Offer selection reuses the Commerce
contract's own `is_purchasable` rule rather than reimplementing it, so the
adapter cannot form a second opinion about purchasability.
**The projection deliberately carries NO evidence and NO trust data.**
**INFERENCE:** structured data is a public assertion. An adapter able to
read verified claims could publish them as schema.org markup, and the
cheapest way to guarantee it never does is not to give it the material.
**TRADE-OFF:** a future adapter wanting to render review or certification
markup will need a new, separately-reasoned endpoint — which is the point:
that decision should be made deliberately, not inherited.

## ADR-043
**FACT:** the repository contained zero CSS and zero JS before Phase 9
(verified by file search), so no design system existed to reuse.
**DECISION:** define a small semantic-token layer that EXTENDS WordPress
admin rather than replacing it: spacing/radius/surface/status tokens, status
pills, cards, form fields, an empty state, and a table that reflows to
stacked cards under 782px. It binds to `--wp-admin-theme-color` so it
follows the user's admin colour scheme instead of fighting it.
**Techniques from the external references were assessed and mostly
rejected:** GSAP, Lenis, WebGL, Three.js, scroll choreography, custom
cursors and View Transitions are built for marketing sites; on an admin
settings screen they cost performance and motion-sensitivity risk for no
user benefit. **What WAS adopted** is the anti-pattern discipline: no emoji
as icons (inline SVG only), focus rings never removed, colour never the sole
signal (every status is icon + word + colour), `prefers-reduced-motion`
respected, `forced-colors` handled, 40px minimum control height, readable
measure capped at ~52-70ch, and real `<label>` elements rather than
placeholder-as-label.
**KNOWN LIMITATION:** none of this has been verified by rendering — see
ADR-044.

## ADR-044
**FACT:** visual verification was attempted, not assumed. Puppeteer 24
installed successfully in this environment; its Chrome binary download from
`storage.googleapis.com` is outside the network allow-list, and the apt
`chromium-browser` candidate is a snap that cannot run in this container.
**STATUS: ENVIRONMENT BLOCKED** — no screenshot was taken and no rendered
measurement was made. **DECISION:** ship the verification apparatus rather
than a claim: `tests/visual/harness.html` reproduces the real admin markup
against the real stylesheet, and `tests/visual/shoot.js` measures (not
merely captures) horizontal overflow, clipped elements, sub-12px text,
minimum control height and focus-ring presence at 375/768/1024/1440.
Anyone with network access reproduces the check in about two minutes.
**KNOWN LIMITATION:** reflow, contrast ratios, focus rendering, and
WordPress integration (keyboard traversal, screen-reader announcement,
block-editor meta box, alternate admin colour schemes, RTL) remain
unverified. They are listed individually in `tests/visual/README.md` rather
than summarised as "UI untested".

## ADR-045
**FACT:** the first version of `AIOL_Credentials::save()` accepted any
`http://` or `https://` endpoint. **INFERENCE:** an installation token is a
bearer credential; over plaintext HTTP it is readable by anything on the
path and replayable indefinitely. Allowing `http://` "for convenience" is
how a development shortcut reaches production.
**DECISION:** refuse `http://` unless the **parsed host** is exactly
`localhost`, `127.0.0.1` or `::1`. The check is on the parsed host, never a
substring — `http://localhost.attacker.com` is refused, and a test asserts
that specific bypass fails.
**TRADE-OFF:** a merchant with an internal HTTP-only Core on a private
network must terminate TLS or use a tunnel. That is the correct trade: the
alternative is silently shipping bearer tokens in clear text.

## ADR-046
**FACT:** the legacy bot monitor matched 18 User-Agent strings and logged
"GPTBot visited", storing IP address and full request URI.
**INFERENCE — two separate problems.** (1) A User-Agent is a *claim*, not an
identity; anyone can send `ClaudeBot`. Presenting a header match as fact is
the same error as treating unverified evidence as verified. (2) "Bot vs
human" is the wrong axis: a crawler indexing for later, an AI answering a
user's live question, and an agent acting on a user's behalf are three
different things with different commercial meaning, and a boolean cannot
express it.
**DECISION:** `AIOL_Actors` classifies into HUMAN / SEARCH_CRAWLER /
AI_CRAWLER / AI_USER_AGENT / AGENT_TOOL / UNKNOWN, and every observation
carries a confidence of DETECTED / PROBABLE / VERIFIED / UNKNOWN. **Nothing
is ever VERIFIED**, because reverse-DNS and published-IP-range verification
are not implemented — a test asserts this, so the field cannot quietly start
lying. `ChatGPT-User` and `Claude-User` are reclassified from "AI bot" to
AI_USER_AGENT, since a person asked.
**PRIVACY, narrowed:** no IP address is stored anywhere (a test greps the
whole plugin for `REMOTE_ADDR`), no query string, path only, UA truncated to
120 chars, cap lowered 300 → 200, and humans are not logged at all.
**KNOWN LIMITATION:** AGENT_TOOL has no signatures yet — the actor type
exists so Phase 10+ has somewhere to put agentic traffic, not because it can
currently be detected.

## ADR-047
**FACT:** the legacy plugin computed a single 0–100 "AI Readiness Score"
from seven boolean checks.
**INFERENCE:** the number implied an authority it did not have. It could not
distinguish "we checked and it is fine" from "we could not check", it
implied a relationship to real AI visibility that was never measured, and a
merchant could not act on it — 72/100 does not say what to fix.
**DECISION:** no composite score. `AIOL_Diagnostics::dimensions()` returns
seven named dimensions, each with a state and the counts behind it. Two are
genuinely measurable by the adapter (technical discoverability, machine
readability); five are explicitly **UNKNOWN — "measured in Cloud Core, not
by this adapter"** rather than a fabricated zero. `UNKNOWN` is a first-class
check result, so an unreachable robots.txt reports "could not determine"
instead of the legacy behaviour of scoring it as failure.
**TRADE-OFF:** no single headline number to show a merchant. That is the
intent: a number that cannot be acted on is worse than an honest list.

## ADR-048
**FACT:** the legacy AI Gateway (274 lines) exposed `ai-access-toolkit/v1`
with its own API keys, its own per-IP rate limiter and its own content
contract.
**DECISION: REPLACE, not migrate.** Cloud Core is the canonical API. A
second canonical API inside WordPress is a second source of truth by another
name — it would need its own auth, its own tenancy, its own rate limiting
and its own versioning, all of which Core already owns and does better
(installation identity, derived tenancy, per-installation limits).
**The plugin registers no REST routes at all**, and a test asserts
`register_rest_route` appears nowhere in the source.
**What survived:** the *transport* role, as `/llms.txt` and `?aiol_format=md`
(ADR-049). Those serve WordPress's own published content and claim no
authority, which is a legitimate adapter job.

## ADR-049
**FACT:** llms.txt and Markdown output were legacy "optimization" features.
**DECISION:** retained as **representations**, with an explicit header in
every response stating they are a view of published WordPress content and
not verified business data. **No price, stock, evidence or trust data ever
appears in them** — those reach the public only through `AIOL_Schema`, which
renders what Core asserts. A test asserts `price` appears nowhere in
llms.txt output.
**Invalidation widened:** the legacy version hooked `save_post`,
`deleted_post`, `trashed_post` — missing the cases that matter most.
Unpublishing left a post listed until the cache expired. Now
`untrashed_post`, `transition_post_status` and `aiol_mapping_changed` also
invalidate. Published-only is enforced at generation as well as routing,
because a filter could widen the query.

## ADR-050
**FACT:** master spec §38 requires WooCommerce hooks; §40 defines
`commerce_mappings`; §62 assigns WooCommerce to Phase 10. Phase 9 recorded
the §38/§40 tension as unresolved (ADR-041).
**RESOLUTION, now settled:** Phase 9 registered identity projection only;
Phase 10 owns commerce. The directional rule:

    WooCommerce owns : its own post/variation IDs, and the merchant's
                       operational price and stock
    Cloud Core owns  : what the product IS, whether it may be recommended,
                       its evidence, its trust

**DECISION:** WooCommerce may write exactly one thing into Core — an Offer's
price/stock/availability, via
`POST /adapter/commerce/mappings/{id}/offer`. **There is no route on the
adapter surface that reaches Product identity, Product status,
ProductEvidence, TrustRecord or Recommendation** — not "no permission for",
but no route. §27's Product/Offer separation is what makes that containment
possible: had price lived on Product, a price sync would necessarily have
been a write to the product record.
**Re-pointing a Woo product at a different Core product returns 409**, not a
silent rewrite — that would move a merchant's evidence and trust history
onto another product.
**TRADE-OFF:** a merchant who renames a product in WooCommerce will not see
the name change in Core. Correct: Core's name is the reviewed one.

## ADR-051
**FACT:** §41 lists `sync_jobs` with `attempts` and `status` but does not
enumerate status values.
**DECISION:** add `DEAD_LETTER` beyond the obvious set.
**INFERENCE:** without it, a job that has exhausted its retries is
indistinguishable from one that failed once and will be retried. Those need
opposite operator responses — the first needs a human, the second needs
patience. `attempts` lives on the row rather than in the broker, because a
counter held only in the broker is lost when the broker is, and DEAD_LETTER
would then be unreachable deterministically.
**KNOWN LIMITATION:** `MAX_ATTEMPTS = 5` is a documented constant, not a
tuned value — there is no production retry data to tune against.

## ADR-052
**FACT:** `commerce_mappings.woo_variation_id` is NULL for simple products.
Postgres' default unique-constraint behaviour treats NULLs as distinct, so
two simple products on one site could both claim the same `woo_product_id`.
**DECISION:** use `UNIQUE NULLS NOT DISTINCT` (PostgreSQL 15+; verified
running on 16.15). A test asserts two simple products cannot share a Woo ID,
and that a simple product and a variation do not collide.
**TRADE-OFF:** raises the minimum PostgreSQL version. Accepted — the
alternative is a partial index pair that is easy to get subtly wrong.

## ADR-053 (Phase 9 reconciliation)
**FACT, found by forensic reconciliation and not by the Phase 9 test
suite:** `aiol_mapping_changed` was registered as a listener in
`AIOL_Representations` but **never fired by anything**. ADR-049 claimed a
mapping change invalidated representations; it did not. Unlinking or
re-pointing a post left stale llms.txt output until the TTL expired.
**DECISION:** fire the hook on both the link-change and unlink paths, and
assert with a regression test that it is fired — not merely that a listener
exists. Also replaced an instance-to-static `$this->cache::flush_all()` call
with an explicit static call.
**Recorded prominently because the lesson generalises:** a passing test
suite did not catch a hook that was never called, since nothing tested the
*wiring* between publisher and subscriber. Tests that assert a listener is
registered prove nothing about whether anything triggers it.

## ADR-054
**FACT:** offer sync issues an HTTP call per product, inline in the request.
For one price edit that is correct and cheap. For a 5,000-product CSV
import, a WP-CLI run, or a 200-row bulk edit it is 5,000 synchronous calls
inside one PHP request — timeout, half-synced catalogue, retry storm.
**DECISION:** a per-request budget (`MAX_SYNCS_PER_REQUEST = 20`). Past it,
the adapter stops calling Core and **persists** the remaining product IDs to
an option, scheduling a cron drain that processes them in slices and
re-schedules itself while work remains.
**The two properties are in tension and both are tested:** the guard must
(1) stop calling Core, and (2) not lose the work it stopped doing. A guard
that only did (1) would silently drop syncs — worse than being slow, because
the merchant would believe the catalogue was in sync.
**Verified by mutation testing**, three ways: disabling the threshold,
removing the persistence, and removing the guard's call site each break a
distinct assertion.
**KNOWN LIMITATION:** the drain uses WP-Cron, which on a low-traffic site
only fires when someone visits. A large import may therefore take a while to
finish. Real-time bulk sync needs a server cron or the Celery path from
Phase 5, and is not built.

## ADR-055
**FACT:** R1 (a hook with a listener and no publisher) went undetected by
110 passing tests, because every test asserted a listener *existed* and none
asserted anything *fired* it.
**DECISION:** `tests/test-wiring.php` scans the whole plugin and requires
every custom `aiol_*` hook to have both ends, plus that every
`[$this, 'method']` callback names a method that actually exists.
**The test was itself wrong on the first attempt, and mutation testing
caught it.** It scanned raw source, so a *commented-out* `do_action` counted
as a publisher — meaning it could not have caught R1, the bug it was written
for. Re-scanning with `token_get_all()` to strip comments fixed it, and
re-running the mutation (commenting the `do_action` back out) now fails 2
assertions as it should.
**This is recorded as an ADR rather than a footnote because the lesson is
general:** a test written to catch a bug class must itself be verified
against that bug class. "The test passes" and "the test would fail if the
bug returned" are different claims, and only the second one is worth
anything.

## ADR-056
**FACT, found by Phase 10 forensic reconciliation:** master spec §51 lists
sorting among required API capabilities. No endpoint had it — 98 routes,
zero `sort_by`. Pagination, filtering, request IDs, consistent errors and
versioning were all present; sorting alone had been missed since Phase 1 and
never noticed because no test asked for it.
**DECISION:** `SortParams` + `apply_sort()` in `schemas/common.py`.
`sort_by` is validated against an explicit **allow-list mapping public field
names to model attributes**, never interpolated — so the API contract is not
tied to column names, and a column rename does not break consumers.
**An unknown sort field is a 422 naming the permitted values, not a silent
fallback.** Silently ignoring a sort request is worse than refusing it: a
consumer paginating through results gets a different order on every page and
never learns why.
**KNOWN LIMITATION:** applied to the shared helper, not yet threaded through
every one of the 98 routes. Each list endpoint adopts it as it is next
touched; recorded in the debt register rather than claimed as complete.

## ADR-057
**FACT:** an external AI system consuming a JSON API will present what it
receives as the whole picture. `{"claims": []}` reads as "nothing notable";
`{"evidence_strength": 0.0}` reads as "bad". Neither conveys "we have not
established this yet", which is the true state most of the time.
**DECISION:** every agent-facing response carries a `coverage` block —
claim counts by standing, an explicit `SignalState`, and human-readable
caveats — and it is **never omitted**, including on empty results. A
knowledge object with no claims returns `evidence_state: unknown` plus the
caveat "No claims have been recorded for this object yet."
**INFERENCE:** this is the Phase 8 UNKNOWN-vs-NEGATIVE rule (ADR-028)
crossing the system boundary. Enforcing it internally while letting the
external interface flatten it would defeat the point, because the external
interface is where the claim actually gets repeated to a person.
**TRADE-OFF:** more verbose responses. Accepted — the alternative is an
agent confidently reporting absence as a finding.

## ADR-058
**FACT:** §63 fixes MCP as a *future/secondary* agent interface and REST as
primary. §58 says keep the architecture extensible without prematurely
implementing future functionality.
**DECISION:** Phase 11 does **not** build an MCP server. It builds
`GET /api/v1/ai/capabilities` — an unauthenticated, self-describing manifest
of what this API answers, what it refuses, and what its honesty guarantees
are. That is precisely the thing an MCP server would wrap, so adding one
later is a translation layer rather than a redesign.
**Unauthenticated on purpose:** a client must be able to discover the
contract before it holds a credential.
**TRADE-OFF:** an MCP client cannot connect today. Correct per §63 — and
building an MCP server now would have meant guessing at a protocol binding
before any consumer exists to validate it.

## ADR-059
**FACT:** §33 states the internal recommendation score is a decision signal,
not a rating, and explicitly not Google/ChatGPT/AI ranking.
**DECISION:** `/ai/ask` returns **no numeric score of any kind** — only rank
position, evidence/trust `SignalState`, and caveats. A test asserts that
`final_score`, `relevance_score`, `evidence_score`, `trust_score` and
`availability_score` never appear in the response body.
**INFERENCE:** a 0-1 float that leaves the building will be multiplied by
ten and quoted as "9.2/10" by the first consumer that renders it. Rank
position carries the ordering information an agent actually needs and cannot
be misquoted as a rating.
**The endpoint delegates ranking entirely to Phase 8** rather than scoring
locally — otherwise an external agent and the merchant's own dashboard could
give different answers to the same question, and neither would be wrong.

## ADR-060
**Supersedes the "KNOWN LIMITATION" recorded in ADR-056.** Sorting is now
threaded through every applicable route; `P11-sort-rollout` is closed.

**FACT:** the repository has **150** `/api` routes, of which **41** return
`Page[...]`. An earlier Phase 11 report said "98 routes" — that figure
counted unique paths rather than method×path and is corrected here.

**DECISION:** 39 of the 41 collection routes take `SortParams`. Two are
deliberately excluded, and the exclusions are asserted by test so they
cannot silently grow:

| Excluded route | Reason |
|---|---|
| `GET /knowledge/search` | Relevance-ordered. An arbitrary sort discards the ranking that is the entire point of a search endpoint. |
| `GET /query-clusters/{id}/members` | Similarity-ordered against the cluster representative. The order IS the information. |

**Single implementation:** `SORTABLE_FIELDS` in `schemas/common.py` maps
**public field name → model attribute** for 32 models (153 permitted
fields). The indirection is deliberate: the API contract is not tied to
column names, so a column rename does not break consumers, and an internal
column is excluded from the contract simply by being absent.
`secret_hash` is absent from `InstallationCredential` for that reason, and
a test asserts it.

**Deterministic pagination:** every sort appends `id ASC` as a tiebreak.
Without it, sorting by a non-unique column (status, category, price) lets
Postgres order ties freely, so page 2 can repeat or skip rows from page 1.

### Two wiring bugs the rollout itself produced

Recorded because they are the phase's most transferable lesson:

1. **Routes passing `sort=sort` without accepting a `sort` parameter** —
   `NameError` 500 on every request. Two routes; caught by the full
   regression, not by the sorting tests.
2. **Routes accepting `sort` and never passing it on** — the parameter is
   accepted, returns 200, and is silently ignored. Three routes.

**The second is worse than the first.** A 500 is loud. A silently ignored
sort is exactly the silent-fallback failure this feature exists to
prevent — a client sends `?sort_by=name`, receives 200, and gets default
ordering with no indication anything was wrong.

**Neither was caught by the signature-level coverage test**, which
inspected function signatures and found them correct. The bodies were not.
That is the R1 lesson recurring: *structure verified, behaviour not.*
`test_sort_wiring_is_complete_in_both_directions` now asserts both
directions statically via AST, and
`test_every_collection_route_actually_responds` calls every collection
route and fails on any 5xx.

**KNOWN LIMITATION:** cursor pagination is not implemented; `limit`/`offset`
remains the contract. Offset pagination over a mutating dataset can still
skip or repeat rows even with a stable sort — the tiebreak fixes ordering
determinism, not snapshot isolation. Recorded in the debt register.

## ADR-061
**FACT:** master spec §31 lists `mentioned`, `cited`, `recommended`,
`product_present`, `url_present` — names that read naturally as booleans.
**DECISION:** they are a tri-state `SignalPresence`
(PRESENT / ABSENT / NOT_CHECKED), defaulting to NOT_CHECKED.
**INFERENCE:** a boolean `false` cannot distinguish "we looked and the
brand was not cited" from "we did not check for citation". Those are
completely different facts, and a dashboard that averages them produces a
number that is simply wrong — quietly, with no symptom. This is the same
UNKNOWN-vs-NEGATIVE rule as ADR-028 (recommendation) and ADR-057 (agent
responses), now applied to observation.
**TRADE-OFF:** callers must state what they checked, which is more work
than passing booleans. That is the intended cost.

## ADR-062
**FACT:** §31's prose names seven signals that must stay distinct —
Mention, Citation, Recommendation, Product Display, URL, **Click**,
**Purchase** — while its column list gives five.
**DECISION:** Click and Purchase get **no columns**, and a test asserts
their absence.
**INFERENCE:** this is the correct reading rather than an omission. A click
happens in the user's browser on a platform this system cannot observe; a
purchase happens on the merchant's own site and belongs to commerce. Giving
them columns would create a place to write values that could only ever be
guesses, and a guessed conversion figure is worse than no figure.
**KNOWN LIMITATION:** the merchant genuinely cannot see AI→click→purchase
attribution from this system. Saying so is the honest answer; a later phase
connecting real analytics could change it.

## ADR-063
**FACT, from Phase 12 forensic reconciliation (F7):** no budget or cost
guard existed anywhere in the codebase before this phase.
**INFERENCE:** every prior phase's work cost database and CPU time, bounded
by the merchant's own hosting. Phase 12 is the **first phase able to spend
external money** — each platform probe may be a paid API call — and a
monitoring loop with a bug is exactly the shape of thing that produces a
large bill overnight.
**DECISION:** `VisibilityBudget`, checked **before** the probe. A budget
discovered to be exceeded afterwards is an invoice, not a guard.
**A missing budget means a limit of ZERO, never unlimited** — "not
configured" and "unlimited" must never be the same state. Refusal is
**402, not 403**: the caller is authorised, there is simply no budget left,
and a client needs to handle those differently.
**TRADE-OFF:** `period_spent` is a counter rather than a live sum of
`estimated_cost`. Summing every check would slow the guard precisely as
usage grows. Drift is bounded by one probe.

## ADR-064
**DECISION:** `GET /visibility/summary` returns counts split
present/absent/not_checked plus an honest `checked` denominator and a
`caveats` list. It returns **no score, no percentage, no ranking**, and a
test asserts none of those words appear in the response.
**INFERENCE:** §31's entire point is that the seven signals are not the
same metric. A composite number would undo that in one field. This is the
third time the project has refused a headline number, for the same reason
each time: ADR-047 (no AI readiness score), ADR-059 (no score leaves the
building), and now this.
**The `checked` denominator is the load-bearing detail.** Observations that
never examined a signal must not enlarge its denominator — reporting
`1 present of 3 observations` when only 2 were examined invents a rate.

## ADR-065
**MarkItDown is the primary document NORMALIZATION engine — not the
Document Intelligence engine.**

**FACT (measured in this environment, MarkItDown 0.1.7, real fixtures):**

| Claim | Measured |
|---|---|
| preserves PDF tables | **FALSE** — `tables.pdf` flattened to `Compound Amount Unit / Mannitol / Glucose / Water / 42.1 / 18.7 / 12.0`, rows and columns scrambled |
| preserves embedded images | **FALSE** — `with_image.pdf` returned only `See figure below.`; the figure vanished silently |
| OCR plugin covers images | **FALSE for these cases** — with `enable_plugins=True` the image is still dropped; a PNG passed directly returns **0 characters** |
| fails safely on malformed input | **FALSE** — `broken.pdf` returns the literal string `"None"`, a silent garbage success |
| DOCX/XLSX tables | **TRUE** — correct Markdown tables |
| Persian / mixed script | **TRUE** — `۴۲ گرم`, correct ی/ک, no mojibake |

**DECISION:** MarkItDown owns exactly one stage of the pipeline —
normalization. Structure extraction, tables, images, OCR and vision are
**our** layer built around it:

```
Original File → Secure Intake → Validation/Quarantine
 → MarkItDown Conversion            (MarkItDown)
 → Document Structure Extraction    (ours)
 → Table Extraction / Validation    (ours: pdfplumber)
 → Embedded Image / Figure Extraction (ours: pypdf)
 → OCR when required                (ours: tesseract, Level 3)
 → Vision only when required        (policy-gated, NOT built)
 → Canonical Markdown Artifact
 → Structured Document Artifacts
 → Semantic Chunking → Entity/Claim/Evidence → Knowledge Object
```

**INFERENCE:** assigning MarkItDown the other stages would make the
architecture depend on capabilities that measurably are not there. The
failure mode would be silent — a dropped figure and a flattened table both
look like a successful conversion.

**TRADE-OFF:** more moving parts than "just call MarkItDown". Accepted: the
alternative is losing tables and images without noticing.

**KNOWN LIMITATION:** scanned-page OCR and figure/chart semantics are **not
built**. They are recorded as deferred with an explicit owner, not implied.

## ADR-066
**Dependency selection for the extraction layer — and one rejection.**

Every dependency below was chosen after measuring it here. Popularity was
not a criterion; in the one case where the most popular option was also the
fastest, it was **rejected on licence**.

| Dependency | Version | Licence | Role | Measured evidence |
|---|---|---|---|---|
| `markitdown[pdf,docx,pptx,xlsx]` | 0.1.7 | MIT | normalization | correct on text PDF, DOCX, XLSX, Persian |
| `pdfplumber` | 0.11.10 | **MIT** | PDF tables | ruled table extracted perfectly; unruled recovered via `text` strategy; **0.013s/page** |
| `pypdf` | 6.18.1 | **BSD-3-Clause** | embedded images | extracted the 1,947-byte PNG MarkItDown dropped |
| `pytesseract` + `tesseract` | 5.3.4 | Apache-2.0 | OCR (Level 3) | read `FIGURE yield by year` from the extracted image |

**REJECTED: `PyMuPDF`.** Metadata reports
`Dual Licensed - GNU AFFERO GPL 3.0 or Artifex commercial`. For a
network-served commercial Cloud Core, AGPL's network-use clause is a serious
obligation, and the alternative is a paid Artifex licence. It is the fastest
and most popular option, which is exactly why the rejection is recorded:
**licence is a hard blocker, not a footnote.**

**NOT ADOPTED:** `camelot` (requires Ghostscript, itself AGPL, for a job
pdfplumber already does) and `unstructured` (very large dependency tree that
overlaps MarkItDown's own role). Neither adds capability we lack.

**A correction worth recording:** pdfplumber initially appeared to fail —
zero tables from `tables.pdf`. The cause was **my fixture**, which reportlab
had drawn without grid lines, not the library; the default strategy is
`lines`. A ruled fixture extracted perfectly. Concluding "pdfplumber cannot
do tables" from the first result would have been wrong and would have led to
adopting a heavier dependency for no reason. The implementation therefore
tries `lines` first and falls back to `text`.

**Security considerations, per dependency:** all parse untrusted input and
must run in the Cloud Core worker, never in WordPress. `pdfplumber` and
`pypdf` are pure Python (no subprocess, no network) but need page and time
bounds. `tesseract` is a **subprocess over untrusted image bytes** — the
sharpest edge — and needs a timeout, bounded input and no shell.

**Cost-aware routing (Levels 1–4)** and the full capability/fallback table
are in `docs/audits/DOCUMENT_INTELLIGENCE_CAPABILITY_MATRIX.md`. The level
used is recorded per document so a reader can tell cheap extraction from
expensive interpretation.

## ADR-067
**FACT (G8, found by the Phase 0–12 audit):** the only Markdown in the
system was `AIOL_Representations::markdown()` in the WordPress plugin,
which renders **WordPress `post_content`** — WordPress's copy of the text,
not the canonical Knowledge Object.
**INFERENCE:** that is exactly the drift §12 forbids. Two representations of
"the same" knowledge existed with no mechanism keeping them consistent and
no way for a consumer to know which was authoritative.
**DECISION:** Markdown, JSON and JSON-LD are all generated from the
canonical Knowledge Object by `knowledge_representation.py`:
`/knowledge/{id}/markdown`, `/representation`, `/jsonld`. Markdown is a
**derived artifact** (§13), never a source of knowledge.
**Claim status is rendered in every format.** A draft claim and an approved
one must not look identical — a consumer that cannot tell them apart will
quote both with equal confidence.
**JSON-LD publishes only approved, evidence-backed claims.** A draft claim
emitted as structured data is a public assertion the merchant cannot
support — the rule ADR-042 applied to product markup, applied to knowledge.
**KNOWN LIMITATION:** the WordPress plugin still renders `post_content` for
its own pages. Wiring it to fetch the canonical representation is Phase 9
adapter work and is recorded in the debt register, not silently done here.

## ADR-068
**FACT (P12-17):** `VisibilityJobStatus` was created during Phase 12 and
referenced exactly once — its own definition. It shipped as a PostgreSQL
enum type in migration 0012 and was never used by any model or service.
**It is self-inflicted dead architecture: I introduced it while auditing
others for the same fault.**
**DECISION:** remove it. The canonical job model is `SyncJob` (Phase 10),
extended with `RETRYING` and a `DOCUMENT_INGESTION` job type rather than a
second job system. Migration 0014 drops the dead type.
**INFERENCE:** two job-state vocabularies would be a duplicate domain. The
contract's rule — extend the canonical model if it can be extended — points
the same way.

## ADR-069
**FACT (P12-16):** budget enforcement was read → decide → write. Two
concurrent probes each reading 0.04 against a 0.10 limit both concluded
they fit and both proceeded, spending 0.12.
**DECISION:** atomic reservation. A single conditional `UPDATE` evaluates
the limit and applies the increment in one statement; `rowcount == 0` means
exhausted. Reservation happens **before** execution, with
`release_reservation()` on failure and `settle_reservation()` once the real
cost is known.
**`estimated_cost` is never assumed to equal `actual_cost`.** A cheaper
provider refunds the difference; a dearer one consumes it even past the
limit, because the money is already spent and a ledger that disagrees with
the invoice is worse than one that shows an overspend.
**Verified by real concurrency tests** — separate threads on separate
committed connections. A test that serialised the callers would have passed
against the broken code and proved nothing.
**Two test defects mutation testing exposed:** the tenant-isolation test did
not materialise the second tenant's budget row, so an unfiltered UPDATE had
nothing to corrupt; and my first race test used arithmetic under which
*neither* reservation could fit, so the correct implementation refusing both
looked like a failure. Both fixed.

## ADR-070
**FACT (P12-01):** ingestion discarded the uploaded bytes and wrote
`storage_path=None`. Irreversible — once a converter upgrade makes better
Markdown possible, there is nothing left to reconvert.
**DECISION:** content-addressed retention at
`<root>/<organization_id>/<sha256[:2]>/<sha256>[.ext]`, written **before**
conversion so a crash during conversion does not lose the source.
**The uploaded filename never enters the path.** It is recorded as data;
the path is the hash. That is what makes `../../etc/passwd.pdf` inert
rather than merely unlikely, and a test asserts it.
**Tenant enforced twice:** the document row is tenant-scoped, and the store
refuses any resolved path outside the caller's tenant directory — so a
wrong database row cannot become a cross-tenant file read.
Stored mode `0600`; downloads are `attachment` + `nosniff` so a stored
HTML/SVG original cannot execute in the caller's origin.
**KNOWN LIMITATION:** filesystem backend. An object store slots in behind
the same interface; what matters is that the bytes are kept and addressable.

## ADR-072
**FACT (P12-07):** `app/ingestion/url_source.py` contained a complete SSRF
implementation — scheme/port allow-lists, per-hop redirect validation, DNS
resolution with **every** resolved address checked, connection pinned to the
validated IP, streamed size enforcement — and **no route called it**. A
security control that no code path reaches protects nothing.
**DECISION:** `POST /documents/ingest-url` wires it, and the fetch runs in
the **worker**, not the request.
**INFERENCE — the placement is a security property, not a latency one.**
Fetching in the request handler makes the API itself the SSRF probe and its
timing observable to the caller, which is the difference between a
rejection and a port scanner. A caller now learns only that a job failed.
**`UrlRejected` is a PERMANENT failure:** a blocked target is blocked
identically on every retry, so retrying would turn a rejection into a slow
internal port scan.
**Idempotency is tenant-scoped** and keyed on the normalized URL plus
source — two organizations ingesting the same public article are doing two
separate legitimate things. Normalization drops default ports and fragments
but **preserves the query string**, because `?id=1` and `?id=2` are
different documents.
**Verified by 7/7 mutations**, including removing the route's
`validate_url` call — the exact original defect.

## ADR-073
**FACT:** consolidating the async work revealed **two job-runner
implementations**: `ingestion_jobs.py` (added while implementing P12-02) and
`ingestion_job_service.py`. Both created jobs, marked states and recorded
outcomes.
**DECISION:** keep `ingestion_job_service.py` and delete the duplicate. It
is the better design: `run_ingestion_job(db, job_id)` is session-agnostic,
so the Celery task is a thin wrapper and the real chain is testable without
a live broker. A task that owns its session cannot be driven by a caller
that already has one.
**This is the third duplicate-abstraction incident in this phase** (four
ingestion implementations, three job schemas, now two job runners). They
share a cause: appending a new implementation instead of locating the
existing one. The forensic sweep for duplicates is now part of the phase
checklist rather than an afterthought.

## ADR-074
**P12-18 Visibility infrastructure.**

**FACT (forensic baseline):** `Query`, `Intent`, `SyncJob`, `VisibilityTest`,
`VisibilityBudget` and `KnowledgeGap` already existed. `Snapshot`,
`Competitor` and a visibility provider package did not.

**DECISION — what is REUSED rather than rebuilt**, because the previous
phase produced four ingestion implementations and two job runners by
appending instead of locating:

| Contract concept | Resolution |
|---|---|
| VisibilityQuery | canonical `Query` — a visibility query IS a query |
| VisibilityObservation | existing `VisibilityTest`, extended with project/run links |
| VisibilitySource | `VisibilityPlatform` + `VisibilityCollectionMethod` already model surface and method; a table would add one row per enum value |
| Job lifecycle | `SyncJob` (ADR-068) |
| Budget | `VisibilityBudget` (ADR-069) |
| Gaps | `KnowledgeGap` referenced, never duplicated |

Four models are genuinely new: Project, Run, Snapshot, Competitor, Event.

**`PARTIAL` earns its place:** a run over twenty queries where three
providers failed is neither SUCCEEDED nor FAILED, and forcing it into
either loses the distinction an operator needs to decide whether to re-run.

**A failed probe is PERSISTED, not dropped.** Dropping it would shrink the
denominator and inflate every rate computed from the run. It is recorded
with `provider_outcome` set and every signal NOT_CHECKED — never ABSENT,
which would convert "we could not ask" into "the brand is not there".

**Snapshots are immutable** and every rate ships its denominator
(`observations_tested`, never `observations_total`). A rate is `None`, not
`0.0`, when nothing was tested: 0.0 asserts a measured absence.

**Events carry no causal field** — no `cause`, `impact` or `attribution`
column exists, and a test asserts that. The system observes that a value
changed and cannot know why.

**Competitors:** `origin` distinguishes a brand the merchant named from one
the system merely saw, and `is_approved` is False for SYSTEM_DISCOVERED.
Declaring a brand a competitor without approval puts words in the
merchant's mouth.

**Provider boundary** follows the existing `app/integrations/` convention
(`Protocol` + `NotConfigured*`), not a new one. The default provider
returns NOT_CONFIGURED with all signals NOT_CHECKED — never an empty
success, which would read as "brand absent".

## ADR-075
**P12-19 Search intelligence.**

**DECISION:** `SearchObservation` is a separate table from
`visibility_tests`, and the columns are the evidence for why: a search
observation has position/URL/result-type; an AI observation has
mention/citation/recommendation tri-states. Neither set is meaningful for
the other, and one table would be half-null in every row with no way to
tell which half was legitimately empty. They share `query_id` and market —
the correct amount of sharing: same question, different kind of answer.

**No second Query system.** An imported query becomes a canonical Phase 6
`Query`, and normalization reuses `query_service.normalize_query` rather
than a second rule that could disagree about what counts as the same query.
The ORIGINAL text is stored verbatim; a Persian query stays Persian.

**Every metric is nullable, and that is the point.** Search Console reports
impressions but no URL ranking for some rows; a SERP provider reports
position but never impressions. NULL says "this source does not report it";
zero would claim a measurement that was never made.

**Provider failure is never an empty result.** `AUTH_REQUIRED` and a
genuine zero-row day are different facts, and the response carries
`data_retrieved` to separate them explicitly.

**Append-only.** A re-import is idempotent via `UNIQUE NULLS NOT DISTINCT`
and never overwrites — overwriting would destroy the history the feature
exists to provide.

**KNOWN LIMITATION:** no live Google Search Console or SERP credentials
exist here. The adapters, schemas, normalization, failure states and
fixtures are implemented and tested; **live provider execution is
ENVIRONMENT BLOCKED and is not claimed as verified.**


---

# Phase 13 — Analytics, Demand Intelligence and AI Access Control

## ADR-076 — The actor vocabulary moves to Core; the plugin keeps a generated mirror

**Status:** ACCEPTED (Phase 13)
**Supersedes:** nothing. **Extends:** ADR-046.

`AIOL_Actors` (ADR-046) already classifies actors, and Phase 13 does NOT
introduce a second classifier. What moves is the *vocabulary*: `ActorType`
and `ActorConfidence` become Core enums, and
`app/services/actor_signatures.py` becomes THE signature list.

**Why Core.** Core is the source of truth (§52), and a merchant with two
sites must see one agent list, not two. An access policy written against
"GPTBot" has to mean the same thing everywhere it is enforced.

**Why the plugin still holds a copy.** Classification runs in
`template_redirect` on every page load on shared hosting. A network round
trip there would put Core's latency on the merchant's critical path.

**Why the copy cannot drift.** `scripts/sync-signatures.php` generates the
PHP block from the Python list, and two tests — one per runtime — fail if
they differ, including on ORDER. Order is load-bearing: matching is
first-hit, so `Claude-User` must precede `ClaudeBot`, or a customer's live
question is classified as a training crawler and the merchant's "block
training" rule blocks their own customers.

**Rejected:** having the plugin call Core per request (latency, coupling);
having each runtime maintain its own list (drift, and the failure is
invisible — the edge blocks one thing while the report shows another).

**Confidence semantics are unchanged.** A User-Agent is a claim. Header
matches are `DETECTED`, never `VERIFIED`; nothing in Phase 13 can write
`VERIFIED`, because no reverse-DNS or published-IP-range check exists.

---

## ADR-077 — Access policy: four precedence levels, first match wins, default is "not configured"

**Status:** ACCEPTED (Phase 13)

One row is one decision: for this agent (or class of agent), fetching for
this purpose, the answer is free / paid / forbidden.

**Precedence, most specific first, first match wins, evaluation stops:**

```
30  agent + purpose          "GPTBot, for training"
20  agent, any purpose       "GPTBot, anything"
10  actor_type + purpose     "any AI crawler, for training"
 5  actor_type, any purpose  "any AI crawler, anything"
```

**Rejected: "strictest wins."** It is the plausible-looking alternative,
and it would make *"block all AI crawlers except this one"* impossible to
express — a policy merchants actually want. **Rejected: scoring or
combining rows.** A merchant must be able to read the table and predict
the outcome; an algorithm that blends four rows cannot be read.

**No rule matched ⇒ `NOT_CONFIGURED`, not `ALLOWED`.** Both let the
request through; only one is honest that nobody decided. The dashboard
counts undecided agents precisely so the absence stays visible instead of
hardening into de-facto policy. Defaulting to FORBIDDEN was rejected: it
would remove merchants from answer surfaces the day Phase 13 ships,
without anyone choosing that.

**Humans are never subject to a policy.** No configuration can return 403
to a customer's browser. A merchant who wants to block human traffic has a
firewall.

**`PAID` records intent and nothing more.** It produces HTTP 402 with a
`Link: rel="terms-of-service"`. There is deliberately **no price column**:
a number there would look like a working price when nothing in this
product meters, invoices or collects.

**Honest limit, stated on the dashboard rather than in a footnote:**
identification is by header, so this stops honest agents and does not stop
dishonest ones.

---

## ADR-078 — Page-view telemetry is append-only, idempotent, and NULL-preserving

**Status:** ACCEPTED (Phase 13)

**Idempotency.** Every observation carries a client-minted `event_key`
under a unique constraint. The adapter batches and retries; without this,
one retry inflates every count on the merchant's dashboard and nothing
afterwards can detect it. A redelivered batch is accepted, deduplicated,
and the response reports `accepted` and `duplicates` **separately** — the
caller is told rather than the duplicate being hidden.

**`dwell_ms` is NULL when nothing reported it.** A crawler that fetches
one URL and leaves reports no dwell. Writing 0 would claim "measured, and
it was instant", which is a different and false statement. Same rule as
ADR-075's search metrics. `mean_dwell_ms` is NULL, never 0, when
`dwell_samples = 0`.

**Counts are split six ways, not two.** "A training crawler took a copy"
and "an AI quoted this page to a customer 400 times" are the two facts the
merchant is trying to tell apart. A bot/human boolean collapses the only
distinction that changes what they do next.

**Buffer drops the OLDEST on overflow** and records the count. A full
buffer means the flush is failing; in that situation recent traffic is
what the operator needs, and the loss is recorded rather than silent.

---

## ADR-079 — IP address, geolocation and dwell time are collected, bounded, and never inferred

**Status:** ACCEPTED (Phase 13)
**Supersedes:** the privacy narrowing recorded in ADR-046.
**ADR-046 remains on file, unedited.**

**History, because this must not read as a silent reversal.** ADR-046
deliberately stored no IP and no query string: *"an adapter log is not an
analytics product."* The pre-Phase-13 UX checkpoint (§P.5) found that the
original design conversation had asked for geography and dwell time, and
declined to close the gap by default — recording it as an **owner
decision**, not a settled question. The owner has now decided to collect
all three. This ADR records that decision and its cost.

**What is kept from the old decision:**

* the query string is still never stored (a search term that matters is
  recorded deliberately as a `SearchDemandEvent`, not swept up from a URL);
* no cross-session visitor identifier is minted, anywhere;
* checkpoint §76/§77 stands: nothing infers a psychological state,
  receptiveness, or a purchase-readiness label from any of this.

**How the cost is bounded:**

| Column | Lifetime |
|---|---|
| `ip_address` (full) | nulled by `enforce_retention()` at `ip_retained_until`, default 30 days |
| `ip_truncated` (/24 v4, /48 v6) | permanent |

Historical analytics therefore keep working forever at network
granularity, and the identifying value has a life span the merchant can
point to. The full address is served only on a separate route, only to
OWNER/ADMIN, via a separate response model — a permission that hides a
field inside a shared handler is one refactor away from leaking it. It is
also **deliberately absent from the sortable allow-list**: sorting a
report by a visitor's IP is a lookup dressed as an ordering.

**Geolocation is never derived.** There is no bundled IP-geolocation
database, no lookup call, and no heuristic from TLD, language or timezone.
A location appears only when an upstream CDN or the adapter already
resolved it, and `geo_method` records which. Otherwise every geo column is
NULL and the dashboard reads *Not available* — a different statement from
"unknown country" and a very different one from zero. Coordinates are
rounded to 2 decimal places (~1 km): enough to say "Tehran", not enough to
say "this street".

**`X-Forwarded-For` is ignored unless the merchant declares a trusted
proxy**, because it is client-controllable: reading it by default would
let any visitor write whatever address they liked into the merchant's
analytics.

**Wiring a real geolocation provider is a documented follow-up, not
something this phase quietly faked.**

---

## ADR-080 — The content report reads a rollup, and the rollup is a full recompute

**Status:** ACCEPTED (Phase 13)

"Sort my content by how often it was seen, least to most and the reverse,
with the numbers" is an ORDER BY over a COUNT over every page view ever
recorded. Live, that is a full aggregate scan on every dashboard load —
fine on demo data, and exactly the anti-pattern §18 names.

`content_view_daily` is **derived data with a stated derivation**, not a
second source of truth: `page_views` stays authoritative and the rollup
can be dropped and rebuilt from it at any time. `recomputed_at` is shown,
because a stale rollup must be visible as stale (§68).

**Recompute, never increment.** An incremental counter that drifts is
undetectable; a recompute that can be re-run is verifiable by re-running
it, and a test does exactly that. `total_views` is denormalised for a
cheap sort and is asserted equal to the sum of its six components, so it
cannot become a seventh independent number.

**Dwell is stored as `total` + `samples`, not as an average.** Averaging
at write time loses the ability to re-average over a different window, and
a mean over 3 samples and a mean over 3,000 are not the same claim. The
dashboard divides and states how many samples it divided by.

---

## ADR-081 — A searched term IS a `Query`; demand events carry no text

**Status:** ACCEPTED (Phase 13)

`SearchDemandEvent` stores `query_id` and **no query text column**, the
same way `SearchObservation` did in ADR-075. Recording a search goes
through Phase 6's `normalize_query`, so a term typed by a customer and the
same term imported from Search Console resolve to one row and one demand
picture — instead of three tables holding three spellings of one string.

**Bot and human searches share the table** because the merchant's question
— "what is being asked for that we do not answer?" — has the same shape
either way, and the comparison is the point. `actor_type` keeps them
separable; a `bot_searches` table would have made the comparison a join
nobody writes.

**`result_count = 0` and `result_count = NULL` are not merged.** Zero
means "we searched and found nothing" — the most valuable row in the
table, a content gap with a date on it. NULL means the adapter did not
report it.

**This service may not set `Query.status`** (Phase 6 made CLASSIFIED a
consequence of having an Intent, never a manual assignment) **and may not
create a `KnowledgeGap`.** Closing the UX-21 demand→gap link is real work
with its own review; auto-filing gaps from search misses would produce a
gap list full of typos, which is a gap list nobody reads. Zero-result
terms are surfaced as *candidates* and stop there.

---

## ADR-082 — Subscription, Wallet and Entitlement are three aggregates, not one balance

**Status:** PROPOSED (Phase 13 billing follow-up — design only, not implemented)

The owner's billing prompt asks for a dashboard that answers "what plan
am I on", "how much AI budget remains" and "can I do this right now" as
three separate questions. They are modelled as three independent
aggregates rather than columns on one row: `Subscription` (current plan
and status), `Wallet` + `LedgerEntry` (AI processing budget), and
`Entitlement` (resolved per-request, never persisted as a stored
boolean). Merging them would mean a plan cancellation and a budget
exhaustion collapse into the same signal to the user, which they are not
— a canceled-but-still-in-period Pro subscription and an empty wallet are
different problems with different fixes (renew vs. top up).

See `docs/billing/BILLING_ARCHITECTURE.md` §2 for the full rationale and
`docs/billing/ENTITLEMENT_MATRIX.md` for the capability table
`EntitlementService` reads.

---

## ADR-083 — Entitlement is enforced once, server-side, at the mutation boundary

**Status:** PROPOSED (Phase 13 billing follow-up — design only, not implemented)

Every Pro-gated mutation calls `EntitlementService.require(org,
CAPABILITY)` before touching the database, following the exact
"frontend hiding is not authorization" principle `access_policy_service.py`
already states for AI access policy. A disabled button in the dashboard
is a courtesy; it is never the control. This closes the exact failure
mode the owner's prompt names at §60/§117: an expired user manually
calling the API and getting a queued job anyway because only the UI
checked the plan.

---

## ADR-084 — The billing ledger is append-only; wallet balances are a derived cache

**Status:** PROPOSED (Phase 13 billing follow-up — design only, not implemented)

`LedgerEntry` rows are never updated or deleted; `Wallet.available_cents`
etc. are a cache that must always be reconstructable by summing a
wallet's ledger entries. This is ADR-080's "recompute, never increment"
rule for `content_view_daily`, applied to money: an incrementing balance
that drifts from reality is undetectable, while a cache that can be
recomputed and compared is verifiable by actually recomputing it. A
correction is a new compensating entry (`MANUAL_ADJUSTMENT`, `REFUND`),
never an edit to a historical row.

---

## ADR-085 — The 7-day Pro trial is a unique, server-enforced `TrialClaim` row

**Status:** PROPOSED (Phase 13 billing follow-up — design only, not implemented)

`billing_trial_claims` carries `UNIQUE(organization_id)`. This constraint
*is* the anti-abuse mechanism for "cannot be claimed repeatedly by
logout/relogin" — a database guarantee, not a check that could be bypassed
by clearing cookies or calling the API directly. `start_at`/`end_at` are
set once, at claim time, server-side; the frontend never computes or
sends a trial window.

---

## ADR-086 — AI wallet spend follows reserve → settle → release, with an atomic conditional reservation

**Status:** PROPOSED (Phase 13 billing follow-up — design only, not implemented)

Before any AI-provider call that spends wallet budget, the reservation
step is a single conditional `UPDATE ... WHERE available_cents >=
:amount`, not a read-then-write — this is what actually prevents two
concurrent jobs from both successfully reserving the same remaining
balance (the race the owner's prompt names at §83/§235), not an
application-level lock that a second process instance could still race
against. Estimated cost and actual settled cost are separate ledger
entries so the two numbers — what the system predicted and what the
provider actually reported — are never silently merged into one figure.
See `docs/billing/BILLING_ARCHITECTURE.md` §4.

## ADR-087 — AI Resource Registry: Provider ≠ Account ≠ Model (tenant-scoped, bring-your-own-key)
**Status:** ACCEPTED (owner prompt 2026-09-25). **Context/Problem:** execution targets were strings and one environment credential; the owner requires many providers, several accounts per provider, dynamic models and switching. **Decision:** tenant-scoped relational tables `ai_providers`, `ai_provider_accounts` (independent credentials, usage, health, limits per account), `ai_models` (dynamic, per provider; nothing hard-coded), `ai_health_events` (history). **Alternatives:** a global platform catalogue (rejected: every table is tenant-scoped by project invariant, and platform-owned credentials imply platform AI credits, which are not approved). **Consequences:** discovery seeding is per tenant. **Tenant:** composite (id, organization_id) FKs. **Cost:** per-account token quota / spend limit, NULL when unknown. **Migration:** 0020, additive; 0017–0019 untouched.

## ADR-088 — Provider credentials: encrypted at rest, write-only
**Status:** ACCEPTED. **Decision:** Fernet (AES-128-CBC + HMAC-SHA256) keyed by `AI_CREDENTIAL_KEY` from the environment; without the key a credential is refused, never stored in clear. The API accepts a credential (PUT) and can delete it; it never returns it — only presence, a short fingerprint, and set/rotated/tested timestamps. Never logged. **Rejected:** deriving the key from `SECRET_KEY` (rotating the JWT secret would silently make every stored credential unreadable).

## ADR-089 — Six routing modes, deterministic and explainable
**Status:** ACCEPTED. **Decision:** `ai_routing_policies` (manual_single, manual_chain, stage_manual, auto_pool, auto_priority, hybrid) with ordered `ai_routing_steps`; the router is deterministic over registry state and returns ordered candidates plus a reason for every skipped candidate (disabled, unhealthy, quota, rate limit, no credential, no adapter, capability, stage, spend limit); each decision is persisted in `ai_routing_decisions` (auditable, answerable "why A, why not B"). Manual single never falls back; manual chain follows the user's order strictly. **Rejected:** opaque/ML scoring.

## ADR-090 — Shared AI Working Memory, AI jobs, checkpoint and handoff (native, canonical)
**Status:** ACCEPTED. **Decision:** `ai_jobs` (business parent of executions via the arc column `ai_job_id`) with relational `ai_job_items` (pending/completed/failed per item) and `ai_working_memory` (JOB_STATE, AI_HANDOFF, INTERMEDIATE_FINDING, OPEN_QUESTION, CURRENT_SYNTHESIS, NEXT_ACTION, CONFLICT_CONTEXT, PROCESSING_CHECKPOINT, AI_SUMMARY; versioned, never overwritten; provenance; tenant-scoped; idempotent). Before any switch (quota, rate limit, auth failure, timeout, manual switch) the job persists a checkpoint and a handoff package; the next resource resumes from it and completed items are never reprocessed. Pause / resume / cancel / retry-failed / manual switch are auditable controls. A worst-case cost estimate is checked against the job's limit before each call. **Distinct from:** Project Memory (documents), Knowledge Core (domain truth), AIExecution (invocation facts).

## ADR-091 — Walrus Memory: optional, non-canonical, not yet integrated
**Status:** ACCEPTED (boundary only). **Decision:** server-side boundary (health, namespace derived from the tenant, mirror write, recall); clients never submit a namespace; delegate credentials server-side only; native memory stays canonical. **Current state:** the Walrus HTTP contract has not been verified here (no endpoint, no credentials), so no client call is implemented — inventing endpoints would be a fake integration. Health reports DISCONNECTED / BLOCKED_EXTERNAL_DEPENDENCY; writes report "not mirrored".

## ADR-092 — Keyword & Query Workspace per Knowledge Object
**Status:** ACCEPTED. **Decision:** `knowledge_keywords` (kind, intent, source, volume, country, language, notes, priority, `raw` = the untouched imported row), import from CSV / Excel / TXT / JSON / manual with limits and a per-row report; "search new sources" creates research tasks from selected keywords and links them back (traceability keyword → research task). **Rejected:** keywords as a JSON array on the knowledge object.

## ADR-093 — AIExecution: account attribution, job parent, stop reason (Phase 16 lock preserved)
**Status:** ACCEPTED. **Decision:** additive `provider_account_id` and `ai_job_id` (composite tenant FKs, column-list ON DELETE SET NULL) and normalised `stop_reason`; `ai_job` joins the exclusive arc (now two columns: the cardinality CHECK finally has two parents to reject). All new columns are covered by the immutability trigger (links / outcome fact). One invocation = one execution; retry / fallback = new execution — unchanged.

## ADR-094 — Discovery Registry: a discovered name is not an integration
**Status:** ACCEPTED. **Decision:** `ai_discovery_entries` with the status machine DISCOVERED → IDENTIFIED → OFFICIAL_SOURCE_VERIFIED → … → ACTIVE and exception statuses; the owner's list is imported as DISCOVERED, types labelled as proposals, API / pricing / quota NULL until verified from an official source; nothing becomes ACTIVE automatically. **Rejected:** hard-coding applications and models in business logic.

## ADR-095 — Background Processing Policy: explicit opt-in per task type
**Status:** ACCEPTED (owner prompt §11–12, 2026-09-25). **Problem:** a connected account must NOT automatically be eligible for background processing; the owner must explicitly choose. **Decision:** `background_processing_policies` table (one active policy per tenant), `background_task_type_configs` (one row per task type × tenant), referencing `ai_routing_policies` so the existing six routing modes apply. Worker enforces the policy before dispatching any task; without a policy row for a task type the task is refused with POLICY_MISSING. **Alternatives:** flags on accounts (rejected: too coarse, cannot vary by task type). **Tenant:** organization_id on every row. **Migration:** 0021, additive.

## ADR-096 — Agent Orchestration Layer (provider-neutral, tenant-scoped)
**Status:** ACCEPTED (owner prompt §18–29, 2026-09-25). **Problem:** the project needs multi-agent coordination for complex research/content workflows without vendor lock-in. **Decision:** separate domain tables: `agent_definitions`, `agent_endpoints`, `agent_capabilities`, `agent_sessions`, `agent_tasks`, `agent_messages`, `agent_handoffs`, `agent_memory_bindings`. The existing `ai_agents` table (Phase 13) detects external crawler traffic — these new tables are a completely different domain. Agent tasks create AIExecution rows via the existing invocation layer (Phase 16 lock preserved). Routing considers capability, health, trust, permission, tenant. All messages are durable and auditable. **Alternatives:** adopting an existing orchestration framework (rejected: vendor lock-in, architecture mismatch). **Tenant:** composite organization_id FKs. **Migration:** 0021 alongside background processing.

## ADR-097 — AI Catalog as first-class navigation surface
**Status:** ACCEPTED (owner report "لیست AI را ندیدم", 2026-09-25). **Decision:** a dedicated `screen-ai-catalog` nav item shows the full discovery corpus (114+ entries) with search, filter by type/status/capability, and clear distinction of CONNECTED vs DISCOVERED vs APPLICATION_ONLY. This is a read-mostly screen backed by `/ai-center/discovery`. It does NOT replace the discovery tab in AI Center; it complements it with better discoverability.

## ADR-098 — Shared Memory Control screen
**Status:** ACCEPTED (owner report "قسمت اتصال و انتخاب حافظه مرکزی مشترک را ندیدم", 2026-09-25). **Decision:** two surfaces: (a) Settings → AI → Shared Memory: configure semantic backend (native / Walrus / future), memory profiles, permissions; (b) AI Center → Shared Memory: inspect runtime state, versions, handoffs, health, job bindings. PostgreSQL canonical store is always locked and cannot be replaced. Semantic backend is optional and additive.

## ADR-099 — Demand Intelligence: distinct real sources normalised into DemandSignal
**Status:** ACCEPTED (owner prompts 2026-09-25, REQ-DI-001..003). **Problem:** demand data (site search, Search Console, GA4, AI visibility, customer questions, product behaviour) must drive knowledge work without being merged or faked. **Decision:** `demand_signals` (source_type kept per row; one normalised shape; unknown metrics NULL; raw row kept; dedupe per source) and `demand_connections` (GSC / GA4 OAuth state). Implemented sources: `internal_search` (first-party telemetry, Phase 13) and `gsc_export` (owner-uploaded Search Console export). Live `gsc` / `ga4` connectors report `BLOCKED_EXTERNAL_DEPENDENCY` until OAuth client credentials exist — never simulated. Promotion: signal → information need → research task (`research_task_id`, traceable). **Rejected:** a single merged demand score; estimated/synthetic behaviour data. **Tenant:** organization_id on both tables. **Migration:** 0023, additive.

## ADR-100 — Per-user preferences in Cloud Core; fixture screens labelled explicitly
**Status:** ACCEPTED (REQ-SET-001, Phase 14 completion, 2026-09-27). **Decision:** `user_preferences` (one row per user, composite tenant FK, language/theme/font/notifications) served only as `/users/me/preferences` (no user id in the path — nothing to tamper with). Dashboard screens that have no backend by design (support, chat, billing — not established requirements) or that are per-object design samples show an explicit "DEMO / FIXTURE DATA" label when connected, instead of silently showing sample content. **Rejected:** browser-only preference storage (not persistent across devices; not the owner's requirement).

## ADR-101 — Pilot-ready research: found ≠ read, compound evidence is indirect
**Status:** ACCEPTED (owner prompt 2026-09-27). **Decision:** (1) Sources carry five separate facts — existence, content access (what the system *holds*: full_text_available / abstract_only / metadata_only / restricted / unavailable / unknown), rights, acquisition paths (DOI, publisher, PubMed, Europe PMC, library, open-access locations) and review status; a database CHECK forbids `full_text_available` unless `full_text_accessed` is true. (2) Federated research runs Crossref, PubMed (E-utilities) and Europe PMC against fixed official hosts; each provider's failure is recorded and never removes another provider's results; results are deduplicated by DOI, then PMID, then canonical title. (3) Discovery creates sources only; the research agent creates *pending* evidence candidates only from text the system actually holds (abstract); verification is a human decision in which the reviewer states what the study tested. (4) A research question with a compound runs four separate routes (direct subject, compound in humans, mechanism, co-occurrence); a CHECK makes compound / mechanistic / co-occurrence evidence INDIRECT, and the evidence map reports each route separately and never infers an effect of the subject from compound evidence. (5) The research engine never edits a knowledge object. **Rejected:** treating a provider hit as a reviewed source; merging compound evidence into subject evidence. **Migration:** 0025, additive.

## ADR-102 — Login page: typed slogan, interactive field, advisory VPN/proxy notice
**Status:** ACCEPTED (owner request 2026-09-27). **Decision:** the login screen shows a typed slogan (lead line + rotating typed phrase with caret, English and Persian, a stable `aria-label` for screen readers, static under `prefers-reduced-motion`), and an original canvas dot field behind the auth screens that bulges under the pointer and tilts/turns when dragged (colours from design tokens, paused when hidden, no drag on touch). A VPN/proxy notice is **advisory only**: `GET /auth/network-check` reports proxy headers (Via, Forwarded / X-Forwarded-For beyond `TRUSTED_PROXY_HOPS`, known proxy headers), never echoes the IP or header values, and never blocks sign-in or sign-up; "Check again" re-runs it. Consumer VPNs without headers need an IP-reputation service — not configured (`ip_reputation: not_configured`). **Rejected:** blocking sign-up behind a VPN (owner: recommend only); copying third-party site code (the effects are re-implemented).

## ADR-103 — Auth pages v2 and the brand mark
**Status:** ACCEPTED (owner request 2026-09-27). **Decision:** login, sign-up and code pages share a split layout — a dark brand panel (particle sphere that rotates, bulges under the pointer and turns when dragged; typed slogan; three proof points) and a clean form column (Google first, then email; one primary action per page). New brand mark: three rounded petals in violet → cyan → pink gradients around a light core, outside any circle, with a slow "breathing" scale/glow (static under reduced motion); colours are design tokens (`--logo-a/b/c`, `--logo-core`, `--on-brand`, `--auth-ink-*`) in `frontend/design-system/tokens.css`; standalone file `frontend/brand/aiol-logo.svg`. Security/SEO: `noindex, nofollow` and a strict referrer policy, `autocomplete` (`username email`, `one-time-code`), `method="post"` forms (no email in URLs), honeypot on sign-up, explicit unchecked consent, https-only website field, generic lock messages, one descriptive title per page. The layout follows the common split sign-up pattern; no third-party code or artwork is copied.
**Amendment (owner, 2026-09-27):** the brand mark keeps the original shape (a hub with five connected nodes, as in the previous design) — only its colours change: violet → cyan → pink gradient on the connectors, a light-to-cyan-to-violet hub, nodes in the three brand colours, no enclosing circle, staggered breathing (hub, nodes, glow). The petal mark is withdrawn.

## ADR-104 — Wallet, ledger, reservations, payments and webhooks (implements the ADR-082..086 billing design)
**Status:** ACCEPTED (owner prompt sections 12–14, 2026-09-28, which list wallet reservation/settlement, insufficient balance, payment idempotency, webhook replay and billing isolation as required tests). **Decision:** tenant wallet in integer cents; append-only `wallet_ledger_entries` (DB trigger refuses UPDATE/DELETE) with a unique idempotency key per entry; balances are derived (available = sum of entries; reserved = held reservations); reserve → settle (hold released, actual charged) / release; `402` when the available balance is short; payments with a unique idempotency key; provider webhooks verified by HMAC-SHA256 over `timestamp.body`, a ±5-minute window, and a unique event id — a replay is acknowledged but never credits twice; amount/currency mismatch never credits. Only the `sandbox` provider (development) exists; with no provider configured the wallet reports `BLOCKED_EXTERNAL_DEPENDENCY` and top-ups are disabled. Plans, subscriptions and trials from the draft remain DESIGNED_ONLY. **Migration:** 0026.

## ADR-105 — Live progress (SSE), memory export, full-text acquisition
**Status:** ACCEPTED. `GET /ai-center/jobs/{key}/events` streams job snapshots (text/event-stream, tenant-scoped, ends at a terminal state or after 10 minutes; browsers read it with fetch so the bearer header is sent). `GET /ai-center/memory/export` returns working memory (all versions), memory profiles and agent handoffs as one JSON document (owner/admin, audited, no-store). `POST /research/sources/{id}/acquire-full-text` fetches only a recorded open-access location through the SSRF-guarded fetcher and sets `full_text_accessed` only when a document of at least 4 000 converted bytes exists; anything else changes nothing and says why.
**Amendment 2 (owner, 2026-09-28) — the mark tells the product's idea.** Five scattered source dots of different sizes (articles and content spread around the world) flow along clockwise curves into one rounded diamond core with a light spark (one unified piece of knowledge). Animation: a short pulse travels along each curve into the core, sources breathe in sequence, the core breathes; reduced motion shows the static mark. File: `frontend/brand/aiol-logo.svg`. The auth pages also show the same idea as a background: a breathing constellation behind the form column whose points briefly connect.
**Amendment 3 (owner, 2026-09-28) — final mark.** A filled round core, slightly larger than its surroundings, with five hollow satellite circles of different sizes connected by straight spokes that meet the core perpendicularly at uneven (random-looking) lengths: scattered sources joined into one unified piece of knowledge. Breathing only (scale + glow), no rotation; static under reduced motion. The auth pages carry the same idea as a scattered field of breathing points behind the form column (no connecting lines).

## ADR-106 — Passwordless organization sign-up
**Status:** ACCEPTED (owner prompt section 3, 2026-09-28). **Problem:** the sign-up page is passwordless, but `/auth/register-organization` required a password. **Decision:** `signup_codes` holds a pending sign-up — organization name, owner name, email and an **HMAC of the 6-digit code** (never the code) — and nothing is created in `organizations`/`users` until the code is verified, so an unverified request cannot occupy a name or an address. Rules: 10-minute expiry, one-time use (`consumed_at` set before anything is created), at most 5 wrong attempts per request, a 60-second resend cooldown, 5 requests per email and 20 per IP per hour, and an identical `202` answer for an address that already has an account (no enumeration, and no code sent). `users.password_hash` becomes nullable: a passwordless owner has no password, and `authenticate()` refuses password login for such a user, so only the emailed code can sign them in. Registration is audited as before (`organization.registered`). The password endpoint stays for existing accounts. **Migration:** 0027 (down-migration writes a non-matching placeholder hash before restoring NOT NULL). **Tests:** `tests/test_passwordless_signup.py` — 12 cases.

## ADR-107 — Source access states and user-supplied full text
**Status:** ACCEPTED (owner prompt sections 13–15, 2026-09-28). **Decision:** `sources.content_access` gains `title_only`, `landing_page_only`, `paywalled`, `registration_required`, `access_blocked` beside the existing states, and a person can record what they actually found (`POST /research/sources/{id}/access-state`) — that route can never set `full_text_available`. The user may obtain an article legally and upload it (`POST /documents/upload`, then `POST /research/sources/{id}/attach-full-text`): the claim is made only when the upload parsed into ≥ 4 000 bytes, otherwise the source is left untouched and the reason is returned. New columns record provenance: `full_text_origin` (`open_access_fetch` | `user_upload`), `full_text_document_id`, `access_checked_at`, `access_blocked_reason`, plus an `access_history` entry in `metadata_`; a DB CHECK refuses a full-text claim without an origin. The attachment is audited (`source.full_text_attached`). **Migration:** 0028. **Tests:** 5 in `tests/test_progress_export_fulltext.py`.

## ADR-108 — Full indirect-evidence route vocabulary and multi-compound reasoning
**Status:** ACCEPTED (owner prompt §17–18, 2026-09-29). **Decision:** evidence routes become `direct_subject`, `compound_human`, `mechanistic`, `co_occurrence`, `indirect_taxonomic`, `indirect_analogous_species`, `indirect_formulation`, `combination`, `background`, `general`; a database CHECK keeps every route except `direct_subject`/`general` INDIRECT, so no reviewer action and no direct SQL can turn a compound, species, formulation or combination study into direct evidence for the subject. A research question carries **several** compounds and related species (taken from the knowledge object's `compound` and `related_entity` keywords when not supplied); each route is searched with its own query and the results are never merged — the combination route searches the compounds *together*. Each evidence row records `evidence_about` (the subject, one compound, a combination, or a species). `GET /research/questions/{id}/evidence-graph` returns the labelled graph subject —contains→ compound —studied_in→ study —reports_outcome→ outcome; a `contains` edge is marked `documented: false` unless a reviewed source actually documents it, and every `studied_in` edge carries its route and directness. **Rejected:** inferring a clinical effect of the subject from the presence of a compound. **Migration:** 0029. **Tests:** 8 new (34 in the research suite).

## ADR-109 — Source dependency, independent evidence count, and research saturation
**Status:** ACCEPTED (owner prompt §20, §22, 2026-09-29). **Decision (§20):** `source_dependencies` records that one source rests on another (`cites`, `reviews`, `reanalyses`, `same_study`, `preprint_of`, `retracts`, `corrects`). Only `reviews`, `reanalyses`, `same_study` and `preprint_of` group sources together — a source that merely *cites* another is still an independent finding. Grouping is transitive, so twenty reviews of three trials report **three** independent findings, and that number appears in the evidence map. Dependencies are never guessed: each one is recorded by a person or a provider, with `detected_by`. **Decision (§22):** every search round is recorded in `research_iterations` (seen, new, duplicates, providers ok/failed). Saturation is computed from those facts and reports one of `query_variants_exhausted`, `low_marginal_yield`, `duplicate_sources_only`, `budget_reached`, `user_limit_reached`, `no_new_relevant_evidence`, `provider_unavailable`, `not_saturated`. All providers failing is explicitly **not** saturation. The response always states that this is an operational stopping condition over the configured providers, never a claim that the literature has been exhausted. A person can declare or reopen the search. **Migration:** 0030. **Tests:** 9.

## ADR-110 — Memory Center, extraction confidence, conflict intelligence
**Status:** ACCEPTED (owner prompt §9, §19, §21, 2026-09-29).
**§9 Memory Center:** `/memory/search` (text inside the content, kind, job key, knowledge object, date range, latest-version-only, sortable), `/memory/items/{job}/{kind}/versions` and `/compare` (a field-by-field diff between two versions), and `/memory/export.{json|jsonl|csv|zip}` produced by the backend — never assembled in the browser — scoped, audited, owner/admin only, carrying provenance and no credentials. A dedicated Memory Center screen exposes all of it.
**§19 extraction confidence:** `evidence.extraction_confidence` (0–1) records how sure we are that *the source says this*; it is separate from `evidence_strength`, which rates how strong the science is. A database CHECK forbids a machine extraction from claiming certainty (`1.0`) before human review, and another keeps the value within range.
**§21 conflicts:** `evidence_conflicts` records each supports/contradicts pair on a claim with a side-by-side comparison (population, sample size, design, directness, route, dates, what was read) plus `differs_on` and `not_recorded`, in states `unreviewed → under_review → partially_resolved → resolved | unresolvable`. The system never chooses a side; a database CHECK refuses a resolution without a written reason, and every review is audited. **Migration:** 0031. **Tests:** 10.

## ADR-111 — Research query sets, evidence completion, new gap types, job counters
**Status:** ACCEPTED (owner prompt §12, §16, §23, §32, 2026-09-29). **Decision:** `research_query_sets` saves an editable keyword/term set per knowledge object (distinct from the Phase 13 demand `query_clusters`), re-runnable with a run count so results can be compared over time. `evidence_completion_tasks` names what is still missing for a claim or gap, with the route and directness that would satisfy it; a database CHECK refuses `satisfied` without naming the evidence, and refuses `blocked`/`abandoned` without a written reason; the service additionally refuses evidence that is unreviewed, of the wrong directness, or on the wrong route. Gap types gain `structure_gap`, `retrieval_gap`, `ux_gap`, `commerce_gap`. `ai_jobs` gains `retry_count` and `switch_count`, incremented at every checkpoint and exposed on the job view (§32). **Migration:** 0032. **Tests:** 10 + the §43 acceptance scenario.

## ADR-112 — §43 acceptance scenario
**Status:** ACCEPTED. `tests/test_acceptance_taranjabin.py` walks all twenty steps of the owner's scenario in one test on the production code path: keyword cluster, discovery across three providers, deduplication, abstract-only and title-only states, open-access locations, user upload, parsing, attachment with provenance, candidate extraction, human review, direct vs indirect, extraction confidence beside evidence strength, the labelled graph, conflict detection, dependency grouping, gap and completion task, Find More, iteration, stopping condition, and a person updating the knowledge object. No scientific conclusion is asserted — what is asserted is that the system never overstates what it holds.

## ADR-111 — Research query sets, evidence-completion tasks, named modes, new gap types, job counters
**Status:** ACCEPTED (owner prompt §11, §12, §16, §23, §32, §43, 2026-09-29). **§12:** `research_query_sets` saves an editable set of keywords, extra terms and a query mode per knowledge object (distinct from the Phase 13 `query_clusters`, which group observed demand queries); running one records `run_count` and `last_run_at` so results can be compared over time. **§16:** `evidence_completion_tasks` name what is still missing, which route and which directness would satisfy it; a task can only be satisfied by a *reviewed* piece of evidence on the required route and directness, and `blocked`/`abandoned` require a written reason — both enforced by database constraints. **§11:** a research question declares its mode (`gap_driven`, `user_driven`, `exploratory`, `continuous`) and the project records it; a gap-driven project must name the gap it came from. **§23:** `structure_gap`, `retrieval_gap`, `ux_gap`, `commerce_gap` added. **§32:** `ai_jobs.retry_count` and `switch_count` are incremented at every checkpoint and exposed on the job view. **§43:** `tests/test_acceptance_taranjabin.py` runs all twenty acceptance steps through the production code path, asserting only what the system recorded — including that direct human evidence for the subject is absent unless a study of the subject itself was reviewed. **Migration:** 0032. **Tests:** 17.

## ADR-111 — Research query sets, evidence completion, new gap types, job counters
**Status:** ACCEPTED (owner prompt §12, §16, §23, §32, 2026-09-29). **Decision:** `research_query_sets` saves an editable named set of keywords, extra terms and a mode for one knowledge object, which can be re-run and compared over time (`run_count`, `last_run_at`); it is distinct from the Phase 13 `query_clusters`, which group observed demand queries. `evidence_completion_tasks` name what is still missing for a claim or gap, with the route and directness that would satisfy it; a task can only be marked satisfied by **reviewed** evidence that matches both, and `blocked`/`abandoned` require a written reason — all three enforced by the API and by database CHECKs. `GapType` gains `structure_gap`, `retrieval_gap`, `ux_gap`, `commerce_gap`. `ai_jobs` gains `retry_count` and `switch_count`, incremented at every checkpoint and exposed on the job view (§32). **Migration:** 0032. **Tests:** 10 + the 20-step acceptance test `tests/test_acceptance_taranjabin.py`.

## ADR-114 — Category schema, knowledge sections and the Master Topic Matrix
**Status:** ACCEPTED (owner prompt v3.0 §11–§16, 2026-09-30). **Decision:** a real `categories` table rather than overloading `knowledge_objects.object_type`. The matrix needs a section schema per category, a status row per topic × section including the ones that do not apply, and a schema version so a recomputed matrix stays auditable; an unvalidated `String(100)` that is only ever compared with `==` can carry none of that. **`object_type` is untouched** and no data is migrated: `knowledge_objects.category_id` is nullable, and a topic without a category behaves exactly as before.
**Tables:** `categories` (slug unique per tenant, `schema_version`), `section_definitions` (the schema; `origin` = category_schema | discovered | user_added, with the discovering topic and evidence recorded), `knowledge_sections` (one cell per topic × section), `section_propagations` (§16).
**Rules enforced in the database, not only in code:** a cell in `not_applicable` or `no_evidence_found` must carry a written reason; a cell in `error` must keep its `last_good_status` (§78 — never replaced by zero); skipping a cross-topic proposal needs a note.
**Derived status:** a cell's state is computed from the claims linked to it via the new `claims.section_key`, the evidence linked to those claims, open conflicts and gaps — never asserted. Statuses a person set deliberately (`not_applicable`, `field_research`, `experiment_required`, `user_input`, `outdated`) are never re-opened by a recalculation.
**Cross-topic propagation:** a section discovered on one topic creates a **pending proposal** for each sibling; nothing is written into a sibling's knowledge until a person decides. This is what prevents a discovery on one plant from fabricating a section on another.
**Migration:** 0033 (reversible, verified base → head → base → head). **Tests:** 12.

## ADR-115 — Coverage Audit: six dimensions, versioned, failure-safe
**Status:** ACCEPTED (owner prompt v3.0 §17–§24, §71–§73, §77–§78, 2026-09-30). **Decision:** one `coverage_audits` table holding a *run*, at topic, category or organization scope. Every figure is counted from tables that already exist (`sources`, `documents`, `evidence`, `claims`, `claim_evidence`, `knowledge_gaps`, `evidence_conflicts`, `knowledge_sections`); the audit is a cache with provenance, not a second knowledge base.
**Six dimensions, never collapsed (§19):** source, processing, knowledge, evidence, section, publication. There is deliberately no overall completeness figure anywhere in the module — a topic can have every section present and almost no evidence behind them, and the audit must show exactly that.
**Unknown is never zero (§29 of the prohibitions):** a percentage is returned only where the denominator is real; otherwise `null` with a stated reason. Sections closed with a written reason are excluded from the section denominator rather than counted as failures. Publication and citation coverage report `null` with a note, because no publication layer exists yet.
**Versioned (§24):** every run is a new `audit_version`; the history is queryable, so how coverage moved stays auditable.
**Failure-safe (§78):** a failed run is its own row with a mandatory `failure_reason` (enforced by a CHECK). `current_view()` then returns the **last successful audit**, marked `stale`, with the failed attempt's reason beside it — never an empty or zeroed audit. `never_run` is said plainly rather than shown as 0%.
**Category scope is cross-topic (§22):** per-section documentation across the category, the weakest sections, stale topics and pending cross-topic evaluations — never a sum of topic rows.
**Performance (§77):** the Dashboard reads the prepared row; `/coverage` never recalculates, only `/coverage/run` does.
**Migration:** 0034 (reversible, verified). **Tests:** 12.

## ADR-116 — Publication layer and sentence-level Vancouver citation
**Status:** ACCEPTED (owner prompt v3.0 §33–§67, §81–§88, 2026-09-30). **Decision:** five tables — `publications`, `publication_sections`, `publication_sentences`, `sentence_sources`, `publication_references` — arranged so that prose cannot exist without the sources that produced it. `add_sentence()` takes the **claim** a sentence came from and derives its sources through the existing claim → evidence → source chain (§42); there is no entry point that writes text first and looks for citations afterwards.
**Numbering (§36–§39, §45):** sentences are walked in document order; a source new to the publication takes the next number, a source already seen reuses its number forever. Deterministic — the same content resolves identically every time, verified by test.
**Range compression (§40):** only genuinely consecutive runs of three or more become ranges. `1,3,5` never becomes `1–5`; `4,5` is written out; `1,2,3,7,8` → `1–3,7,8`. Ten consecutive sources render `(1–10)` and are never truncated (§82).
**No fabrication (§61, §87, §88):** a factual sentence with no validated source is marked `evidence_unavailable` and rendered with **no** citation — never `(1)` or `(999)`. A database CHECK refuses to mark such a sentence resolved with neither a citation nor that flag. References are formatted only from stored `Source` fields; a field that is not stored is omitted, and a record with no bibliographic metadata is written as an explicit placeholder rather than invented.
**One number, one source (§57, §59):** two unique constraints — a number cannot belong to two sources, a source cannot hold two numbers. Duplicate ingestions collapse to a canonical source by DOI, then PMID, then URL (never by title alone), so a paper ingested twice takes one number.
**Support, not relevance (§48):** `sentence_sources` records the claim and evidence that justify each citation, and attaching a source that does not support the claim is refused with 409.
**Indirect stays indirect (§49):** each sentence-source carries the evidence's `directness` through to the rendered output.
**Versions (§46, §67):** a new publication supersedes the previous one, which keeps its own numbering intact.
**Citation Integrity Audit (§59–§60):** nine checks plus three separately reported coverage figures — presence, validity and support — which are never merged into one score.
**Migration:** 0035 (reversible, verified). **Tests:** 22, covering every case the prompt enumerates in §81–§88.

## ADR-117 — Dashboard screens for categories, coverage and publications
**Status:** ACCEPTED (owner prompt v3.0 §5, §13–§15, §71–§73, 2026-10-05). **Decision:** three screens added to the **existing** dashboard shell — same nav, screen picker, page header, live-panel, field, table and chip patterns; no second dashboard. All three read live from the endpoints of ADR-114/115/116 and show nothing until Cloud Core is connected.
**Categories & matrix:** category picker and creation with a starter schema; the Master Topic Matrix as a sticky-header, horizontally scrollable table with one button per cell. Status is never colour alone — every cell carries its word and a glyph (✓ documented, ? needs research, ⇄ conflicting, ∅ no evidence found, — not applicable…). A cell opens a panel to set its status; closing a section demands a reason, as the API does. Per-topic Apply schema and Recalculate, and the queue of cross-topic proposals with "needs research" / "does not apply (why?)".
**Coverage audit:** topic or category scope; a CURRENT / STALE / never-run banner that keeps the last good audit on screen when the newest run failed; the six dimensions as equal boxes, each with its headline figure or the word **Unknown**, its counts and its note; the category view shows the weakest sections across topics; run history.
**Publications & citations:** pick a topic and a version, add sentences from claims, create a new version (the old one keeps its numbering), resolve. The document renders each sentence with its own Vancouver citation; an evidence-unavailable sentence is marked with a wavy underline and carries no number. The numbered reference list and the nine integrity checks with presence / validity / support shown separately.
**Resolver refinement:** sources first cited together in one sentence are numbered in the order their evidence was attached (then by id), so "Study 1" is reference 1 — still deterministic. One test added.
**Verified:** in the browser against a real backend at migration 0035 with seeded data — 3 topics × 19 sections, 2 pending proposals, six coverage dimensions with two honest Unknowns, and a publication rendering `(1–10)`, `(11–14)` and an unsupported sentence with no number. Dashboard rules 33/33; 48 screens × 6 widths × LTR/RTL with 0 overflow and 0 small targets; English locale clean.

## ADR-118 — Website management: blog, page sections, newsletter
**Status:** ACCEPTED (owner request, 2026-10-06). **Decision:** the public website is administered from the main dashboard through four new tables (migration 0036, additive, reversible) and two groups of endpoints.
**Posts** (`site_posts`, `site_post_revisions`): one row per language (`en` / `fa`); an English post and its Persian translation share a `translation_group`, which the public API exposes as the `alternate` so the site can link them with hreflang without guessing from slugs. Every edit increments the version and stores a revision with a note — that list is the article's public update history. A database CHECK refuses a published post without a publication date and an author; the API also refuses to publish an empty body.
**Sections** (`site_sections`): per page and per language — shown or hidden, order, optional heading override. Seeded on first use from the home page's real 19 sections in their real order. The hero carries the page's only H1 and cannot be hidden (422).
**Subscribers** (`newsletter_subscribers`): a CHECK makes `consented_at` mandatory, and the consent wording is stored with it. The public subscribe endpoint is rate-limited per client (/24), silently drops honeypot submissions, never reveals whether an address is already on the list (the same 202 either way), and re-subscribes a former subscriber only on fresh consent. Unsubscribe is by an unguessable token. Admins can export CSV (cells beginning `= + - @` are neutralised against spreadsheet formula injection), mark someone unsubscribed, or erase the row entirely.
**Access:** admin endpoints are owner/admin only and tenant-isolated; list endpoints use the shared `apply_sort`. Public endpoints are addressed by organisation slug and return only published posts and section settings.
**Site wiring:** the static site works unconnected (shipped articles; newsletter opens a mail draft). Setting `api` and `org` in `assets/js/site-config.js` makes the blog list read published posts and the newsletter form store consented subscribers.
**Dashboard:** three screens in the existing shell — Website: blog, Website: page sections, Website: subscribers. Dashboard rules 33/33.
**Tests:** 9 (drafting, history and publishing, public visibility, the database guard, linked translations, sections and the hero rule, consent / probing / honeypot, token unsubscribe, CSV export and erasure, admin-only and isolation, sorting). Verified end-to-end in a browser: a visitor subscribed from the Persian page (refused without consent, accepted with it), the subscriber appeared in the dashboard tagged Persian, and a post published in the dashboard appeared on the public blog.

## ADR-119 — Memory export as Markdown
**Status:** ACCEPTED (forensic audit, 2026-10-13). **Decision:** the memory export gains a fifth format, `md`, alongside json, jsonl, csv and zip, and the zip now carries `memory.md`.
**Why:** the historical requirements (§7, §22) call for a readable Markdown export; the implementation offered only machine formats, so this was a genuine gap rather than a documentation one.
**What it is:** a readable *representation*, not the canonical store. The header names PostgreSQL as the store, states the scope and record counts, and carries the no-credential statement. Each working-memory record is rendered with its kind, job key, version, record id, creation time and any provenance, source or checksum, followed by its content as nested bullets (long or multi-line strings as fenced blocks). Memory profiles and agent handoffs follow in their own sections. Empty sections say so rather than vanishing.
**Binary assets:** never converted. A record that points at a binary asset keeps its reference, checksum and provenance so the original can still be found; the JSON, JSONL and ZIP formats remain the lossless copy.
**Access:** unchanged — owner/admin only, tenant-scoped, audit-logged, `Cache-Control: no-store`, attachment disposition.
**Tests:** 2 added (readability and provenance with the zip carrying the same Markdown; admin-only and tenant isolation), and the existing zip file-list assertion updated. `/api/v1/memory/export.md`; dashboard: Memory Center gains a Markdown download button.

## ADR-120 — Routing policies are editable by an admin
**Status:** ACCEPTED (2026-10-13). **Problem:** the schema carried everything needed to choose providers and order them (`ai_routing_policies`, `ai_routing_steps.position`, six modes incl. `priority_pool`), but the API offered only `POST` and `GET`. The dashboard said so on screen: "Create one through the API". By the project's own standard this was BACKEND-ONLY — a capability the user could not reach.
**Decision:** complete the contract. Added `GET`, `PATCH` and `DELETE` for a policy, and `POST`, `PATCH`, `DELETE` and `/move` for its steps.
**Rules that hold on every edit:** a policy can never be edited into a shape it could not have been created in — `_validate_policy` is the single source for the mode rules and runs on create, on mode change, on adding, editing and removing a step. So `manual_single` keeps exactly one step, `stage_manual` keeps a stage on every step, and the last step cannot be removed.
**Ordering:** `position` stays 0..n-1 with no gaps. `/move` shifts everything between the step and its destination. Renumbering runs in two passes with a flush between them, because `(policy_id, position)` is unique and both passes would otherwise be sent as one statement — found by a test, not by reading.
**Deletion:** a policy that has run jobs is refused with 409 rather than cascading, so job history stays readable. An unused policy deletes with its steps.
**Dashboard:** the Routing tab now has a create form and, per policy, rename, mode change, ceiling removal, delete, and per step move up / move down / remove plus an add-step form. Each step shows its account's health.
**Tests:** 6 added (editing, ordering and priority, retargeting a step, mode rules on edit, deletion safety, admin-only and tenant isolation). Verified in a browser against a live backend: created a policy, added a second step, moved it up, and confirmed the stored order.

## ADR-121 — A second provider: the OpenAI adapter
**Status:** ACCEPTED (2026-10-13). **Problem:** the adapter boundary, the registry, provider fallback and six routing modes all existed, but only one adapter did. `priority_pool` and `PROVIDER_FALLBACK` had nowhere to fall back to, which the audit named the project's second-highest risk.
**Decision:** `app/integrations/llm/openai.py`, behind the same `LLMAdapter` contract as Anthropic and registered the same way. The shared rules are unchanged: the non-bypass permit check first, the response-size cap, honest token reporting, and a `safe_message` that never carries the prompt, the response body or a credential.
**What differs is only the provider's own API:** `/v1/chat/completions` rather than `/v1/messages`; `Authorization: Bearer` rather than `x-api-key` plus a version header; `max_completion_tokens`; the answer at `choices[0].message.content` (a string or typed parts); `usage.prompt_tokens` / `usage.completion_tokens`; `finish_reason` `length` → `TOKEN_LIMIT` and `content_filter` → `SAFETY_BLOCKED`; the request id from `x-request-id`.
**Cost:** never reported. The chat endpoint does not say what it billed, so `actual_cost` stays None and the wallet's own estimate stands rather than an invented figure.
**429:** OpenAI uses it both for rate limiting and for an exhausted quota, and the body is never read, so it is treated as retryable — which the ledger's reservation already protects against.
**Settings:** `OPENAI_API_KEY`, `OPENAI_API_BASE_URL`.
**Tests:** 26 for the adapter (request shape, answer and token reading, typed content parts, normalised finish reasons, malformed answers, the full HTTP vocabulary, the prompt and credential never leaking, timeouts, oversized responses, the connection test) and 4 for two-provider behaviour: Anthropic failing over to OpenAI with each attempt its own execution chained by `previous_execution_id` and marked `PROVIDER_FALLBACK`; an unconfigured provider skipped with no execution recorded; a rejected credential on the first provider still reaching the second; and every provider failing reported as failure, never disguised.
**Status of the provider itself:** MOCK_VERIFIED. Both adapters run for real — real httpx, real request building, real response parsing, real error mapping — against a mock transport. **No test here is evidence of a real OpenAI call; that needs a real credential.**

## ADR-122 — Canonical Document Representation, provider abstraction, extraction history
**Status:** ACCEPTED (owner prompt v4.0 §4–§13, §25–§26, §38, §55–§57, 2026-10-14). **Problem:** the "canonical" artifact of a document was Markdown assembled from MarkItDown output plus pdfplumber tables plus OCR blocks (`ingestion/pipeline.py`). It held no reading order, no geometry, no per-dimension confidence, no equations, and a reprocess deleted the previous extraction's tables and images. Evidence could point at a chunk but never at a page. **Decision:** (1) `app/ingestion/cdr.py` defines the CDR — pages and typed elements (heading, paragraph, list item, table with cells and spans, figure, caption, display/inline equation, chemical, reference, footnote, header, footer, page number, link, code, transcript segment, unclassified) with reading order, `[x0,y0,x1,y1]` geometry, original and NFC-normalised text (never NFKC, which corrupts formulae), script/direction/conservative language, per-element extraction confidence and method. (2) `DocumentExtractionProvider` (`ingestion/providers/`) with four implementations: `local_pdf` (pdfplumber words → lines → blocks → margin extraction + recursive XY-cut reading order → classification; tesseract TSV with word geometry for scanned pages), `markitdown` (non-paginated formats parsed once into elements), `image_ocr`, and `mathpix` (documented v3/pdf endpoints; `lines.json` parsed defensively because its field schema is not in the public reference — HYPOTHESIS, mock-verified only). Vision is a declared contract that reports itself unavailable: both LLM adapters are text-only. (3) `orchestrator.run` — primary → validate → confidence → next provider → human-review flag; every candidate kept, candidates never merged, disagreement flagged. (4) Six confidence figures on `document_conversions` (`NULL` = not measured; overall = weakest measured). (5) Persistence: `document_elements` hang off the conversion, not the document, so every extraction keeps its own reading; `is_current` + `superseded_at` (one current per document, partial unique index); tables/assets gain `conversion_id` and are no longer deleted on reprocess; a reprocess is created non-current and only replaces the current extraction if it succeeds. (6) `Document.content` is now rendered FROM the CDR (`render.py`: Markdown, MMD, HTML with spans and `data-bbox`, LaTeX, JSON); the legacy MarkItDown text stands in only when no provider succeeds, and the extraction is then flagged. DOCX/PDF output is refused with 501 — no writer is a dependency, and a fake file is worse than a refusal. (7) Evidence gains `document_element_id` + a snapshot of page and box (§9); "claims from page N" is a join. (8) `benchmark.py` measures CER/WER, information loss, reading-order tau, heading F1, table cells, equation recall, caption association, provenance completeness and confidence calibration — per document, never as a ranking. **Rejected:** PyMuPDF (AGPL, already rejected by ADR-066); Markdown as the stored truth; merging provider outputs. **Migration:** 0037 (additive; existing conversions back-filled from their known status only; confidence left NULL). **Tests:** `test_v4_document_intelligence.py` (37).

## ADR-123 — Silent truncation and false completion removed from AI jobs
**Status:** ACCEPTED (v4.0 §13, §66). **Problem:** `ai_job_service.run_job` stored every model answer as `result[:4000]`, discarding the tail of every long answer without a trace; and a job whose items failed ended `completed / COMPLETED`. **Decision:** the whole answer is stored with its length; a job with failed items ends `completed_with_failures / ITEMS_FAILED` (new value in the `ai_jobs.status` CHECK). The agent layer already treats anything but `completed` as blocked, which is the honest outcome. **Also fixed (§13):** the legacy extractor's 200-page cap now says which pages were not scanned. **Migration:** 0037. **Tests:** 2 in `test_v4_context_synthesis.py`.

## ADR-124 — Context assembly, three budgets, coverage-preserving synthesis
**Status:** ACCEPTED (v4.0 §14–§23, §39–§41, §58–§60). **Decision:** `app/ai/context_assembly.py` (pure) turns the claims in scope — with all supporting and contradicting evidence, conflicts, source locations and access state — into units; scores them on ten reported dimensions (semantic overlap, section, evidence, quality, contradiction, rarity, specificity, negative finding, provenance, language) where rarity RAISES importance; packs every unit (conflicting units together; an oversized unit split by evidence, never shortened); plans against three separate budgets (context per call, calls, money — an unknown price under a money limit blocks rather than guesses). A blocked plan starts nothing; `allow_partial` processes the most important packs and leaves the rest PENDING, never omitted. Execution is ordinary `ai_jobs` (one per stage: map, then reduce levels) — no second job system. **Audit path (§21):** a deterministic comparator over `[[U<n>]]` markers and a `---LEDGER---` the model must write decides each unit's fate (represented, merged — only into a unit that is itself cited, transformed, unresolved, contradictory, omitted with reason, pending) independently of the model's own claim. Information-loss rate = omitted / units sent. The database refuses an omitted unit without a reason, a merge without a target, and a `completed` run with any omitted or pending unit. **Publication:** an audited synthesis becomes publication sentences whose sources come through each cited unit's claim → evidence → source chain; the existing Vancouver resolver numbers them; an uncited sentence is marked evidence-unavailable, never numbered. `publication_service.add_sentence` gains `additional_claim_ids` (same support rule). **Migration:** 0038. **Tests:** `test_v4_context_synthesis.py` (19).

## ADR-125 — Persistent command workspace
**Status:** ACCEPTED (v4.0 §46–§54, §64). **Decision:** `workspace_commands` + `workspace_command_versions`. Drafts autosave server-side with a revision counter (a stale tab gets 409 with the newer text, never a silent overwrite); localStorage holds only unsaved keystrokes. Running a version freezes it — a database trigger refuses any change to what was asked once `executed_at` is set; editing creates the next version; restore and regenerate create new versions; compare diffs text and scope; delete requires `permanent=true` (archive otherwise). A rule-based parser (EN + FA) only PROPOSES an intent; `/plan` resolves intent + explicit scope (+ the synthesis plan for model work) and `/run` refuses an incomplete scope with 422. Deterministic intents (claims on a page, unsupported statements, contradictions, section applicability, evidence for a claim, coverage audit) answer from the knowledge base via `knowledge_query_service` at no cost; `reprocess_document` queues the existing ingestion job; model intents run ADR-124 synthesis. State, result, cost (unknown prices counted, never zeroed) and errors live on the version; a provider stop leaves the command `blocked` and `/resume` continues from the checkpoint without redoing finished items; `/workspace/commands/resumable` drives the "Continue previous task?" offer. Commands are private to their author: another user's command is a 404 even inside the organisation. **Dashboard:** the `screen-chat` placeholder (labelled "no backend") becomes the workspace inside the existing shell; dashboard rules 33/33. **Migration:** 0038. **Tests:** `test_v4_workspace.py` (24).

## ADR-128 — Authenticated knowledge chat
**Status:** ACCEPTED (master prompt §13–§14, 2026-10-19). **Problem:** nothing in the project stored a conversation. `customer_context` explicitly refuses to keep conversation content, and the dashboard's `screen-chat` is the command workspace (ADR-125), which is durable versioned intent — not a thread of questions. The requirement is a chat on the public website, behind the same account as the dashboard, that answers from the knowledge base, says when it cannot, and asks before researching.
**Decision:** `chat_settings` (one row per organisation) + `conversations` → `conversation_messages` → `conversation_citations` / `conversation_feedback`, plus `conversation_research_requests`. `app/services/chat_service.py` is the pipeline; `app/api/v1/chat.py` is the contract.
**No new AI machinery.** `ai_executions` is LOCKED and its parent arc needs a typed column per domain, and the project's own rule (v4 §69) is that AI work goes through `ai_jobs`. So one question becomes one `ai_job` with one item — the shape `synthesis_service` already uses — inheriting routing, the pre-spend cost gate, provider/account fallback, health recording, prompt-safety output checking and checkpointing. No third job system, no change to a locked table.
**Retrieval reuses the knowledge layer:** `synthesis_service.collect_units` (claims with ALL supporting and contradicting evidence, conflicts, source locations, access state, every source-derived field already cleaned and prompt-safety scored), then `context_assembly` scoring and packing. Terms are content words in any script (`[^\W_]` excludes punctuation, so Persian "گوید؟" yields "گوید"); stopwords are dropped because they match every claim and would turn the filter into no filter.
**One call per question, and it says so.** A synthesis may spend many calls reducing many packs; a chat answers in one. The first pack is consulted and the remainder is reported as `units_not_consulted` with a count — `PARTIAL_ANSWER`, never a silent cut. A corpus too large for one reply is answered by a narrower question or a workspace synthesis.
**The answer state is not a score.** Eight states (§13.5) decided by deterministic code AFTER the model has spoken, never by the model about itself: nothing retrieved → `UNKNOWN` (research disabled) or `NEEDS_WEB_RESEARCH`; no topic in scope → `NEEDS_USER_SOURCE`; contested evidence behind a citation → `CONFLICTED`; an answer citing nothing → `PARTIAL_ANSWER` flagged `ungrounded`; no policy, no capacity, an unaffordable or unpriced model, or a provider failure → `PROVIDER_UNAVAILABLE` with the reason in `limitation`. A CHECK constraint refuses an assistant turn with no state and a user turn with one, so the rule holds in the schema and not only in the service.
**Grounding is validated, not trusted.** `[[U<n>]]` markers the model wrote are intersected with the units actually supplied; an invented marker is removed and counted (`invented_markers`) because there is no claim behind it. Surviving markers become `[1]`, `[2]` … by first appearance — the same first-appearance rule the Vancouver resolver uses, but local to one message and never a publication reference number. Each cited unit becomes one citation row carrying its primary evidence (verified, then direct over indirect, then strength) in typed columns and **every** evidence row for that claim in `location.evidence`: consolidating a citation must not discard independent evidence (§3.4).
**Authorisation is server-side and per user.** Every route requires a session — `get_current_user` rejects a missing or malformed token with 401 before any handler body runs, and there is no anonymous or fail-open branch. A conversation belongs to its author: another user's id is a 404 even inside the same organisation, and a message is resolved through its owning conversation so an id cannot be probed. The topic allow-list, the research mode, the routing policy, the token and cost ceilings, retention and the daily limit all live in `chat_settings` and are re-read on every question, so revoking a topic takes effect on the next turn. Settings are owner/admin only, and every reference is checked against the caller's own organisation.
**Research needs a named authorisation (§13.6).** *(Steps 5–9 — actually carrying the request out — were added later; see ADR-130.)* A gap opens a `conversation_research_requests` row: `pending_approval` under `ask_every_time`, or `approved` with `authorization_basis = preauthorized` under the administrator's standing grant — recorded either way, never implicit. The gap is also written into the knowledge layer as a `RETRIEVAL_GAP`, so the chat feeds the research loop instead of keeping its own list. Approving twice is 409; cancelling is always available.
**Chat memory is not knowledge.** Conversations are a record of what happened: a failed answer is kept, a retry is a new turn, and nothing here writes a claim. Promotion into canonical knowledge happens only through the research workflow, with its own provenance.
**Dashboard:** a 52nd screen, `screen-chat-settings`, in the existing shell — the only surface for §14. Off by default, so a new tenant has no chat until someone enables it deliberately. The dashboard exists in two copies that had already drifted apart (the bundled preview and `visual-harness/index.html`, which has a theme picker and four fewer script blocks); the screen was added to the bundle first and later ported verbatim to the harness — option, sidebar link, section and driving script — at the same neighbours, so both copies now say the same thing about the chat. The rest of the drift between them is untouched.
**Done in a later pass:** the website chat page, once the owner chose the website's session mechanism — see ADR-129.
**Migration:** 0040 (additive and reversible; no existing table or column changed). **Tests:** `test_chat.py` (44), including every route refusing an unauthenticated request, per-user isolation inside one tenant, each answer state, marker rewriting, invented-marker removal, overflow reporting, evidence preservation in citations, and the two CHECK constraints.

## ADR-129 — The website's own session: refresh token in an HttpOnly cookie, access token in memory
**Status:** ACCEPTED (master prompt §13, owner decision 2026-10-20). **Problem:** ADR-128 left the website chat page unbuilt for one reason: the public website had no session of its own. Every "Log in" link on all 13 pages navigated to `/dashboard/#screen-login`, and a grep for `Authorization`, `Bearer`, `access_token`, `document.cookie`, `credentials:` or `sessionStorage` across the whole website returned nothing. A chat that must refuse anonymous visitors cannot be built on an authentication mechanism that does not exist, and inventing one silently was explicitly out of bounds.
**Decision (the owner's, between three candidates):** the access token is held in a JavaScript closure variable and nowhere else, and the durable half of the session is a refresh token in an HttpOnly cookie — the pattern OAuth 2.1 and the current browser-app guidance recommend over a bearer token in `sessionStorage`. A closure variable cannot be read back by a later script and dies with the tab; an HttpOnly cookie cannot be read by page script at all. Neither half is a long-lived credential sitting in readable storage.
**Three new routes, no existing one touched.** `POST /auth/session` verifies the same emailed six-digit code `/auth/login-code/verify` does — same service, same lockout, same deliberately indistinguishable failures — and additionally sets the cookie. `POST /auth/session/refresh` rotates it and returns the next access token. `DELETE /auth/session` signs out. `/login`, `/login-code/verify`, `/signup/verify` and `/register-organization` are unchanged and still return a bearer token to API and dashboard clients that never wanted a cookie; a test asserts they set no cookie.
**Rotation with reuse detection.** `auth_sessions` stores an HMAC of the current secret keyed with `SECRET_KEY` — the same treatment `login_codes` gives a code — so reading the table yields no usable cookie. Every refresh mints a new secret. If a secret that has already been rotated away is presented, two parties hold the cookie and there is no way to tell which is the legitimate one, so the session is revoked outright (`reuse_detected`, recorded in the audit log) rather than guessed about.
**With one exception, because the obvious implementation is wrong.** Two tabs of the same site refresh at the same moment and both send the cookie the browser had; strict reuse detection signs the person out for opening a second tab. So the secret replaced by the *most recent* rotation stays acceptable for 30 seconds (`previous_token_hash`, `previous_until`) and is rotated normally — both tabs share one cookie jar, so the newest cookie is the one that survives either way. Anything older than that one secret, or presented after the window, still revokes the session. The window is what separates a concurrent refresh from a replay, and it applies to sign-out too, so "sign out" from the second tab really does sign the person out. `expires_at` is absolute and rotation never extends it: a stolen cookie cannot be refreshed forever. A refresh also re-checks that the user and organisation are still active, because a current cookie proves nothing about the account behind it.
**The cookie is scoped, not ambient.** `Path=/api/v1/auth/session`, `HttpOnly`, `SameSite` configurable (`strict` by default, correct when site and API share a registrable domain), and `Secure` everywhere except development, which is served over plain http and would otherwise never receive it. It is therefore never attached to a chat or knowledge request: those carry the bearer token, so the chat API has no cookie-authenticated surface and needs no CSRF token. A test asserts that the cookie alone authenticates nothing. `SameSite=none` without `Secure` is refused at startup rather than producing a cookie no browser will store.
**CORS stays shut by default.** `CORS_ALLOW_CREDENTIALS` is a new setting defaulting to `false`, so an existing deployment behaves exactly as before; it is turned on only when the website is served from a different origin than the API. Allowed origins remain explicit and never `*`.
**Shorter-lived than the API token.** `BROWSER_ACCESS_TOKEN_EXPIRE_MINUTES = 15` against the API's 60: this token is replaceable at any moment by a cookie the page cannot read, so there is no reason to make it last an hour. The page renews a minute early, and a 401 mid-session triggers one silent renewal and one retry before the user is returned to the sign-in prompt.
**The gate is structural, not cosmetic.** On `chat.html` the chat interface lives in a `<template>` and is cloned into the document only after a session is proved. While signed out there is no thread, no composer and no chat request of any kind — not a hidden UI, but an absent one. Answers are written with `textContent`, never parsed as HTML.
**A revoked session always says why.** `revoked_reason` is constrained in the schema to `logout`, `reuse_detected` or `expired`, and a revoked row with no reason is refused — written NULL-safely, because `NULL IN (...)` is NULL and a CHECK that evaluates to NULL passes. Two tests hold that, and they are the reason the first version of the constraint did not ship.
**Migration:** 0041 (additive and reversible; no existing table or column changed). **Tests:** `test_auth_session.py` (25) — cookie attributes, hash-only storage, rotation, reuse detection killing the session for both holders, two tabs refreshing together NOT being treated as a replay, a secret older than the window or older than one rotation still revoking, absolute lifetime not extended, malformed and forged cookies, idempotent sign-out, sign-out with a wrong secret revoking nothing, the cookie failing to authenticate `/auth/me` or any chat route, and the pre-existing bearer routes still setting no cookie.
**Verified in a browser, not only in tests.** The page was driven in Chromium against a live Cloud Core: signed out it reaches the sign-in prompt with no `.chat-app` in the document and no call to any chat endpoint; a real code is emailed, read and accepted; the cookie is present and HttpOnly while `document.cookie` cannot see it; nothing resembling a token reaches local or session storage; and only then are `/chat/config` and `/chat/conversations` called. That run is also what caught the sign-in panel staying on screen after sign-in — the site's `.card { display: flex }` outranks the UA rule for `[hidden]`, which no amount of markup checking would have revealed.

## ADR-130 — Carrying out an approved chat research request
**Status:** ACCEPTED (master prompt §13.6 steps 5–9, 2026-10-20). **Problem:** ADR-128 implemented steps 1–4 and 10 — the chat detects a gap, proposes a scope, records a decision with a named authorisation basis, writes a `RETRIEVAL_GAP` into the knowledge layer, and lets the user approve, reject or cancel. Nothing then acted on the approval. A request stayed `approved` for ever, `research_project_id`, `reanswer_message_id` and `sources_added` were columns nothing ever filled, and the user was told the request was "waiting to be carried out" by a system in which nothing would ever carry it out.
**Decision:** `app/services/chat_research_service.py` performs steps 5–9, and `chat.run_research_request` is the worker that calls it. Approval queues it; a pre-authorised request starts at the moment it is opened, because the administrator's standing decision *is* the authorisation and waiting for a second one would ignore it.
**It is not a second research engine.** The project already has one — `research_projects` → `research_tasks`, executed by whatever `ResearchProvider` is registered — and §18 says there is exactly one. So an approved request creates a real project and a real task through `research_project_service` and `research_task_service` and runs them through `execute_research_task`. The task lifecycle is honoured as written (`pending → queued → running`), which is also what stops two callers racing the same task into execution.
**Mode is not decorative.** The project is `gap_driven` only when a `knowledge_gap` was actually recorded; a question with no topic pinned produced no gap row, so its mode is `user_driven`. The schema refuses `gap_driven` without a gap, and claiming one anyway would make the research log lie about why the investigation exists.
**No provider is the normal case, and it is reported.** This repository registers `NotConfiguredResearchProvider`, which §18 requires to report `NOT_CONFIGURED` rather than fabricate a plausible result. A request whose task does not reach `COMPLETED` therefore ends `failed`, carrying the research layer's own reason, and the schema refuses a `failed` row with no reason. The outcome a user sees is "no research could be performed, and here is why" — never a `completed` request with nothing behind it.
**Sources are counted from the research layer, not from the provider's summary.** `sources_added` is the number of distinct `research_task_references` of type `source` the task actually produced. A provider that claims success in prose but registers nothing adds nothing.
**Re-answering is conditional (step 8).** With `sources_added = 0` the request completes and stops: re-answering an unchanged knowledge base would spend a model call to produce the same answer and present it as progress. Only when sources were really added is the original question asked again through `chat_service.ask`, and the new turn is linked as `reanswer_message_id`. If research succeeded but the re-answer failed, both facts are recorded — the request fails with an error that states the research succeeded and says how many sources it added.
**Approval survives a broker outage.** The decision is committed before the work is queued; a `.delay` that raises is logged and the request stays `approved`, runnable later. Queueing is not the decision.
**Wording changed to match.** The pre-authorised limitation no longer says the request "is waiting to be carried out" — since this change that would be the false statement. It says a request was opened and started, and still never claims research has produced anything.
**Migration:** none — ADR-128's schema already carried every column this needed. **Tests:** `test_chat_research.py` (17) — no provider failing honestly, provider failure and inaccessible results reported, every failure carrying a reason, nothing-found completing without a model call, sources counted from reference rows, the work going through a real project and task, mode matching whether a gap exists, only `approved` requests running, a finished request not running twice, another tenant's request not running, approval reaching the worker, a dead broker not undoing the approval, and rejection starting nothing.
**Still not done:** no real `ResearchProvider` exists. Implementing one (web search, PubMed/DOI, a licensed corpus) is the remaining work, and it is a single interface with one method — `app/integrations/research/base.py` — registered in `get_research_provider()`. Until then every chat research request will honestly fail, which is the behaviour §18 asks for and not a defect in this wiring.

## ADR-131 — Durable AI-job execution: worker lease, recovery sweep, capacity deferral
**Status:** ACCEPTED (master prompt v5 §9, §10, §74, Workflows B and D, 2026-10-20). **Problem (FACT, read in code):** `ai_job_service.run_job` set a job `running` and held nothing that could tell a live worker from a dead one. If the worker died the job stayed `running` for ever: `ai_center.run_job` skips every job not in `queued/paused/blocked`, and no sweeper touched `ai_jobs` (the Phase 17 reclaimer only marks the in-flight `ai_executions` row `abandoned`). Separately, a job whose every account was rate-limited or out of quota became `blocked` and nothing ever resumed it, although `ai_provider_accounts.unavailable_until` already said when the limit would lift.
**Decision:** three columns on `ai_jobs` (migration `0042`, additive, reversible) and one periodic task.
* **Lease** (`lease_owner`, `lease_expires_at`). `run_job` claims it with one atomic `UPDATE … WHERE no live lease … RETURNING`, renews it before every item and releases it on every exit. A second worker on the same job gets `LEASED_BY_ANOTHER_WORKER` and processes nothing. `AI_JOB_LEASE_SECONDS` (900) must exceed one provider call.
* **Resume time** (`resume_after`). Set only when routing found no resource and the stop is `PROVIDER_UNAVAILABLE`: the earliest `unavailable_until` among the policy's enabled, permitted accounts whose health only passes with time (`rate_limited`, `quota_exhausted`, `unavailable`, `timeout`, `degraded`). Auth failure, a spend limit, a missing adapter and a background-policy refusal get no resume time: time does not fix them, a person does. A DB CHECK allows `resume_after` only on a `blocked` row.
* **`ai_center.recover_jobs`** (Celery beat, every `AI_JOB_RECOVERY_INTERVAL_SECONDS`). Running + expired lease → `queued`, `retry_count` + 1; blocked + `resume_after` passed → `queued`, `auto_resume_count` + 1. Rows are locked `FOR UPDATE SKIP LOCKED`, so two sweepers cannot double-queue. Every transition is written as a `job_state` memory row with its reason.
**Bounded, never infinite (§74).** After `AI_JOB_MAX_AUTO_RESUMES` (24) automatic resumes the job stays `blocked` with `AUTO_RESUME_LIMIT`. A manual resume from the dashboard resets the allowance. An exception inside the worker (a bug, not a provider limit) ends the job `blocked` / `WORKER_ERROR` with the lease released and no resume time, so a defect is never retried by itself.
**Status stays `blocked`, not a new `deferred` state.** Synthesis, workspace, agent execution and chat all branch on `blocked`; a new state would have changed four callers and their tests for no gain. "Blocked with a resume time" carries the same meaning and the API reports `resume_after`, `auto_resume_count` and `worker_lease_active`.
**Semantics:** at-least-once. An item whose provider call was in flight when the worker died is run again (its `ai_executions` row is already `abandoned` by the Phase 17 reclaimer, and the new execution links to it). Finished items are never redone, because `ai_job_items.status` is the canonical progress. This is not exactly-once and is not claimed as such.
**Not done here:** the adapters still do not read the provider's `Retry-After` header, so `unavailable_until` comes from the fixed avoid windows in `HEALTH_FOR_STOP` (60 s rate limit, 3600 s quota). That is the next increment.
**Tests:** `test_v5_job_durability.py`.

## ADR-132 — The provider's Retry-After decides how long an account rests
**Status:** ACCEPTED (master prompt v5 §9 "retrying after Retry-After", 2026-10-20). Closes the gap left open in ADR-131.
**Problem (FACT):** neither LLM adapter read the `Retry-After` header. `record_health` already accepted `retry_after`, but no caller ever passed one from an execution, so a rate-limited account rested for a fixed 60 s and an exhausted quota for 3600 s, whatever the provider had said. Too short wastes calls against a provider that already said no; too long leaves capacity idle.
**Decision:** `parse_retry_after` in `integrations/llm/base.py` reads both RFC 9110 forms (delta-seconds and HTTP-date). Both adapters attach the value to the `AdapterError` they raise for a non-200 answer (`retry_after_seconds`), and `ai_job_service` passes it to `record_health`, where it already outranks the fixed window. Through ADR-131 it becomes the job's `resume_after`, and it is recorded on the `ai_health_events` row.
**Conservative bounds:** a value that is unreadable, negative, in the past or longer than a day is ignored (`None`), so the fixed window applies. A malformed or hostile header cannot park work indefinitely. `0` becomes 1 s.
**Unchanged:** no response body is read, so the rule that provider bodies (which may echo the prompt) are never surfaced still holds. The header carries no secret.
**Live verification:** none. No provider key exists in this environment, so this is `IMPLEMENTED_BUT_LIVE_PROVIDER_NOT_VERIFIED`. Whether a given provider actually sends `Retry-After` on 429/402 is **UNKNOWN** here; when it does not, behaviour is exactly as before.
**Tests:** `test_v5_job_durability.py::test_retry_after_parsing`, `::test_provider_retry_after_sets_the_resume_time`.

## ADR-133 — Working-memory lifecycle; state records supersede, findings accumulate
**Status:** ACCEPTED (master prompt v5 §11–14, §55, §87, 2026-10-20). **Problem (FACT):** `ai_working_memory.status` was free text, written `active` and never changed. Every version of a job's `job_state` or `processing_checkpoint` stayed "active" side by side, so nothing distinguished the current state from history. Model output was recorded with the same status as application state, and there was no rule for moving a record on.
**Decision (migration `0043`, reversible):**
* `status` is constrained to `created → validated → active → superseded → archived`. The allowed moves are `MEMORY_TRANSITIONS`; `archived` is terminal. `ai_memory_service.transition` is the only way to move a record, and every move is appended to `provenance.transitions` with actor and reason.
* **State-like kinds** (`job_state`, `current_synthesis`, `processing_checkpoint`, `ai_handoff`, `next_action`): writing a new version marks the previous current one `superseded` and links it with `superseded_by_id`. Nothing is deleted. `superseded` cannot be set by hand.
* **Accumulating kinds** (`intermediate_finding`, `open_question`, `conflict_context`, `ai_summary`) are never superseded by a newer write.
* **Model output starts `created`** (`created_by` = `execution:…`). Being written does not make it validated; a validator or a person moves it on (`POST /ai-center/memory/{id}/status`, editor role, tenant-scoped; `superseded` is refused there).
* **Memory never becomes a claim.** No transition creates or changes a `claims` row (test-asserted). Promotion into knowledge goes through the evidence/claim review workflow and, from ADR-134, the reconciler.
* `agent_memory_bindings.access_level` gains a CHECK (`read`/`write`/`admin`). The READ/WRITE/ADMIN enforcement itself already existed (`agent_execution_service.require_memory`, §55 FACT). Unknown values are lowered to `read` on upgrade (least privilege).
**Existing data:** older versions of state-like kinds are marked `superseded` on upgrade, which is what they already were. Downgrade resets every status to `active`, the only value the old column held.
**Also corrected in ADR-131:** migration `0042` dropped its `resume_after only when blocked` CHECK before release. Synthesis, the workspace and an existing test re-queue a blocked job by status alone, and the CHECK broke them (`test_v4_context_synthesis` caught it). The rule is kept in code instead: the sweep acts only on `blocked`, `run_job` clears the field, and the API shows `resume_after` only on a blocked job. Constraint names in `0042`/`0043` use `op.f()` so the naming convention does not double the prefix.
**Tests:** `test_v5_memory_lifecycle.py` (7).

## ADR-134 — Knowledge Transfer Package v1, deterministic Validator and Reconciler
**Status:** ACCEPTED (master prompt v5 §21–25, §35, §51–53, Workflow A; implemented 2026-10-20, recorded 2026-10-21). **Problem (FACT):** worker output was stored as free text in `intermediate_finding` memory and nothing validated it or carried it into `claims` / `claim_evidence` / `evidence_conflicts`. `current_synthesis` was a mechanical merge. Workflow A could not run.
**Decision (migration `0044`, additive, reversible):**
* **Package schema** (`app/schemas/knowledge_transfer.py`): claims, each with verbatim-quoted evidence (`source_id`, optional `document_id` / `document_element_id` / page, `relation` supports|contradicts, `directness`, `route`, `about`), plus open questions, gaps, assumptions, rejected interpretations, finding kind (qualitative, numerical, negative, unique, rare) and `processing_status`. Unknown keys are refused.
* **Validator** (`knowledge_reconciliation_service`, no model involved). A truncated (`TOKEN_LIMIT`) or unparseable package is `invalid` and nothing is used. Per claim: the subject/object entity must exist in the topic, there must be evidence, the source/document/element chain must belong to the tenant, and the **quote must be found in text the system actually holds** for that source (full text, partial text or abstract). A quote that cannot be found is `CITATION_MISMATCH`, and a source with no stored text is `SOURCE_TEXT_UNAVAILABLE`. Evidence about another substance (e.g. mannitol for Toranjebin), or an indirect route, cannot be filed as direct (§35). Rejections are per item and recorded, never silent.
* **Reconciler:** same subject + predicate + object is a **duplicate**, so the new evidence is linked to the existing claim (one canonical claim + N evidence links, §23). Same subject + predicate with a different object is a **variant**, kept as its own draft claim and pointed at the claim(s) it differs from; the system does not decide whether it is a refinement or a contradiction. Anything else is a **new** claim. `contradicts` evidence goes through `conflict_service.detect` (ADR-110), so no side is chosen.
* **Workers never write approved knowledge (§51):** everything created is `DRAFT`, `source_generated`, `human_reviewed = false`, evidence strength `VERY_LOW` / claim `UNVERIFIED` until review.
* **Idempotent:** a package is unique by hash per tenant (at-least-once delivery is safe); evidence is deduplicated on (source, document, quote).
* **Wiring:** `ai_jobs.output_contract = 'ktp_v1'` (needs `knowledge_object_id`). Each item's output goes through `ingest`. An invalid package fails the item (`OUTPUT_INVALID`), while its raw text stays in memory so it can be retried. An accepted package moves the item's finding memory `created → validated` (ADR-133). Packages can also be submitted and listed at `/api/v1/knowledge-transfer/packages` (editor role to submit, tenant-scoped reads).
**Dashboard (2026-10-21):** AI Center → Jobs & memory lists packages (server-side paging, status filter) with per-claim verdicts, outcomes, open questions, gaps and recorded conflicts; not yet verified in a browser. **Not done:** Quote matching is exact after normalisation (NFC, case-fold, whitespace), so a model that paraphrases gets its evidence rejected; that is deliberate. There is no fuzzy match, and no OCR-noise tolerance either.
**Tests:** `test_v5_knowledge_reconstruction.py` (7): two workers into one evidence-linked state, variant kept, explicit rejections, malformed/truncated output, idempotent resubmission, tenant isolation, topic ownership.

## ADR-135 — Task DAG: dependencies between AI-job items
**Status:** ACCEPTED (master prompt v5 §10 "task DAG, dependency tracking", §50, 2026-10-21). **Problem (FACT):** `ai_job_items` was a flat list run in `position` order. A planner could not say "pharmacology after chemistry", so dependent work either ran too early or had to be split across jobs by hand.
**Decision (migration `0045`, additive, reversible):** `ai_job_items.depends_on text[]`, the item keys of the same job that must be `completed` first. Existing items get `{}` and run exactly as before.
* **Checked at creation** (`ai_job_service.validate_dependencies`): unique keys, no self-dependency, no unknown key, no cycle (Kahn). The API answers 422 and nothing is stored. Items are never added to a job afterwards, so the graph stays valid.
* **Scheduling** (`_next_item`): the lowest-position pending item whose dependencies have all completed. A pending item with a failed dependency can never run, so it is failed with `DEPENDENCY_FAILED: <keys>`, transitively. Independent items still run, and the job ends `completed_with_failures` instead of waiting for ever. Because the graph is acyclic, a pending item is always either runnable or failed.
* **Observable:** the handoff/checkpoint package carries `waiting_on` (pending item → dependencies not yet completed).
**Deliberately not done:** a dependency orders work; it does not pipe one item's output into the next item's prompt. Per §22, a dependent worker should read the reconciled canonical state (ADR-134) through context assembly, not its predecessor's prose. Execution is still one item at a time per job; parallel branches are not run concurrently.
**Tests:** `test_v5_task_dag.py` (9).

## ADR-136 — Provider capability limits on `ai_models`, enforced before each call
**Status:** ACCEPTED (master prompt v5 §7, §16, §17, Workflow C, 2026-10-21). **Problem (FACT):** `ai_models` held `context_window` and capability tags, but nothing read `context_window`. An item larger than the routed model's window was sent anyway, and the provider either rejected it (a wasted call) or the system had no way to know beforehand. There were no columns for max input/output, RPM/TPM, structured-output or tool support, and none for where a figure came from. Models could not be edited after registration.
**Decision (migration `0046`, additive, reversible; every column nullable = unknown):** `max_input_tokens`, `max_output_tokens`, `rpm_limit`, `tpm_limit`, `supports_structured_output`, `supports_tools`, `capability_source` (`official_docs` | `provider_api` | `operator` | `conservative_estimate`, DB CHECK), all positive by CHECK. Limits are per-tenant data, never hardcoded, because providers change them.
* **Enforced** (`ai_routing_service.request_fit`, called by `ai_job_service` for every item before the cost gate's call): a job reserving more output than `max_output_tokens` fails the item `OUTPUT_EXCEEDS_MODEL_LIMIT`. An input estimate (system + item prompt, `context_assembly.estimate_tokens`, which already over-estimates) above the room fails it `CONTEXT_OVERFLOW … split the item`. The room is `max_input_tokens` and `context_window − output reserve`, whichever is smaller; the whole window is never treated as input (§16). No provider call is made, nothing is truncated, and other items still run.
* **Unknown blocks nothing:** an unregistered model or a NULL limit leaves the provider as the authority, as before. This is the conservative choice for availability, not for cost. To be strict, register the model with its documented limits.
* **Correctable:** `PATCH /ai-center/models/{id}` (admin, tenant-scoped). Only the fields sent change (null resets one to unknown), and old and new values are audit-logged (`ai_model.limits_updated`).
**Not done:** `rpm_limit` / `tpm_limit` / the support flags are recorded, not enforced. Rate limiting still relies on the provider's 429 + `Retry-After` (ADR-132). An oversized item fails rather than being re-routed to a larger model on the same policy or split automatically; synthesis runs (ADR-124) already split by packing, but plain AI jobs do not. Live limits are `IMPLEMENTED_BUT_LIVE_PROVIDER_NOT_VERIFIED`. The dashboard model form does not show the new fields yet.
**Tests:** `test_v5_model_limits.py` (8).

## ADR-137 — Official client suite: one shared UI, one Tauri 2 shell, four platforms
**Status:** ACCEPTED (client-suite master prompt, 2026-10-31). **Problem (FACT):** AIOL had a Cloud Core chat API (ADR-128), a browser session (ADR-129), preferences, billing usage and a dashboard, but no native client and no client a phone could install. The website chat page named in ADR-129 is not in this repository. No Device Intelligence code existed.
**Options evaluated.** (1) Flutter for all four: strong mobile story, but a second UI stack beside a repository whose every UI is plain HTML/CSS/JS on `frontend/design-system`; the design tokens and icon registry would have to be re-implemented in Dart (a second design system, which START_HERE forbids). (2) Shared web UI + Tauri 2 for all four: reuses the canonical tokens and icon registry byte-for-byte, one Rust native layer with OS keychains on Windows/macOS/iOS and a Kotlin Keystore plugin on Android, small binaries, system WebView. (3) Tauri desktop + Capacitor mobile: two native layers to secure. (4) Electron: large, ships its own Chromium, no mobile.
**Decision:** (2). `clients/app` is a no-bundler ES-module UI (the repository's own convention) that runs unchanged in a browser for development and tests; `clients/src-tauri` is the shell. Linux is not a release target.
* **Server-authoritative.** Identity, permissions, conversation history, answer states, usage, limits and research authorisation are only displayed. Nothing is cached to disk; lists, threads and drafts live in memory and are dropped on sign-out and account switch.
* **Session.** New routes `/auth/native/session{,/refresh,/end}` open the SAME `auth_sessions` row ADR-129 uses, with the refresh secret in the body instead of a cookie. The client stores it in the OS vault (Rust command surface allows only that one name) and keeps the 15-minute access token in memory; refresh is single-flight because a second rotation of the same secret is treated as theft. Sign-out revokes on the server and never deletes conversations.
* **Chat idempotency.** `conversation_messages.client_request_id` (migration 0049, partial unique index). A lost reply re-sent with the same key returns the stored turn; a key still being answered is 409 `request_in_progress`. The UI shows pending / confirmed / failed / unknown, and only "confirmed" means the server has it.
* **No invented UI.** Help/Learn more/Privacy/Terms appear only when `CLIENT_*_URL` is set (`GET /clients/config`); Get apps lists only `CLIENT_RELEASES_JSON` entries; Upgrade says "not available" until `CLIENT_UPGRADE_URL` exists and is withheld on Android/iOS (`CLIENT_UPGRADE_PLATFORMS`) until a store-policy-reviewed purchase flow exists. There is no subscription-plan model, so Usage shows wallet credit, quotas and the chat daily limit and says plans are not offered. Streaming is not offered because the API does not stream; "Stop waiting" says the answer may still be saved.
* **Languages.** English and Persian (the values `/users/me/preferences` accepts). Arabic is not offered: no backend preference, no catalogue.
* **Errors.** The envelope gains an optional `error.reason` when a route raises `{code, message}`; existing string details are unchanged.
**Not done (debt rows CLIENT-*):** streaming, OIDC/PKCE (no IdP exists), updater, store billing, attestation, dashboard screen, narrowing CSP `connect-src` in release builds.
**Tests:** `cloud-core/tests/test_client_suite.py` (19), `clients/test/*.test.js` (30), `clients/e2e/run.mjs` (39 browser checks against a live Cloud Core), `clients/src-tauri` `cargo test`.

## ADR-138 — Device Intelligence: installation continuity by proof of possession, evidence only
**Status:** ACCEPTED (client-suite master prompt §15–§21, 2026-10-31). **Problem (FACT):** the prompt refers to a previously specified "Web Device Intelligence Engine"; no such code, table or document exists in this repository (searched: device, fingerprint, MachineGuid, installation key). There is no free-quota policy engine either.
**Decision:** a small, tenant-scoped registry built on cryptographic proof of possession, not fingerprinting.
* An installation generates an ES256 key (WebCrypto non-extractable in a browser; OS keychain on Windows/macOS/iOS; Android Keystore, hardware-backed where available). The server issues a single-use, 120-second nonce bound to (organization, user, purpose, credential); the client signs a domain-tagged input the server rebuilds from its own record. A failed signature consumes the challenge. Rows: `device_credentials`, `device_credential_links` (account ↔ installation; account switching links a second account), `device_challenges` (nonce hash only), `device_observations` (append-only, expiring).
* **Collected:** public key, client-claimed key storage, app version, OS family/version, and for each observation a keyed, versioned HMAC of the client IP and of its /24 or /48 prefix. **Not collected:** hardware serials, MachineGuid, IMEI, UDID, MAC, ANDROID_ID, browser fingerprint attributes. MachineGuid/GDID were rejected as unnecessary once a key proves continuity, and as spoofable/copyable.
* **Tenant isolation.** The same key in two tenants is two unrelated rows; cross-tenant correlation waits for a platform-admin model (debt).
* **Assessment, not enforcement.** `di-assess-v1` returns categories with reason codes and the evidence counts behind them: `DEVICE_CREDENTIAL_REVOKED`, `SAME_REGISTERED_INSTALLATION`, `CONFLICTING_EVIDENCE`, `SHARED_NETWORK_ONLY`, `INSUFFICIENT_EVIDENCE`. Never a score (ADR-024) and never "same person". Nothing enforces on it; a failed or disabled device check never blocks sign-in.
* **User control.** The client's Settings explain what is collected and let the user turn it off, which unlinks the installation on the server and deletes the local key. Admin detail reads are audit-logged; revocation is audited.
* **Privacy settings.** `DEVICE_OBSERVATION_RETENTION_DAYS` (90), `DEVICE_PSEUDONYM_KEY` + `_VERSION` (falls back to a key derived from `SECRET_KEY` with domain separation; set an explicit key in production so `SECRET_KEY` rotation does not silently change pseudonyms), `DEVICE_INTELLIGENCE_ENABLED`.
**Not done:** retention scheduler (the purge function exists and is tested), App Attest / Play Integrity, policy engine, dashboard screen, legal review of the disclosure text. **Tests:** `cloud-core/tests/test_device_intelligence.py` (30, labelled synthetic) — replay, expiry, wrong nonce, spoofed public key, signature moved between users, verify challenge bound to one credential, P-384 / garbage keys, platform switch, cross-tenant isolation, RBAC, account switching, unlink/revoke lifecycle, audit, shared-network and VPN-change false-positive cases, pseudonymisation, retention.
