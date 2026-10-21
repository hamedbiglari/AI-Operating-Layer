# Prompt v4.0 — Phase A audit and Phase B gap analysis

Audited 2026-10-14 against the delivery of 2026-10-13 (migration head `0036`, 1255 tests reported).
Baseline commit: `d192804` in this repository (local git initialised for this work — the only
repository previously was the owner's home directory).

Classification key: **EXISTS · PARTIAL · MISSING · BROKEN · DUPLICATED · NEEDS HARDENING**.
Basis key (§3): **FACT** (read in code / executed) · **SIGNAL** (documented, not executed here) ·
**INFERENCE** · **HYPOTHESIS**.

## A. What exists (FACT, read in code)

| Area | Where | Notes |
|---|---|---|
| Ingestion, two-phase (HTTP persist → Celery convert) | `services/ingestion_service.py`, `ingestion_job_service.py`, `workers/tasks.py` | Original bytes retained, magic-byte validation, quarantine |
| Converter boundary | `ingestion/converter.py` (`DocumentConverter`, MarkItDown default) | Format normaliser, not a layout provider |
| PDF structure | `ingestion/extractors.py` (pdfplumber tables, pypdf images, tesseract OCR) | Levels 1–3; level 4 (vision) not built |
| Extraction persistence | `models/document_artifact.py` (`document_conversions/tables/assets`) | Converter name + version recorded |
| Claims, evidence, direct/indirect | `models/claim.py`, `evidence.py`, DB CHECKs (ADR-101/108) | Indirect routes cannot become direct |
| Conflicts | `evidence_conflicts` (ADR-110) | System never picks a side |
| Category schema + Master Topic Matrix | ADR-114, `knowledge_schema_service.py` | Cross-topic propagation as pending proposals |
| Coverage audit | ADR-115, `coverage_audit_service.py` | Six dimensions, versioned, failure-safe |
| Publications + Vancouver resolver | ADR-116, `citation_resolver.py`, `publication_service.py` | First-appearance numbering enforced by DB |
| AI invocation, routing, jobs | `ai/invocation.py`, `ai_routing_service.py`, `ai_job_service.py` (ADR-089/090) | One job system for AI work (`ai_jobs`), checkpoint/handoff |
| Budgets | wallet reserve/settle (ADR-086/104), per-job cost cap (`max_cost_per_job`) | Financial budget only |
| Dashboard | `02-dashboard/index.html`, 48 screens, live panels | `screen-chat` is a labelled no-backend fixture |

## B. Gap matrix

| § | Requirement | Status | Finding |
|---|---|---|---|
| 5–6 | Canonical Document Representation (not Markdown) | **MISSING** | `Document.content` = assembled Markdown and is called "canonical" (`ingestion/pipeline.py`). No block/line structure, no reading order, no geometry. |
| 7 | All outputs derived from one representation | **PARTIAL** | Tables stored structurally; everything else only as Markdown. |
| 8.1–8.2 | Text, layout, multi-column, headers/footers | **MISSING** | MarkItDown text only; no column/reading-order logic. |
| 8.3 | Tables preserved | **PARTIAL** | pdfplumber rows kept; no cell geometry, spans or page-spanning tables. |
| 8.4–8.5 | Equations / chemistry | **MISSING** | No detection, no representation. |
| 8.6 | Figures with captions/location | **PARTIAL** | Images recorded (incl. unread ones); no bbox, no caption association. |
| 9 | Geometry provenance | **MISSING** | No bbox anywhere; `evidence` links to a chunk, not to a page or location. |
| 10 | Differentiated confidence | **PARTIAL** | Table confidence only; no text/layout/equation/figure/overall. |
| 11 | Provider abstraction | **PARTIAL** | `DocumentConverter` exists; no Mathpix / vision / alternative provider contract. |
| 12 | Fallback + candidate retention | **MISSING / BROKEN** | No fallback. Reprocessing **deletes** previous tables and assets (`process_pending_conversion`), so earlier candidates are not auditable. |
| 13 | No information loss | **BROKEN** | (a) `ai_job_service.run_job` stores findings as `result[:4000]` — silent truncation. (b) `extractors.MAX_PAGES=200`: pages beyond 200 are skipped for tables/images with no note. |
| 14–17 | Context assembly, budgets, context packs | **MISSING** | AI jobs take one prompt per item; nothing assembles context from the KB, nothing packs, nothing tracks per-unit status. |
| 18–21 | Hierarchical, coverage-preserving synthesis; lost-information detector; two-path audit | **MISSING** | `current_synthesis` is "a mechanical merge … not an AI synthesis". No unit ledger, no omission reasons. |
| 22 | Model routing by task | **EXISTS** | Six routing modes, stage-scoped steps (ADR-089). Reuse. |
| 23 | Three budgets | **PARTIAL** | Financial only. No context or reasoning budget. |
| 24–25 | Async batch + states | **PARTIAL** | Celery + `SyncJob` for ingestion; per-document `partially_processed` / `needs_review` missing. |
| 26 | Multilingual originals preserved | **PARTIAL** | `Document.language` only; no script/direction per element. |
| 27 | Audio / video | **MISSING** | No ASR provider. Extension point only in this pass (time ranges on elements). |
| 36 | Coverage audit | **BROKEN** | (a) processing dimension counts `succeeded`/`completed`, but documents are stored `extracted` → every processed topic reports **0 % extracted**. (b) publication dimension still says "no publication layer exists" although migration 0035 added one. |
| 37 | Last data update vs last verified audit | **MISSING** | Not tracked separately. |
| 39–42 | Vancouver citation, resolver, integrity, references | **EXISTS** | Verified by reading; DB constraints enforce one-number-one-source. |
| 35 | Master Topic Matrix | **EXISTS** | ADR-114. |
| 46–54 | Persistent command workspace | **MISSING** | `screen-chat` is a static fixture; nothing persisted. |
| 55–56 | Technology watch / versioning | **PARTIAL** | converter name+version recorded; no query "which documents came from older technology". |
| 57–58 | Benchmark, information-loss rate | **MISSING** | |
| 66 | Failures never become "complete" | **BROKEN** | `run_job` ends `completed / COMPLETED` even when items failed. |
| 69 | No duplicate architecture | **NEEDS HARDENING** | Two job tables exist by earlier ADRs (`sync_jobs` for ingestion, `ai_jobs` for AI). Not consolidated here (would be a rewrite); new work reuses `ai_jobs` for AI work and `sync_jobs` for ingestion — no third. |

## C. Integration plan (Phase C)

| Gap | Extends | Schema | API | UI |
|---|---|---|---|---|
| Bugs §13/§36/§66 | existing services | none | none | none |
| CDR + geometry + confidence + candidates | `ingestion/`, `document_artifact.py` | `0037`: `document_elements`; confidence + provider + `is_current` on `document_conversions`; `conversion_id` on tables/assets; location on `evidence` | `/documents/{id}/elements`, `/render/{fmt}`, `/conversions`, `/reprocess`, `/extraction/stale` | Source detail (existing) |
| Provider abstraction + Mathpix contract | `ingestion/providers/` | — | provider list | — |
| Context assembly + synthesis ledger | `ai_jobs` (job system), `ai_routing_service` | `0038`: `synthesis_runs`, `synthesis_units` | `/synthesis/...` | Workspace |
| Command workspace | `ai_jobs`, synthesis, KB services | `0039`: `workspace_commands`, `workspace_command_versions` | `/workspace/commands/...` | `screen-chat` replaced by the workspace |
| Coverage §37 | `coverage_audit_service` | `last_data_update_at` on audit | existing | existing |
| Benchmark | new `ingestion/benchmark.py` | none | none | — |
