# Current State — AI Operating Layer

> **SYNCHRONIZED 2026-09-29 (final completion pass, migrations 0001→0032).**

**Verdict:** `CONDITIONAL PASS` — every non-external requirement of the owner's 45-section prompt is
implemented, wired to the dashboard and covered by an executed test. The remaining blockers are external
credentials and network egress (see FINAL_EXTERNAL_DEPENDENCY_MATRIX.md).

**This pass added:** ADR-106 passwordless sign-up · ADR-107 source access states + user-supplied full text ·
ADR-108 ten evidence routes + multi-compound reasoning + labelled evidence graph · ADR-109 source dependency
and independent-evidence count + research saturation · ADR-110 Memory Center + extraction confidence +
conflict objects · ADR-111 query sets + evidence-completion tasks + four gap types + job retry/switch counters.

**Verified:** backend 1161/1161 (0 failed, 0 skipped) on a fresh database; migrations up → down → up;
plugin 221/221; dashboard rules 33/33; 45 screens × 6 widths × LTR/RTL clean; English locale clean;
live E2E-K2C-001 order #30 on real WordPress/WooCommerce; live tenant isolation; browser-verified research
console, evidence graph, dependency and saturation panels, Memory Center and wallet.

---

## Historical state (Phase 13 snapshot)

**Project:** AI Operating Layer
**Current Phase:** Phase 13 — Analytics, Demand Intelligence and AI Access
Control: **IMPLEMENTED, NOT VERIFIED, NOT ACCEPTED.** `PHASE 13 = BLOCKED`,
`PHASE 14 = LOCKED`. Phase 12 remains CONDITIONAL, which locks Phase 13 on
its own (MASTER §146); separately, no Phase 13 test, migration or render
has been executed. See `docs/phase13/PHASE13_REPORT.md`.

**Prior line:** Phase 12 — P12-18/P12-19 implemented; live provider execution ENVIRONMENT BLOCKED. Prior line: Phase 12 — AI Visibility (complete); Phase 3 Document Intelligence completed retroactively (ADR-065)

## Completed Phases

- ✅ Phase 0 — Foundation (Docker, FastAPI, PostgreSQL, Redis, CI)
- ✅ Phase 1 — Identity & Multi-Tenancy (Organizations, Users, Sites, Auth, RBAC)
- ✅ Phase 2 — Knowledge Core (Knowledge Objects, Entities, Claims, Relationships, Versions, Gaps)
- ✅ Phase 3 — Sources, Documents, Chunks, pgvector
- ✅ Phase 4 — Evidence, Claim/Evidence linking, Conflict foundations
- ✅ Phase 5 — Research Engine (ResearchProject, ResearchTask, worker execution foundation)
- ✅ Phase 6 — Query Engine, Intent, Query Clustering
- ✅ Phase 7 — Commerce & Product Knowledge (Products, Offers, Product Evidence, Product Relations, Trust)
- ✅ Phase 8 — Recommendation Engine (Customer Context, deterministic explainable recommendation)
- ✅ Phase 9 — WordPress Adapter: generic machine identity, adapter mappings, tenant-aware rate limiting, SQL-level tenant integrity

## Next Phase

**Phase 10 — WooCommerce Adapter** (see docs/development.md)

## Phase 9 summary

- **AI Access Toolkit absorbed** — 23 capabilities classified, 13
  refactored, 6 replaced, 1 deprecated. No `AAT_*` class survives and the
  plugin registers no REST routes; both asserted by negative tests. See
  `AI_ACCESS_TOOLKIT_CAPABILITY_MAP.md` and ADR-045…049.

- **Generic machine identity** (ADR-036): `Installation` +
  `InstallationCredential`, with `AdapterType` making WordPress one
  value rather than the model. Tenant is **derived from the credential,
  never accepted from a request** — no Phase 9 request schema has an
  `organization_id` field at all.
- **`wordpress_mappings` is adapter state, not truth** (ADR-038). It is
  the only place a WordPress concept exists in the codebase; no Core
  model gained a WordPress field, and nothing in Core reads it to decide
  anything. Idempotency is enforced by unique constraints, so a webhook
  delivered five times produces one row.
- **Tenant-aware rate limiting** (ADR-039), positioned after identity
  and before Core work.
- **A3 closed at SQL level** (ADR-037): migration `0010` replaces eight
  single-column FKs with composite ones, so the database itself now
  rejects a cross-tenant parent. Proven by tests that bypass the service
  layer entirely.
- **`DEBT_REGISTER.md` introduced** (ADR-040) after discovering a Phase
  0 debt entry that had been stale for four review cycles.
- **Core + plugin test counts: see docs/development.md (authoritative)**, verified by real runs; full
  migration cycle verified. Breakdown: **415** (Phase 8 hardened
  baseline) + **28** new Phase 9 tests
  (`test_phase9_machine_identity.py` 22, `test_sql_level_tenant_integrity.py`
  6) + **1** B3 test appended to `test_recommendation_policy.py` = 444, plus **12** Redis-down
  fail-open tests added afterwards = **456**.
  An earlier report quoted "443 prior + 28 new"; 443 was an
  *intermediate* run taken before the B3 test was added, and was
  mislabelled as the baseline. Corrected here.

## Phase 8 summary

- New models: `CustomerContext` (§32 — privacy-safe, no conversation
  storage, fully anonymous by default) and `Recommendation` (§33 —
  every score paired with a `SignalState`, structured JSONB `reason`,
  and a `policy_version` for reproducibility).
- **`app/contracts/commerce.py`** — a read contract OWNED BY the
  Commerce domain (ADR-027). Phase 8 consumes Phase 7 exclusively
  through it and never touches Phase 7's ORM models or tables, so a
  Product schema change does not propagate into Recommendation.
- **Hard gates vs soft signals are structurally separate**: no score
  can overturn a gate, because gates run before scoring. This is what
  prevents a profitable-but-irrelevant product from being recommended.
- **UNKNOWN ≠ NEGATIVE** (ADR-028): no evidence scores neutral and is
  labelled UNKNOWN; rejected evidence scores low and is labelled
  NEGATIVE. Tested directly as a ranking invariant.
- **Abstention is first-class**: EDUCATE/REASSURE modes, withdrawn
  consent, and "nothing eligible" all return NO_RECOMMENDATION with an
  explanation, at HTTP 200.
- Rejected candidates are returned with named gates, so "why not that
  product?" is answerable.
- New endpoints: `/context` (CRUD + withdraw-consent), `/recommendations`
  (generate, list, read). Migration `0009`.
- **Two-layer verification invariant** (ADR-032): a product-evidence
  link or trust record counts as verified only when it AND its
  underlying `Evidence` are both VERIFIED — enforced at write time and
  recomputed at read time, so revoking an Evidence row immediately
  stops it counting. Found by independent review; the prior test suite
  had encoded the defective behaviour as correct.
- **415/415 tests passing** (346 prior + 69 new) on a from-scratch
  database; full migration cycle verified.

## Phase 7 summary

- New models: `Product` (§26 — "a normalized Product Knowledge Object",
  deliberately carrying no price/stock), `Offer` (§27 — kept separate
  so price/availability/seller can vary), `ProductEvidence` (§28 — the
  `claim` column is NOT NULL and is what preserves evidence scope),
  `ProductRelation` (§29, directional, never auto-mirrored), and
  `TrustRecord` (§30 — **no score column, `evidence_id` NOT NULL**).
- **Evidence scope is structural, not advisory.** Verifying a Phase 4
  `Evidence` row does NOT verify the product-level claim it is cited
  for. A study about Mannitol linked to a Taranjabin product produces
  an UNVERIFIED product-evidence link that a human must separately
  review — tested directly as an adversarial case (docs/DECISIONS.md
  ADR-025).
- **No fake trust.** Trust is answered by enumerating a subject's
  VERIFIED trust records, each with a claim, evidence and verification
  date — never by a stored number that could drift from the evidence
  beneath it (ADR-024).
- Migration `0008` **closes the deferred `intents.product_id` FK** that
  Phase 6's migration and model docstring both committed to in writing
  — the same pattern `0004` used for `relationships.source_id`.
- New endpoints: all five of §50's literal product paths, plus
  documented write endpoints (ADR-023).
- **346/346 tests passing** (281 prior + 65 new) on a from-scratch
  drop/recreate of a real Postgres database; full migration cycle
  verified.

## Phase 6 summary

- New models: `Query`/`QueryProvenance` (section 23 — three distinct
  roles for `query`/`normalized_query`/`raw_query`, see
  docs/DECISIONS.md ADR-015), `Intent` (section 24, multi-intent with a
  `WHERE is_primary` partial unique index), `QueryGroup`/
  `QueryGroupMembership` (section 25, curated grouping), and
  `QueryCluster`/`QueryClusterMembership` (additive — automatic
  similarity grouping, deliberately separate from curated groups).
- Rule-based intent classifier (`app/services/intent_classifier.py`) —
  built specifically to avoid the "کجا بخریم" (where to buy =
  TRANSACTIONAL) vs. "از کجا می‌آید" (where from = ORIGIN)
  disambiguation failure: every rule anchors on a multi-token phrase or
  unambiguous single word, never a bare ambiguous token; most-specific-
  first evaluation with span-consumption; zero matches leaves a query
  DISCOVERED rather than guessing.
- `Query.status` is a true 3-state lifecycle (DISCOVERED/CLASSIFIED/
  ARCHIVED) — CLASSIFIED is set automatically on first Intent, never a
  manual PATCH target. "Clustered"/"grouped" are derived facts, not
  status values.
- Query clustering v1 is word n-gram Jaccard similarity, not
  embeddings — the existing embedding provider is explicitly a
  semantically-meaningless placeholder, so clustering on top of it
  would look legitimate while being meaningless (docs/DECISIONS.md
  ADR-016).
- Knowledge Need is a computed judgment
  (`query_group_service.assess_knowledge_need`), never a persisted
  table — `QueryGroup` is explicitly NOT the Knowledge Need
  (docs/DECISIONS.md ADR-017). Gap creation stays on the existing
  `POST /knowledge-gaps` (Phase 2); Phase 6 never creates one itself.
- `research_reference_type` (Phase 5) additively extended with
  `query`/`query_group` (docs/DECISIONS.md ADR-018) — the only place
  this phase touches a prior migration's schema surface, additive only.
- New endpoints under `/queries`, `/query-clusters`, `/query-groups`
  (see docs/api.md for the full surface).
- Migration `0007`. Tenant isolation: both directions of the
  QueryGroup↔Query membership two-hop explicitly tested.
- **281/281 tests passing** (223 prior + 54 from Phase 6's initial
  delivery + 4 more from adding Excel `.xlsx` import in a follow-up
  revision) on a from-scratch drop/recreate of a real Postgres
  database; full migration cycle verified, including the enum-rebuild
  downgrade path for the additive `research_reference_type` extension.
- Excel (`.xlsx`) import was added after initial delivery, resolving a
  genuine spec deviation an independent review caught: section 23
  requires "Excel/CSV" (both formats), and v1 had shipped CSV-only.
  `openpyxl` now handles `.xlsx` alongside the existing CSV parser,
  sharing the same row-validation rules. See docs/DECISIONS.md
  ADR-020.
- This phase's design went through an explicit, point-by-point review
  against `docs/master-spec/MASTER_SPEC.md` (sections 23-25, 50)
  before implementation — see docs/DECISIONS.md ADR-015 through
  ADR-018.

## Architecture

- Backend: Python + FastAPI
- Database: PostgreSQL + pgvector
- Queue: Redis + Celery
- WordPress: Thin Adapter
- Source of Truth: Cloud Core

## Repository

- GitHub: https://github.com/hamedbiglari/AI-Operating-Layer
- Local: ~/Downloads/AI-Operating-Layer/AI-Operating-Layer