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

