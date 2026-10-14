# MarkItDown / Document Normalization — forensic audit

**Scope:** audit only. No code was modified, no dependency added, no Git
operation performed.

---

## VERDICT

# MARKITDOWN STATUS: **E — NOT IMPLEMENTED**

Not B (partial), not C (boundary exists), not D (Markdown-only). **E.**

The distinction the audit brief warned about — "Markdown representation"
versus "MarkItDown document normalization" — does not even arise here,
because **neither exists in the ingestion path**. The one Markdown feature
in the repository (`AIOL_Representations::markdown()`, Phase 9) converts
*WordPress post content outward* for machine consumption. It is an output
representation, unrelated to document normalization, and it lives in the
WordPress plugin rather than Cloud Core.

---

## Evidence

### Search results — zero hits, every term

| Term | Occurrences repo-wide |
|---|---|
| `markitdown` / `MarkItDown` | **0** |
| `DocumentConverter` | **0** |
| `document converter` | **0** |
| `canonical markdown` | **0** |
| `markdown artifact` | **0** |
| `source artifact` | **0** |
| `conversion provenance` | **0** |
| `converter_version` | **0** |
| `conversion_status` | **0** |
| `source_hash` | **0** |

`markitdown` is **not in `requirements.txt`**. Neither is any binary-parsing
library: no `pypdf`, `pdfminer`, `python-docx`, `python-pptx`,
`beautifulsoup4`, `lxml`, `unstructured`, `pytesseract`. The only
file-parsing dependency is `openpyxl==3.1.5`, added in Phase 6 for
**query-list import** (ADR-020) — spreadsheet rows of search queries, not
document normalization.

### What the ingestion path actually is

`FACT.` There is no file intake. `Document.content` is a nullable `Text`
column populated **directly from a JSON request body**:

```
POST /api/v1/documents  { "title": ..., "content": "<plain text>" }
        ↓
document_service.create_document()   content stored verbatim
        ↓
content_hash = sha256(content)       hash of the TEXT, not of a source file
        ↓
chunking.chunk_text(document.content)
        ↓
DeterministicHashEmbeddingProvider   (documented non-semantic placeholder)
```

`FACT.` `Document.mime_type` defaults to `"text/plain"` and is a
**caller-supplied label**. Nothing reads it to select a parser.

`FACT.` `SourceType` includes a `pdf` value (used in
`tests/test_sources.py:80`). It is a **classification label on a Source
record** — "this citation is a PDF somewhere in the world" — not a parser
and not a stored file. No PDF is ever fetched, opened or parsed.

`FACT.` `Document.storage_path` exists as a nullable column and is **never
written by any service**. There is no artifact storage layer.

`FACT.` The only `UploadFile` in the entire Cloud Core API is
`POST /api/v1/queries/import` (Phase 6, CSV/XLSX query lists).

`FACT.` The only Celery task is `research.execute_task`. **No conversion
worker exists.**

### The repository already says so

`docs/ai-context/KNOWN_ISSUES.md` line 21, present since Phase 3:

> "No actual ingestion (URL, PDF, WordPress import) implemented yet."

This audit confirms that entry is still accurate. Nothing has changed it.

---

## Per-requirement findings

### Provenance fields — NOT IMPLEMENTED (0 of 12)

`source_file_id`, `source_hash`, `source_mime_type`, `source_size_bytes`,
`converter_name`, `converter_version`, `conversion_options`,
`conversion_status`, `output_artifact_id`, `output_size_bytes`,
`processing_duration`, `created_at` — **none exist.**

Nearest neighbours, and why they are not substitutes:
- `Document.content_hash` — sha256 of the **text**, not of a source binary.
- `Document.file_size` — `len(content.encode())`, the **text** length.
- `Document.mime_type` — an unvalidated caller-supplied label.
- `Document.extraction_status` — a Phase 3 enum tracking *chunking*, not
  conversion. Reusing it for conversion status would conflate two stages.

### Versioning — PARTIAL, and unrelated to conversion

| Version dimension | Status |
|---|---|
| source version | `Document.version` exists (int, manual) |
| converter version | **absent** |
| normalization version | **absent** |
| chunking version | **absent** |
| embedding model/version | **absent** — provider is a hardcoded placeholder |
| extraction model/version | **absent** |
| knowledge version | `KnowledgeVersion` exists (Phase 2) |

### Execution properties — NOT APPLICABLE

Asynchronous / Cloud-Core-isolated / resource-metered / retryable /
observable: **none apply, because no conversion runs.** The `sync_jobs`
infrastructure from Phase 10 exists and would be the right home, but has
no `job_type` for conversion.

### Controlled fallback — NOT IMPLEMENTED

There is no conversion, therefore no unsupported-format path and no
`CONVERSION_FAILED` state. **Nothing silently bypasses normalization —
there is no normalization to bypass.** This is a meaningful distinction:
the system is not quietly mis-handling documents; it simply does not accept
them.

### Deduplication — NOT IMPLEMENTED

`source hash + converter version + configuration` does not exist.
`content_hash` deduplicates identical **text**, which is a different thing.

### Downstream reuse — NOT APPLICABLE, but structurally favourable

There is no canonical Markdown artifact, so nothing reuses one. However
**nothing re-parses binaries either**, because no component parses binaries
at all. When MarkItDown is introduced, there is no existing duplicate
parsing to untangle — a genuinely clean starting position.

### Test matrix — 0 of 21 categories

PDF, DOCX, XLSX, PPTX, HTML, CSV, TXT, images, ZIP, unsupported, malformed,
empty, large, duplicate, conversion failure, OCR, Persian, mixed
Persian/English, RTL, tables, citations, URLs, Unicode, provenance —
**no test covers document conversion in any format.**

---

## Architectural owner

`INFERENCE, and I believe it is correct:` the owner is the **Phase 3
Document/Ingestion layer in Cloud Core** — `app/models/document.py`,
`app/services/document_service.py`, `app/services/chunking.py`.

Reasoning: `Document` already owns `content`, `mime_type`, `storage_path`
and `extraction_status`. A converter belongs beside them, not in a new
domain. Phases 9–11 must then **consume** the canonical artifact:

- **Phase 9/10 (WordPress/WooCommerce):** must NOT convert. The plugin is
  thin by contract (§45/§67) and a shared host cannot parse large PDFs. It
  should upload/register and receive a job id.
- **Phase 11 (AI/REST):** must read the derived Markdown, never re-parse.
- **Phase 12:** §32 of the Phase 12 brief already forbids a second parser.
  Since none exists, the correct Phase 12 behaviour is to **record the
  absence** and build nothing.

---

## Status classification

| Aspect | Status |
|---|---|
| MarkItDown library | **NOT IMPLEMENTED** |
| DocumentConverter abstraction | **NOT IMPLEMENTED** |
| Canonical Markdown artifact | **NOT IMPLEMENTED** |
| Conversion provenance | **NOT IMPLEMENTED** |
| Source preservation / artifact storage | **NOT IMPLEMENTED** (`storage_path` unused) |
| Security / quarantine pipeline | **NOT IMPLEMENTED** |
| OCR | **NOT IMPLEMENTED** |
| Async conversion worker | **NOT IMPLEMENTED** |
| Deduplication by source hash | **NOT IMPLEMENTED** |
| Document-format tests | **NOT IMPLEMENTED** |
| Plain-text Document model | **IMPLEMENTED + TESTED** (Phase 3) |
| Chunking over plain text | **IMPLEMENTED + TESTED** (Phase 3) |
| Markdown *output* representation | **IMPLEMENTED + TESTED** — Phase 9 plugin, unrelated to normalization |
| Excel/CSV **query-list** import | **IMPLEMENTED + TESTED** — Phase 6, unrelated to normalization |

Nothing here is `ENVIRONMENT BLOCKED`. Every finding was verifiable by
static inspection; no external environment was required.

---

## One conflict worth recording

`FACT.` **MarkItDown appears nowhere in `MASTER_SPEC.md`** — zero
occurrences. §44 defines the ingestion pipeline generically
(`INPUT → PARSER → CLEANER → STRUCTURE DETECTION → SEMANTIC CHUNKING → …`)
and never names a converter.

`INFERENCE.` MarkItDown is therefore an **implementation choice introduced
in the Phase 10/11 prompts**, not a Master Spec requirement. Under the
project's own source-of-truth hierarchy (Master Spec first), adopting it is
a legitimate engineering decision that satisfies §44's `PARSER` stage — but
it should be recorded as an **ADR**, not treated as pre-existing spec
compliance. It has never been implemented, so no ADR exists yet.

This matters for scope: §44's pipeline is a **Phase 3 concern that was
deferred**, and the deferral is documented. Building it now would be
completing Phase 3, not delivering Phase 11 or 12.
