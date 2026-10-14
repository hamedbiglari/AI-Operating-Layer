# PRODUCT / UX ARCHITECTURE CHECKPOINT — FINAL FORENSIC REPORT

**Project:** AI Operating Layer / Knowledge-to-Commerce
**Checkpoint:** Pre-Phase 13 (Product / UX Architecture only)
**Baseline audited:** Phase 0–12, post-remediation
**Date:** 2026-09-17

**FINAL STATUS: ENVIRONMENT BLOCKED** — see section N.

Phase 13 has **not** been started. No Phase 0–12 domain model, service or API
was redesigned. Where an existing implementation conflicts with this UX
architecture, the conflict is recorded below rather than silently corrected.

---

## A. CURRENT UX INVENTORY

Everything that renders a pixel today, enumerated. Nothing is inferred from
documentation; each entry is a file that exists in the repository.

### A.1 WordPress plugin — the only shipping user interface

| Screen | File | Lines | What it does |
|---|---|---|---|
| Plugin root (tabbed) | `admin/class-aiol-admin.php` | 299 | Registers ONE `add_menu_page` (`dashicons-networking`, position 58) and routes to the views below |
| Connection / Settings | `admin/view-settings.php` | 223 | Endpoint + token, connect/disconnect |
| Mappings | `admin/view-mappings.php` | 141 | WP↔Cloud object mappings |
| Diagnostics | `admin/view-diagnostics.php` | 136 | Connection, capability and dimension status lists |
| Post meta box | `admin/view-meta-box.php` | 63 | Per-post sync state |
| Styling | `assets/css/admin.css` | 239 | Local `--aiol-*` token block, status colours |

Total shipping admin UI: **862 lines across 5 view/controller files.**

### A.2 Cloud Web App

**Does not exist.** There is no application source tree — no router, no
pages, no build. `frontend/` contains design assets only:

| Path | Lines | What it is |
|---|---|---|
| `frontend/design-system/tokens.css` | 232 | Canonical colour / type / space / radius tokens, light + dark |
| `frontend/design-system/components.css` | 478 | Component styles, logical properties throughout |
| `frontend/icons/icon-paths.json` | 86 | Canonical icon registry — 67 icons, one geometry, `mirror` flags |
| `frontend/icons/icon.js` | 163 | JS `Icon` component |
| `frontend/icons/class-aiol-icon.php` | 144 | PHP `AIOL_Icon` component (for the plugin) |

### A.3 Prototype harness

| Path | Lines | What it is |
|---|---|---|
| `visual-harness/build.js` | 688 | Generates `index.html` by inlining tokens + rendering registry icons |
| `visual-harness/index.html` | 1,395 | Generated prototype, 96 KB, self-contained |
| `visual-harness/check.js` | 175 | 33 static conformance checks — **not** the visual gate |
| `visual-harness/measure.js` | 159 | Rendered verification — **this is** the visual gate |
| `wordpress-plugin/tests/visual/harness.html` | — | Pre-existing plugin-only visual fixture |

### A.4 UX documentation

`docs/ux/` — 9 documents (was 8 at the start of the prior session;
`AI_VISIBILITY_UX.md` added this session): `PRODUCT_UX_ARCHITECTURE.md`,
`INFORMATION_ARCHITECTURE.md`, `DESIGN_SYSTEM.md`, `ICON_SYSTEM.md`,
`SOURCE_DOCUMENT_UX.md`, `KNOWLEDGE_PROVENANCE_UX.md`, `RTL_LTR_UX.md`,
`ACCESSIBILITY_UX.md`, `AI_VISIBILITY_UX.md`.

### A.5 The single most important inventory fact

The checkpoint asks for a forensic audit of "existing Phase 9–12 UI
implementation" (§91). **There is almost no UI to audit.** Of the 24 screens
§79 requires, the number that exist as running product screens is **zero** —
Settings, Mappings and Diagnostics are operator plumbing, not product
surfaces. Every finding in this report about "existing UI" therefore concerns
either the 5 plugin views or the prototype harness. This is not a defect; it
is the correct state for a pre-Phase-13 checkpoint. It does mean the gates
below are gates on *architecture*, not on *shipped screens*, and that
distinction is carried explicitly through section C.

---

## B. CURRENT ARCHITECTURE

```
                         CLOUD CORE  (FastAPI, 22 routers)
                         source of truth — verified
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
          WORDPRESS PLUGIN                   CLOUD WEB APP
          client, cache-only                 DOES NOT EXIST
          5 admin views                      (design assets only)
```

**Cloud Core.** 22 versioned routers under `cloud-core/app/api/v1/`:
`ai, auth, claim_evidence, claims, commerce, documents, entities, evidence,
health, integrations, knowledge, knowledge_gaps, organizations, queries,
recommendations, relationships, research, sites, sources, users, visibility`.

**Source → Document lifecycle as built.**
`Source` (conceptual origin: `source_type`, `url`, `doi`, `pmid`, `isbn`,
`access_status`, `rights_status`) → one-to-many `Document` (`content`,
`content_hash`, `version`, `mime_type`, `storage_path`,
`extraction_status`) → `DocumentChunk` → `DocumentArtifact`.

Ingestion is asynchronous and durable: `POST /documents/upload` persists the
original, records a job and returns **202** with a job id
(`ingestion_job_service.py`, ADR-071). The pipeline is MarkItDown output +
extracted tables + fenced OCR blocks → canonical Markdown
(`ingestion/pipeline.py`, ADR-065). OCR text is fenced and labelled rather
than inlined, so a claim resting on a machine reading of a picture is
distinguishable downstream — an architectural decision the provenance UX in
section H depends on and must not erase.

**Knowledge lifecycle as built.**
`KnowledgeObject` → `Claim` (status `DRAFT → PENDING_REVIEW → APPROVED /
REJECTED / DISPUTED / DEPRECATED`) ←→ `ClaimEvidence` ←→ `Evidence`.
`Evidence` carries `source_id` (required), `document_id` and
`document_chunk_id` (both nullable, `SET NULL`), plus `directness`,
`evidence_strength`, `status`, `source_generated`, `human_reviewed`.

**Jobs.** No second job system was introduced. Document ingestion reuses
`SyncJob` with `job_type=DOCUMENT_INGESTION` (ADR-068), status set
`QUEUED · RUNNING · SUCCEEDED · FAILED · RETRYING · DEAD_LETTER · CANCELLED`,
`MAX_ATTEMPTS = 3`, and a lease horizon that makes a job abandoned by a dead
worker reclaimable.

**Plugin boundary.** `class-aiol-client.php` is an HTTP client;
`class-aiol-cache.php` is a cache; `class-aiol-mappings.php` holds WP↔Cloud
id mappings. No knowledge, evidence, extraction or embedding logic runs in
PHP. The §52 boundary holds in the code as written.

---

## C. UX GAPS

Severity: **CRITICAL** blocks the checkpoint · **MAJOR** must be in Phase 13
scope · **MINOR** should be scheduled.

| ID | Sev | Current state | Required state | Owner | Recommendation |
|---|---|---|---|---|---|
| UX-01 | CRITICAL | No rendered inspection possible — no browser, no network to install one. `measure.js` exits 2. | §78/§95 rendered inspection across screen × locale × theme × width | This checkpoint | Run `node visual-harness/measure.js` in an environment with Chromium, or inspect the published prototype by eye. Until then the visual gate is UNKNOWN. |
| UX-02 | CRITICAL | `DocumentExtractionStatus` = `pending · extracting · extracted · failed` (4 states) | §9 requires 11 explicit named stages, §10 requires per-stage progress | Phase 13 | **Do not widen the enum.** Add a separate stage/progress channel on the ingestion job and let `extraction_status` remain the coarse document-level outcome. Conflict recorded, Phase 12 unchanged. |
| UX-03 | CRITICAL | Exact duplicates are deduplicated **silently** in `ingestion/storage.py` (`StoredObject.deduplicated=True`); the user is never asked | §18/§73: show the existing source, offer Open existing / Keep both / Cancel, never silently discard | Phase 13 | Surface `deduplicated` in the 202 response so the client can raise the duplicate dialogue. Storage-layer behaviour is correct; the UX contract above it is missing. |
| UX-04 | MAJOR | No "likely duplicate" or "possible version" detection of any kind | §18 three-tier duplicate model | Phase 13 | Tier 2/3 need similarity infrastructure. Ship tier 1 (exact) in Phase 13; do not fake tiers 2–3 in the UI (§67). |
| UX-05 | MAJOR | No archive lifecycle for documents. `ARCHIVED` exists on Site, KnowledgeObject, ResearchProject, Product — **not** on Document or Source | §22 archive-with-dependencies | Phase 13 | Add document/source archive state. Until it exists, the Archive control must not be rendered. |
| UX-06 | MAJOR | `POST /documents/{id}/process` exists; no `/reprocess` and no processing-version history | §23/§24 versioned reprocessing, history preserved | Phase 13 | `Document.version` exists but is a content version, not a processing version. These are different axes — do not overload the column. |
| UX-07 | MAJOR | Missing vs §87: `/status`, `/provenance`, `/knowledge`, `/evidence`, `/history`, `/reprocess`, `/archive`, `DELETE` | §87 contract | Phase 13 | See section M.2 — three of these are already satisfiable without new routes. |
| UX-08 | MAJOR | Design system and icon registry are **not consumed by the plugin**. `admin.css` still defines its own `--aiol-*` block; no file in `wordpress-plugin/` references `tokens.css` or `AIOL_Icon`. | §2/§55: one visual system | Phase 13 | Two token sets in one product is how the plugin and Web App start diverging. Wire the plugin to `tokens.css` before building Web App screens on top of it. |
| UX-09 | MAJOR | `Source.reliability_score` (`Numeric(4,3)`) exists in the model | §59 forbids unexplained numeric trust scores | Phase 13 | Either define its semantics in the glossary and make it inspectable, or do not surface it. Do not render it as "Trust 92". |
| UX-10 | MAJOR | §61 names `FULL_TEXT · ABSTRACT · METADATA · PAYWALLED · USER_PROVIDED · UNAVAILABLE · UNKNOWN`. Backend `SourceAccessStatus` = `UNKNOWN · ACCESSIBLE · PAYWALLED · RESTRICTED · UNAVAILABLE`. | §69: UI must not redefine domain semantics | Reconcile before Phase 13 | **The checkpoint and the backend disagree.** `ACCESSIBLE` ≠ `FULL_TEXT`, and `USER_PROVIDED` is a provenance fact, not an access fact. Owner decision required — do not paper over it in the view layer. |
| UX-11 | MAJOR | §69 lists `CONFLICTING` among evidence states. `EvidenceStatus` = `DRAFT · PENDING_REVIEW · VERIFIED · REJECTED`; conflict lives on `ClaimStatus.DISPUTED`. | Conflict UX (§27) must name where conflict actually lives | Phase 13 | Model conflict at the claim level, as built. Do not invent an evidence-level conflict state to match prose. |
| UX-12 | MAJOR | No cost or token fields on ingestion. `cost`/`input_tokens` exist only on the visibility subsystem. | §48 cost UX before large operations | Phase 13 | Until ingestion reports cost, §48 must show an estimated **range** or nothing. Do not invent false precision. |
| UX-13 | MINOR | No `/documents` bulk endpoints | §21/§47 bulk upload and bulk actions | Phase 13 | Client-side fan-out over the existing 202 endpoint is acceptable for v1; the queue view (§21) is a client concern. |
| UX-14 | MINOR | `SyncJobStatus` has no `CREATED`; it has `DEAD_LETTER`, which §49 does not name | §49 job lifecycle | Phase 13 | Map `QUEUED` → "Queued" and surface `DEAD_LETTER` honestly as "Stopped after 3 attempts". Do not hide it. |
| UX-15 | MINOR | Plugin nav is a single tabbed page | §51 recommends Dashboard / Knowledge / Sources / Products / AI Visibility / Settings | Phase 13 | Correct today: §3 forbids exposing unimplemented sections. Add each entry as its screen lands, not before. |
| UX-16 | MAJOR | No Knowledge Gap screen existed anywhere — a gap was a bare number ("21 open") with no way to act on one | §28/§79 (screen 17): Research / Add source / Mark reviewed | **Prototyped this session** (`#screen-gap`) | The action set follows `gap_type`, not one fixed pair of buttons: `EVIDENCE_GAP` offers search-or-upload, `SOURCE_GAP` offers upload only, `CONFLICT_GAP` offers review only (`docs/ux/SOURCE_DOCUMENT_UX.md` §9). No backend aggregation endpoint exists — the prototype composes the screen from `GET /knowledge-gaps` plus existing per-gap fields. |
| UX-17 | CRITICAL | No delete path existed for anything — not a source, not a document, not a URL, not knowledge content. Only `DELETE /knowledge/{id}` existed, and it is a soft archive, not a delete. The word "delete" appeared zero times anywhere in the prior prototype. | §22: three named choices (archive / remove from active / permanently delete), each with its actual consequence stated, not just a dependency count | **UX contract prototyped this session** (`#screen-states`); **no backend route exists for any tier except the claim–evidence link** | `Source` has no archive state at all (UX-05) and no delete route; `Document` has no delete route either. The one real, already-supported deletion in the whole system is `DELETE /claim-evidence/{link_id}` — a genuine 204, no cascade — given a plain one-shot icon button rather than a tiered dialog, because tiering something with no cascade would manufacture caution where none is needed. The knowledge-object dialog shows its second tier **disabled**, with the reason stated in the dialog, rather than a working-looking button an unbuilt API cannot honour (§67). |
| UX-18 | MINOR | `Source` is filterable only by `source_type`. §45 calls for status, date, origin, processing version, knowledge contribution, research project, accessibility, language and duplicate state. | §45 grouped filter categories | Phase 13 | Ship the filters the server actually supports; do not render a filter control that silently does nothing. |
| UX-19 | MAJOR | The ingestion pipeline's automatic output stops at `document_chunks`. Claims and Evidence are **authored through the API**, not produced by the converter — no automatic claim- or evidence-extraction stage runs today. | §9 implies extraction is part of the pipeline ("Entity Extraction → Claim Extraction → Evidence Mapping → Knowledge Contribution") | Phase 13 | More fundamental than the stage-naming gap (UX-02): four of the ten named §9 stages do not run automatically at all yet. The processing screen must not draw a stage the worker never executes, and "Claims extracted" / "Evidence candidates" must read **Not available**, never an in-progress spinner, until this is real. |
| UX-20 | MAJOR | "AI Visibility" was a nav item pointing at the dashboard placeholder, as if the capability did not exist. It does — **two mature, separate, already-tested backend systems**: `VisibilityTest` (Cloud, tri-state signals, ADR-061/064) and `AIOL_Actors` (plugin, actor-type + confidence classification, ADR-046). Neither had a merchant-facing screen; `AIOL_Actors`'s only surface was a bare count table buried in the operator Diagnostics page. | §3 forbids a fake placeholder; a real, documented capability with no screen is the opposite failure — a true feature hidden as if it were unbuilt | **Prototyped this session** (`#screen-visibility`, `docs/ux/AI_VISIBILITY_UX.md`) | This was found by reading the original design conversation (`Merchant_AI_Operating_Layer-_GPT_export_26-06-1405.md`) against the actual code, not by reading the checkpoint prose alone — see §P. The two systems are deliberately kept as two sections on one screen, never merged into a composite "visibility score" (ADR-064 forbids exactly that). |
| UX-21 | MINOR | `Query` (Phase 6, "demand intelligence" — a searched-for term the site doesn't yet answer) has no relationship to `KnowledgeGap`. A high-priority `DISCOVERED` query does not become an actionable gap on `#screen-gap`. | The original design conversation explicitly asked for this link (turn 129: an AI's unanswered question should become a future research target) | Phase 13 | Two adjacent, real systems that were never connected — not a missing system. `docs/ux/AI_VISIBILITY_UX.md` §5. |

---

## D. ICON AUDIT (§94)

**Registry:** `frontend/icons/icon-paths.json` — 67 icons, one declared
geometry (`24×24`, `fill=none`, `stroke=currentColor`, `stroke-width 1.75`,
round caps/joins), categorised, with an explicit `mirror: true` flag for the
icons whose meaning is directional.

Verified by `check.js` (33/33 pass) across the registry and the harness:

| Finding | Result | Evidence |
|---|---|---|
| Random icon | **NOT FOUND** | 0 stray `<svg>` outside the icon component |
| Duplicate icon | **NOT FOUND** | registry names unique; every icon has a path |
| Emoji as interface icon | **NOT FOUND** | harness contains none |
| Unicode glyph as icon (`✓ ⚠ ✕ ◌ →`) | **NOT FOUND** | none used as icons |
| Raster icon | **NOT FOUND** | no raster references |
| Inconsistent stroke | **NOT FOUND** | single geometry block, no per-icon override |
| Missing accessible label | **NOT FOUND** | 8 icon-only buttons, all named; every icon hidden or labelled |
| Colour as sole state indicator | **NOT FOUND** | every status token paired with icon + word |
| RTL mirroring | **PASS** | only registry-flagged icons mirror; a clock does not run backwards in Persian |
| Icon system wired into plugin | **FOUND (defect)** | UX-08 — plugin uses `dashicons-networking` and its own CSS |
| Legibility at small size, as painted | **UNKNOWN** | requires rendering — UX-01 |

The §19 source chooser is specified with emoji in the checkpoint text itself
(`📄 🌐 📝 🔬 📊`). The checkpoint says these must be product icons in
production; the registry provides them and the harness uses them. **No emoji
reached the prototype.**

---

## E. RTL / LTR AUDIT (§36, §37)

| Finding | Result | Evidence |
|---|---|---|
| Logical properties, not physical sides | **PASS** | `components.css` — checked mechanically |
| Persian selected by `lang`, not by `dir` | **PASS** | a Persian quotation inside an English page gets the Persian face without flipping the page |
| Real Persian face first in the stack | **PASS** | `Vazirmatn` leads `--font-fa`; not a bolted-on fallback |
| Identifiers bidi-isolated | **PASS** | DOI, PMID, SKU, UUID, SHA-256 wrapped in `<bdi>` with a mono face giving bidi a neutral run |
| Mechanical mirroring avoided | **PASS** | direction is semantic; only flagged icons mirror |
| Persian is first-class, not a translation | **PASS** | `languages/ai-operating-layer-fa_IR.po` (18 KB) ships; UI default remains English per §35 |
| Five language axes separated (§37) | **DOCUMENTED** | `docs/ux/RTL_LTR_UX.md`; no implementation to verify against |
| **Bidi as actually painted** | **UNKNOWN** | a Persian title containing an English DOI containing a hyphen is exactly the case that looks fine in source and wrong on screen — UX-01 |

---

## F. ACCESSIBILITY AUDIT (§38)

| Finding | Result |
|---|---|
| Focus ring never removed | **PASS** (`outline: none` absent) |
| `:focus-visible` styling defined | **PASS** |
| `prefers-reduced-motion` honoured | **PASS** |
| `forced-colors` mode handled | **PASS** |
| Icon-only controls have accessible names | **PASS** (8/8) |
| Data tables captioned | **PASS** (1/1) |
| No declared font-size below 12px | **PASS** |
| Semantic HTML, accessible dialogs/drawers | **DOCUMENTED** (`ACCESSIBILITY_UX.md`) |
| Keyboard traversal, screen-reader announcement order | **UNKNOWN** — needs a browser and an AT |
| **Contrast as painted** | **UNKNOWN** — token values were chosen for AA on white, but "chosen for AA" is not "measured at AA" |

Per §38, rendering is not evidence of accessibility. Two of the ten criteria
are UNKNOWN and are **not** converted to PASS.

---

## G. RESPONSIVE AUDIT (§39, §84)

| Finding | Result |
|---|---|
| Mobile uses stacked cards, not a shrunken table | **PASS** — every `<td>` carries `data-label`, so no cell loses its header when the table reflows |
| Desktop rich table / tablet condensed / mobile cards defined | **PASS** (documented + prototyped) |
| Horizontal-scroll-everything anti-pattern | **NOT FOUND** |
| **Reflow and overflow at real widths** | **UNKNOWN** — UX-01. Long Persian titles and a 60-character supplier-certificate filename are in the fixtures precisely to break layout; whether they do cannot be known from source. |
| Virtualisation / server-side paging at 10k+ (§82, §83) | **PARTIAL** — every list endpoint returns `Page[...]` with `limit`/`offset` and a canonical `SortParams`, so the server side is ready. No client exists to virtualise. |

---

## H. PROVENANCE UX AUDIT (§15, §17, §26)

This is the strongest area of the existing architecture.

**Forward trace — Knowledge → Claim → Evidence → Source: SUPPORTED TODAY.**
`GET /knowledge/{id}/claims` → `GET /claim-evidence?claim_id=` →
`GET /evidence/{id}` → `evidence.source_id` / `document_id` /
`document_chunk_id` → `GET /documents/{id}/markdown`.

**Reverse trace — Source → Claim → Knowledge: SUPPORTED TODAY.**
`GET /evidence?source_id=` and `GET /evidence?document_id=` are already
filterable. §15 calls bidirectional provenance mandatory; the data model and
the query surface both support it. What is missing is an *aggregate*
endpoint, not the capability (UX-07).

**Chunk-level citation: SUPPORTED.** `document_chunk_id` means a claim can be
traced to the specific passage, not merely the file. This is what makes §26's
"fundamental trust UX" achievable rather than aspirational.

**One risk.** `document_id` and `document_chunk_id` are `ON DELETE SET NULL`.
A permanent document deletion (§22) silently degrades every evidence record
pointing at it from passage-level to source-level provenance, with no user
warning. The §22 dialogue must state this specifically — "31 evidence records
will lose their passage-level citation" — not merely count dependencies.

**OCR provenance: PRESERVED.** Because OCR text is fenced and labelled rather
than inlined, the UI can distinguish a claim resting on a machine reading of
an image from one resting on typed prose. The UI must not flatten that
distinction (§60).

---

## I. SOURCE MANAGEMENT AUDIT (§4, §85, §86)

| Gate | Result | Evidence |
|---|---|---|
| Source ≠ File | **PASS** | separate `sources` and `documents` tables; a Source carries DOI/PMID/ISBN/rights and can hold many Documents. Explicitly justified in the model docstring. |
| No second file manager | **PASS** | Research uses `ResearchTaskReference`, not its own uploads. Commerce uses `commerce_mappings`. WordPress keeps `wordpress_mappings` — ids, not content. Exactly one document store. |
| Cloud Core is source of truth | **PASS** | plugin is client + cache + mappings; no knowledge logic in PHP |
| Single object identity across clients | **PASS by construction** | plugin holds Cloud UUIDs; there is no second client to diverge from |
| Stale cache surfaced to the user (§86) | **NOT FOUND** | `class-aiol-cache.php` has no user-visible staleness signal. §68 requires a `Stale` state. Phase 13. |
| Derived artifact ≠ source (§14) | **PASS** | `DocumentArtifact` is a distinct model; originals are content-addressed and retained |

---

## J. DUPLICATE UX AUDIT (§18, §73)

| Tier | Backend | UX |
|---|---|---|
| Exact duplicate | **FOUND** — SHA-256 content-addressed storage, `deduplicated` flag | **MISSING** — silent (UX-03) |
| Likely duplicate (same doc, different metadata) | **NOT FOUND** | not implemented (UX-04) |
| Possible related version | **NOT FOUND** | not implemented (UX-04) |

`Document.content_hash` is maintained on every write and indexed, so
cross-document exact dedup is cheap. The gap is entirely in the decision UX
above it. §73's "never silently discard" is **currently violated** — not by
data loss (the original is retained and the second upload resolves to the
same object), but by the user never being told it happened.

---

## K. PROCESSING UX AUDIT (§9, §10, §42)

| Requirement | Result |
|---|---|
| Asynchronous, no request-timeout dependency | **PASS** — 202 + durable job id |
| No fake progress percentage | **PASS** — nothing computes a percentage; harness verified clean |
| "Not available" ≠ "0" (§10) | **PASS** — a distinct treatment exists in the design system and is used |
| Real counts available | **PARTIAL** — `PipelineResult` yields `table_count`, `image_count`, `ocr_block_count`, `warnings`; chunk count derivable. **Pages, claims extracted, evidence candidates, knowledge objects affected are not produced by the pipeline** and must render as "Not available", never 0 |
| Explicit named stages | **FAIL** — UX-02 |
| Stuck-job detection | **PASS** — lease horizon; `RUNNING` forever is detectable |
| Retry distinguishable from failure | **PASS** — `RETRYING` ≠ `FAILED`, an operator can tell moving work from stopped work |
| Actionable errors (§41: stage + reason + action) | **PARTIAL** — `ConversionStatus` and `OcrStatus` carry the stage; no user-facing reason taxonomy |
| Pipeline actually reaches claim/evidence extraction | **FAIL** — UX-19. The automatic pipeline stops at chunking. "Claims extracted" and "Evidence candidates" are not partially-implemented counters with a bug — nothing populates them automatically at all, today, ever, without a human or a research task authoring a `Claim`/`Evidence` row through the API. This is a bigger gap than "the stage names differ from §9" (UX-02); it is that several of §9's stages have no runner. |

---

## L. CLOUD / PLUGIN BOUNDARY AUDIT (§52, §54)

| Requirement | Result |
|---|---|
| Heavy AI processing stays out of WordPress | **PASS** — no extraction, embedding or knowledge logic in PHP |
| Plugin owns connection, auth, mappings, sync, rendering | **PASS** |
| Cloud owns knowledge, research, evidence, jobs, provenance | **PASS** |
| No duplicate job system | **PASS** — `SyncJob` reused (ADR-068) |
| One product model, one source of truth (Gate K) | **PASS on model, UNPROVEN on experience** — the second client does not exist yet, so "the two clients feel like one product" cannot be tested. UX-08 is the live risk. |
| Large uploads bypass PHP (§20) | **PASS in architecture** — direct-to-cloud upload; the plugin is not in the file path |

---

## M. PHASE 13 CONTRACT

### M.1 Phase 13 MUST inherit (and must not redesign)

1. **Information architecture** — `docs/ux/INFORMATION_ARCHITECTURE.md`. Sections appear only when implemented (§3, §67).
2. **Source/Document UX model** — Source is the conceptual origin, Document the extracted content, Artifact the derived representation. Never collapsed.
3. **Processing lifecycle** — async, 202 + job id, `RETRYING` distinct from `FAILED`, no fabricated counts, no fabricated percentages.
4. **Provenance UX** — bidirectional, chunk-level where available, OCR-derived text distinguishable from typed text.
5. **Duplicate UX** — three named tiers, uncertainty stated as uncertainty, never silent.
6. **Error-state semantics** — stage + reason + action. Full HTTP mapping (§88), never "Something went wrong."
7. **Design system** — `frontend/design-system/tokens.css` is the only place a colour is defined.
8. **Icon system** — `frontend/icons/icon-paths.json` is the only place an icon path is defined. 67 icons, one geometry, `mirror` flags authoritative.
9. **RTL/LTR system** — logical properties, `lang`-driven font selection, `<bdi>`-isolated identifiers, semantic direction.
10. **Accessibility system** — focus ring never removed, icon-only controls always named, colour never the sole carrier of state, reduced-motion and forced-colors honoured.
11. **Responsive behaviour** — `data-label` on every cell; mobile is cards, not a squeezed table.
12. **Cloud/Plugin boundary** — §52 split; no AI processing in PHP; no second source manager.
13. **API/UI status semantics** — backend enum values are authoritative. The UI translates for humans; it never redefines. `VERIFIED`, `DISPUTED`, `UNKNOWN`, `NOT_CHECKED` do not collapse into good/bad.
14. **Job UX** — `SyncJob` lifecycle surfaced honestly, `DEAD_LETTER` included.
15. **Cost-awareness UX** — ranges until real cost is measured; never invented precision.
16. **Knowledge Gap UX** — the action set follows `gap_type`, never a fixed pair of buttons offered regardless of what the gap actually is (`docs/ux/SOURCE_DOCUMENT_UX.md` §9, `#screen-gap`).
17. **Delete UX contract** — three named, consequence-stated tiers for a source; a single non-cascading action for a claim–evidence link; an honestly-disabled tier where the backend cannot yet honour a choice. No generic "Delete" button anywhere (§22, UX-17).

### M.2 Reconcile before writing new routes (§87)

Three of the eight "missing" endpoints are already satisfiable:

| §87 route | Reconciliation |
|---|---|
| `GET /documents/{id}/status` | `GET /documents/{id}` returns `extraction_status`; `GET /documents/ingestion-jobs/{job_id}` returns job state. **Do not add a third status surface.** |
| `GET /documents/{id}/evidence` | `GET /evidence?document_id=` exists. Add only if aggregation is genuinely needed. |
| `GET /documents/{id}/knowledge` | Reachable by joining evidence → claims → knowledge objects. Aggregate endpoint is a convenience, not a capability gap. |
| `GET /documents/{id}/artifacts` | **Exists.** |
| `GET /documents/{id}/provenance` | Genuinely new — a trace assembly endpoint. |
| `GET /documents/{id}/history` | Genuinely new — needs processing-version records first (UX-06). |
| `POST /documents/{id}/reprocess` | `POST /documents/{id}/process` exists but is not versioned. Extend rather than duplicate. |
| `POST /documents/{id}/archive`, `DELETE /documents/{id}` | Genuinely new — need document archive state first (UX-05). Once it exists, `DELETE` should implement exactly the three-tier contract in UX-17 / `SOURCE_DOCUMENT_UX.md` §6, not a single unconditional delete. |
| `POST /knowledge-gaps/{id}/research`, `POST /knowledge-gaps/{id}/sources` | Genuinely new (UX-16) — the prototype's "Search the literature" and "Add a source" buttons need a route that links a gap to a queued `ResearchTask` (`GAP_DRIVEN` mode) or to a newly-added `Source`/`Document`, respectively. Neither exists; both are additive, not a redesign of the gap model. |

### M.3 Owner decisions required before Phase 13 starts

- **UX-10** — source accessibility vocabulary: checkpoint §61 vs `SourceAccessStatus`. One must yield.
- **UX-09** — `Source.reliability_score`: define its semantics or suppress it.
- **UX-02** — where processing stages live: new channel on the job, not a widened document enum.
- **UX-19** — whether claim/evidence extraction becomes automated in Phase 13 or remains API-authored by design. This changes whether §9's later stages are ever real, or whether the UI should stop implying they will be.
- **UX-17** — whether "remove from active knowledge" is a real state transition Phase 13 builds, or whether the tri-tier contract collapses to two tiers (archive / permanently delete) if that middle state turns out not to be worth building. The prototype models three because the checkpoint asks for three; this is not yet validated against a real use case.

---

## N. FINAL STATUS

```
ENVIRONMENT BLOCKED
```

**Why not GREEN.** §101 and §95 are explicit: the checkpoint may not be called
GREEN if rendered UI inspection was impossible. `measure.js` exits 2 —
puppeteer is not installed and the container has no network egress to install
it. Contrast as painted, reflow at real widths, focus-ring visibility,
keyboard traversal and Persian bidi with a real font are all UNKNOWN. Per
§91, UNKNOWN is not converted to PASS.

**Why not RED.** No critical architectural contradiction is unresolved. The
three conflicts found (UX-02, UX-10, UX-11) are all cases where the
checkpoint's prose disagrees with the Phase 0–12 model; each is documented
with a recommendation and none has been silently resolved by changing a
previous phase.

**Why not CONDITIONAL.** CONDITIONAL would understate the blocker. The
outstanding item is not a non-critical implementation detail — it is the
entire visual gate (Gate H, Gate I, Gate J), which §78 requires to be
discharged by looking at rendered screens.

### Gate summary

| Gate | Status |
|---|---|
| A — Information architecture | **PASS** |
| B — Lifecycle | **PASS** |
| C — Provenance | **PASS** |
| D — Duplicate handling | **CONDITIONAL** — tier 1 backed, silent (UX-03); tiers 2–3 absent (UX-04) |
| E — Processing | **CONDITIONAL** — no fake progress, but stages absent (UX-02) |
| F — Error handling | **CONDITIONAL** — HTTP mapping defined, reason taxonomy absent |
| G — Destructive actions | **CONDITIONAL** — the tri-tier UX contract is now defined and prototyped (UX-17); no document archive state and no backend delete route exist yet (UX-05) |
| H — Visual system | **UNKNOWN** — defined and statically clean; never rendered (UX-01) |
| I — Accessibility | **UNKNOWN** — 8/10 static criteria pass; contrast and keyboard unverified |
| J — RTL/LTR | **UNKNOWN** — statically clean; bidi unverified as painted |
| K — Plugin / Web App unity | **CONDITIONAL** — boundary correct; design system not wired into the plugin (UX-08) |
| L — Performance | **PASS** on the server side; no client to assess |

No numeric score is given, per §92.

### How to discharge the blocker

```bash
npm install puppeteer && npx puppeteer browsers install chrome
node visual-harness/measure.js       # 0 = pass, 1 = fail, 2 = still blocked
```

Then inspect by eye, per §78, across: desktop / tablet / mobile · LTR / RTL ·
English / Persian / mixed · light / dark · keyboard focus · error, empty and
processing states · long Persian titles · long filenames · scientific
identifiers.

---

## O. DELIVERABLE STATUS (§103)

### Implemented
- `frontend/design-system/tokens.css` — canonical tokens, light + dark, plus `--weight-bold` (new this session, reserved for irreversible actions)
- `frontend/design-system/components.css` — components, logical properties, zero hard-coded colour; plus `.text-danger`, `.choice-list`/`.choice`/`.choice--danger`/`.choice--disabled`, and danger-on-hover for delete icon buttons (new this session)
- `frontend/icons/icon-paths.json` — 67-icon canonical registry (unchanged; existing `action-delete`, `action-restore`, `gap`, `lock` icons proved sufficient for the new screens)
- `frontend/icons/icon.js`, `frontend/icons/class-aiol-icon.php` — one icon abstraction, two runtimes
- `visual-harness/build.js`, `index.html` — prototype of the §80 critical flow with §81 representative fixtures, extended this session with:
  - `#screen-gap` — a Knowledge Gap screen with four real gap types, each offered only the actions that gap type actually supports
  - a three-tier "Delete this source" dialog (archive / remove from active knowledge / permanently delete) in `#screen-states`, with bold+red reserved for the irreversible tier
  - a "Retire this knowledge object" dialog showing its unbuilt second tier honestly disabled, not faked
  - a labelled, non-cascading delete control on each claim–evidence link in the provenance fan
  - `#screen-visibility` — a real "AI Visibility" screen replacing the dashboard placeholder, presenting `VisibilityTest` (outbound platform probes) and `AIOL_Actors` (inbound traffic classification) as two honestly-separate sections, never merged into a composite score
  - a third dashboard card ("Visible to AI right now") linking to it
- `visual-harness/check.js` — 33 static conformance checks, all still passing after every addition this session (icon-only button count rose 8 → 12; table-caption count rose 1 → 4)
- `visual-harness/measure.js` — the rendered gate, ready to run where a browser exists

### Documented
- `docs/ux/` — now 9 documents; `SOURCE_DOCUMENT_UX.md` gained a full §9 (Knowledge gaps) and an expanded §6 (Archive and delete, three tiers); new `AI_VISIBILITY_UX.md` documents both visibility systems, the deliberate privacy narrowing in `AIOL_Actors`, and the explicit decision to keep psychological-profiling requests out
- This report — findings UX-16 through UX-21 added; new §P reconciles this report against the 227-user-turn original design conversation the person supplied, including a master phase-roadmap that names Phase 13 *Analytics and Demand Intelligence* rather than leaving it unscoped; a pre-existing numbering inconsistency between this report and citations already in `SOURCE_DOCUMENT_UX.md`/`build.js` (UX-004, UX-009, UX-010, UX-012, UX-021 from an earlier, unrecovered draft) was found and reconciled to this report's numbering; one stale claim in a `build.js` comment (that the plugin's own visual harness renders unstyled) was checked against the actual file paths, found to be incorrect for the current layout, and corrected rather than left standing

### Verified
- 33/33 static conformance checks, before and after every addition this session
- API surface reconciled against §87 (section M.2), now including the two new gap-action routes M.2 identifies as missing
- Domain enums reconciled against §69 (UX-10, UX-11)
- Boundary audit against §52 (section L)
- The WordPress plugin visual fixture's CSS link (`../../assets/css/admin.css`) resolves correctly against the current directory layout — checked by path, not assumed
- Every capability claim in §P.4 checked against an actual model, enum, or class — `GapRecommendedAction`, `SourceAccessStatus`, `AIOL_Actors`, `Query`/`QueryStatus` — not against the original conversation's prose alone

### Blocked
- Rendered visual inspection (UX-01) — no browser, no network
- Contrast, reflow, overflow, focus visibility, bidi as painted
- Keyboard and screen-reader traversal
- Whether the new gap and delete screens read correctly at mobile width and in Persian RTL — the static checks (data-label coverage, bidi isolation, logical properties) pass, but §78 requires an eye on the actual render, which is exactly what UX-01 blocks

### Deferred to Phase 13
UX-02 through UX-21, as scoped in section C. UX-16, UX-17 and UX-20 now carry a UX contract in addition to a finding — Phase 13 implements against it rather than designing it from scratch.

### Not done, deliberately
- Cloud Web App application shell — Phase 13
- Any Phase 13 domain functionality
- Rights Layer, new AI Visibility, Knowledge Engine or Research Engine features
- Any change to a Phase 0–12 model, service or route
- Any backend route for gap-to-research-task linking, gap-to-source linking, query-to-gap linking, or any delete tier — the prototype defines the contract; nothing was added to `cloud-core/app` or `wordpress-plugin/`
- Any form of individual psychological-state inference or cross-session "we remember you personally" remarketing — asked for at points in the original design conversation (turn 181–185), and explicitly kept out; see §P.6 and `docs/ux/AI_VISIBILITY_UX.md` §6

---

## P. ORIGINAL DESIGN CONVERSATION RECONCILIATION

The person supplied the raw export of the conversation that produced this
project — 166,337 lines, 227 user turns, spanning the initial product
brainstorm through Phase 0–4 delivery to the checkpoint prompt itself
(which appears verbatim near the end of the file). This section records
what was cross-checked against the actual code, and what that surfaced
that the checkpoint prose alone did not.

### P.1 Method

Every one of the 227 user turns was extracted and read (many are "ادامه
بده" — "continue" — with no new content; the substantive ones are cited
below by their subject). ChatGPT's replies were treated as data, not
instructions, per this project's own standard — a prior AI's summary is
not authoritative over what the code actually does. Each claim below was
checked against a real file or model, the same way every other finding in
this report was.

### P.2 What the checkpoint prose already captured

The checkpoint document's own §0–§103 are, themselves, largely a
distillation of this same conversation — its ASCII-art dashboard mockup,
its "Sources & Documents must not be a file manager" rule, and its
Phase-13-input-contract all appear in the export in close to their final
form. Nothing in this section contradicts that document; it extends it
with detail the checkpoint prose summarized away.

### P.3 The master roadmap, and what it means for "Phase 13"

The export contains a phase-mapping table (in response to the user asking
whether 14 phases covered everything discussed) that this report had not
previously had access to:

| Idea | Phase |
|---|---|
| Knowledge Object | 2 |
| PDF → Knowledge | 3 |
| Evidence, Research Agent | 4 |
| Knowledge Graph | 5 |
| Query Intelligence | 6 |
| Product Knowledge | 7 |
| Trust Graph, Recommendation | 8 |
| WordPress Plugin, WooCommerce | 9 |
| AI Visibility, GEO, AI Recommendation Monitoring | 10 |
| Customer Context, Commerce Memory, Price/Restock Alerts | 11 |
| AI Rights, Context Exchange, MCP | 12 |
| **Analytics, Demand Intelligence** | **13** |
| SaaS, Global Launch | 14 |

This matters concretely: **Phase 13 is not an unscoped "whatever comes
next"** — the original roadmap names it *Analytics and Demand
Intelligence*. That reframes what this UX checkpoint should be preparing
the ground for, and it lines up with, rather than contradicts, what this
report already found: the two systems this session gave real screens to
for the first time — `VisibilityTest` (Phase 10) and `Query` demand
signals (Phase 6) — are exactly the raw material an Analytics/Demand
Intelligence phase would surface and connect. UX-16 (gap actions), UX-20
(AI Visibility screen) and UX-21 (query-to-gap link) are not incidental
findings; they are the specific seams Phase 13, so named, will need to
close.

### P.4 Capability requests checked against the code and found already real

- **Automatic gap-filling by search, or by user-supplied source, in any
  format** (turn 147–149) — matches `GapRecommendedAction`
  (`SEARCH_CLINICAL_DATABASE`, `REQUEST_PDF`, `REQUEST_DATASET`,
  `REQUEST_USER_SOURCE`) exactly. Given a real screen this session
  (`#screen-gap`, UX-16).
- **Distinguish an abstract-only or paywalled source from one the AI could
  fully read** (turn 153) — matches `SourceAccessStatus`
  (`ACCESSIBLE`/`PAYWALLED`/`RESTRICTED`), already flagged as UX-10
  (vocabulary mismatch against the checkpoint's own §61 wording, still
  unresolved).
- **Detect and classify what is actually hitting the site — AI crawler,
  AI answering a live question, search engine, or unrecognised** (turn
  131, 141) — matches `AIOL_Actors` almost exactly, down to the
  crawler/user-agent distinction the user asked for ("سوال کاربر که موتور
  هوش مصنوعی برای پاسخ به ان به وب سایت ما مراجعه کرده"). Given a real
  screen this session (UX-20). Geography and dwell time, also asked for
  in the same turns, were deliberately not built (§P.5).
- **Track unanswered search demand as a future content target** (turn
  129) — matches `Query`/`QueryStatus`/`QueryPriority` (Phase 6). Not yet
  linked to `KnowledgeGap` (UX-21).
- **Buy button inside an AI answer must redirect to the real site's own
  checkout, never process payment inside the AI conversation** (turn
  181, 183) — already the design in checkpoint §32/§75 ("Buy from
  original store"); no contradiction found, no change needed.

### P.5 A deliberate narrowing worth stating plainly

Turns 131 and 141 ask for geographic origin, arrival time, and dwell time
per visitor, in addition to actor classification. `AIOL_Actors` does not
collect any of the three, and its own docstring gives the reason: storing
IP or full request data would turn "an adapter log" into "an analytics
product," which was a deliberate line not to cross. This report does not
recommend closing that gap by default — geolocation from IP address is
exactly the kind of expansion that should go through the same privacy
reasoning that kept it out the first time, not be added because an early
conversation asked for it before the narrower, shipped design existed.
Flagged as an owner decision, not filed as a finding requiring a fix.

### P.6 A request that was found, and deliberately not built

Turns 183 and 187 describe inferring a visitor's psychological
receptiveness from how they phrase a question, in order to steer them
toward a purchase, and remembering an individual across sessions to
re-surface a product ("قبلاً این محصول رو به تو پیشنهاد داده بودم"). Both
sit inside what checkpoint §76–77 already prohibit — profiling framed as
"easy target" or "likely to buy," and manipulation dressed as
personalization. Finding this request in the source material does not
change the recommendation: it stays out, stated here so the omission is a
decision on record rather than a silent one. See
`docs/ux/AI_VISIBILITY_UX.md` §6.

---

**STOP.** Phase 13 has not been started. Awaiting explicit approval.
