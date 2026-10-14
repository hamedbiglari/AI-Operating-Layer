# Active Task

**Task ID:** P13-IMPL

**Status:** IMPLEMENTED — AWAITING VERIFICATION AND OWNER APPROVAL

Phase 13 (Analytics, Demand Intelligence, AI Access Control) has been
written in full and executed by nothing. Do not treat it as delivered.
Before any further Phase 13 work, run section 8 of
`docs/phase13/PHASE13_REPORT.md` in an environment that has Python
dependencies, PostgreSQL, PHP and a browser.

**Last completed:** Phase 12 P12-18 visibility infrastructure + P12-19 search intelligence (759 Core tests, 9/9 mutations, real Celery+Redis E2E PASS)

**Previously completed:** Phase 3 Document Intelligence completion — MarkItDown + table/image/OCR extraction (ADR-065/066/067)

**Previously completed:** Phase 12 — AI Visibility: tri-state signals, budget guard, no composite score (559 Core + 193 plugin tests)

**Previously completed:** Phase 11 — AI/REST interfaces: agent-facing read API, coverage honesty block, capability manifest, §51 sorting gap closed (529 Core + 193 plugin tests; sort rollout closed)

**Previously completed:** Phase 10 — WooCommerce adapter: commerce_mappings, sync_jobs, directional truth rule (483 Core + 193 plugin tests; unverified in live WordPress/WooCommerce)

**Previously completed:** Phase 9 — WordPress Adapter (Core-side): machine identity, adapter mappings, rate limiting, SQL-level tenant integrity (464 Core + 68 plugin PHP tests, migration cycle verified; plugin unverified in a live WordPress)

**Previously completed:** Phase 8 — Recommendation Engine: CustomerContext, Recommendation, Commerce read contract, deterministic explainable policy (415/415 tests, real Postgres, full migration cycle verified)

**Previously completed:** Phase 7 — Commerce & Product Knowledge: Product/Offer/ProductEvidence/ProductRelation/TrustRecord, evidence-scope enforcement, deferred intents.product_id FK closed (346/346 tests, real Postgres, full migration cycle verified)

**Previously completed:** Phase 6 — Query Engine, Intent, Query Clustering: Query/QueryProvenance, rule-based Intent classifier, QueryGroup + Knowledge Need assessment, QueryCluster n-gram clustering (281/281 tests, real Postgres, full migration cycle verified)

**Next:** verification of Phase 13, then the Phase 13 gate. Phase 14 is
LOCKED. Note: `development.md` names Phase 13 "Rights Layer"; the original
roadmap recovered in checkpoint §P.3 names it "Analytics and Demand
Intelligence", and the owner's Phase 13 instruction is analytics + AI
access. The naming conflict is recorded here rather than resolved
silently — the Rights Layer (MASTER §42) is NOT built.