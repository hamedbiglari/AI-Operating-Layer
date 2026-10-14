# Document Intelligence — architectural clarification and capability matrix

## The clarification

**MarkItDown is the PRIMARY DOCUMENT NORMALIZATION ENGINE. It is not the
Document Intelligence engine.**

Document Intelligence is the pipeline as a whole:

```
Original File
 → Secure Intake
 → File Validation / Quarantine
 → MarkItDown Conversion          ← normalization only
 → Document Structure Extraction
 → Table Extraction / Validation  ← ours
 → Embedded Image / Figure Extraction ← ours
 → OCR when required              ← ours
 → Vision analysis only when required ← policy-gated, not built
 → Canonical Markdown Artifact
 → Structured Document Artifacts
 → Semantic Chunking
 → Entity / Claim / Evidence extraction
 → Knowledge Object
```

MarkItDown owns exactly one box. Assigning it the others would be assigning
it capabilities that **measured testing shows it does not reliably provide**.

## Why this clarification is evidence-based, not stylistic

Measured in this environment, MarkItDown 0.1.7 against real fixtures:

| Claim | Measured result |
|---|---|
| "preserves PDF tables" | **FALSE** — `tables.pdf` flattened to `Compound Amount Unit / Mannitol / Glucose / Water / 42.1 / 18.7 / 12.0`; rows and columns scrambled |
| "preserves embedded images" | **FALSE** — `with_image.pdf` returned only `See figure below.`; the figure vanished with no placeholder or warning |
| "OCR plugin handles images" | **FALSE for these cases** — with `enable_plugins=True` the image is still dropped; a PNG passed directly returns **0 characters** |
| "handles scanned PDFs" | **UNVERIFIED here** — no scanned fixture produced a positive result |
| "fails safely on malformed input" | **FALSE** — `broken.pdf` returns the literal string `"None"`, a silent garbage success |
| "converts DOCX/XLSX tables" | **TRUE** — correct Markdown tables, Persian preserved |
| "handles Persian/mixed script" | **TRUE** — `ماده`/`مقدار`, `۴۲ گرم`, correct ی/ک, no mojibake |

**Stating MarkItDown does these things would be false.** The clarification
exists so the architecture does not depend on a capability that is not there.

---

## Capability matrix

| Capability | MarkItDown | Our additional layer | Fallback | Cost | Provenance | Test coverage |
|---|---|---|---|---|---|---|
| PDF → text | **YES** (verified) | none needed | — | Level 1, negligible | `converter_name/version` | `simple.pdf` |
| DOCX/PPTX/XLSX → Markdown | **YES** incl. tables (verified) | none needed | — | Level 1 | same | `persian.docx`, `data.xlsx` |
| Persian / mixed script | **YES** (verified) | none needed | — | Level 1 | `language` | `persian.docx` |
| **PDF tables** | **NO** — flattens | **pdfplumber**: `lines` strategy, then `text` strategy | text strategy; then flattened MarkItDown text, flagged low confidence | Level 2, ~0.01s/page measured | `extractor`, `strategy`, `confidence` | `ruled.pdf`, `tables.pdf` |
| **PDF embedded images** | **NO** — silently drops | **pypdf** `page.images` | record image exists with `extraction_status=failed` rather than drop | Level 2, cheap | `page_number`, `asset_id`, `source_hash` | `with_image.pdf` |
| **OCR of extracted images** | **NO** — 0 chars on direct PNG | **tesseract 5.3.4** via subprocess | `ocr_status=unavailable`; never silently empty | Level 3, ~0.3s/image | `ocr_engine`, `ocr_version`, `ocr_status` | `figure.png` |
| Scanned-page OCR | **NO** | full-page rasterize → tesseract | `NOT_IMPLEMENTED`, recorded | Level 3 | same | **deferred — no fixture** |
| Figure/chart semantics | **NO** | **not built** — vision model | `vision_status=not_attempted` | Level 4, expensive | `vision_model` | **deferred, policy-gated** |
| Malformed input safety | **NO** — returns `"None"` | guard: treat `"None"`/empty as `CONVERSION_FAILED` | explicit failure status | free | `conversion_status` | `broken.pdf`, `empty.pdf` |

---

## Dependency decisions

Each dependency was selected after measuring it here, not by popularity.

### `markitdown[pdf,docx,pptx,xlsx]` 0.1.7 — ADOPT

- **Reason:** official Microsoft normalization engine; strong on Office
  formats and Persian, which is our hardest text case.
- **Owner:** Phase 3 Document/Ingestion.
- **License:** MIT.
- **Security:** runs in-process and parses untrusted input — must run in the
  Cloud Core worker, never in WordPress, behind size/MIME validation.
- **Performance:** fast on the fixtures; no measured pathology.
- **Fallback:** conversion failure is an explicit status, never a silent pass.
- **Fixture:** all seven fixtures.
- **Provenance:** `converter_name`, `converter_version`, `conversion_options`.

### `pdfplumber` 0.11.10 — ADOPT (PDF tables)

- **Reason:** recovers the tables MarkItDown flattens. Measured: ruled table
  extracted perfectly with the default `lines` strategy; unruled table
  recovered with the `text` strategy. **The first apparent failure was my
  fixture having no grid lines, not the library** — worth stating, because
  concluding "pdfplumber can't do tables" from that would have been wrong.
- **Owner:** Phase 3.
- **License:** **MIT** — verified from package metadata.
- **Maintenance:** actively maintained; built on `pdfminer.six`.
- **Python:** works on 3.12 here.
- **Security:** pure Python, no subprocess, no network. Parses untrusted PDFs
  → needs page/time bounds.
- **Performance:** **0.013s** for a one-page table extraction, measured.
- **Fallback:** `lines` → `text` → flattened MarkItDown text at low confidence.
- **Provenance:** records which strategy succeeded.

### `pypdf` 6.18.1 — ADOPT (embedded images)

- **Reason:** extracts the embedded images MarkItDown drops. Measured: found
  and wrote the 1,947-byte PNG from `with_image.pdf`.
- **License:** **BSD-3-Clause** — verified from `License-Expression` metadata.
- **Security:** pure Python; bound decompressed size to resist decompression
  bombs.
- **Performance:** negligible on fixtures.
- **Fallback:** image recorded as detected-but-unextracted rather than dropped.

### `pytesseract` / `tesseract` 5.3.4 — ADOPT (OCR, Level 3)

- **Reason:** read the extracted figure correctly (`FIGURE yield by year`)
  where MarkItDown returned nothing.
- **License:** tesseract Apache-2.0; `pytesseract` Apache-2.0.
- **Security:** **subprocess on untrusted image data** — the sharpest edge
  here. Needs timeout, bounded input, no shell.
- **Performance:** ~0.3s/image; hence Level 3, never run by default.
- **Fallback:** `ocr_status=unavailable` if the binary is missing — never a
  silent empty string.

### `PyMuPDF` — **REJECTED**

- **Reason for rejection: AGPL-3.0** (verified from metadata:
  `Dual Licensed - GNU AFFERO GPL 3.0 or Artifex commercial`).
- For a network-served commercial Cloud Core, AGPL's network-use clause is a
  serious obligation. The commercial alternative is a paid Artifex licence.
- It is the fastest and most popular option, which is precisely why it is
  worth recording the rejection: **popularity is not a selection criterion,
  and the licence is a hard blocker, not a footnote.**

### `camelot`, `unstructured` — NOT ADOPTED

Camelot needs Ghostscript (**AGPL**) and is heavier for the same job
pdfplumber does. `unstructured` pulls a very large dependency tree and
overlaps MarkItDown's own role. Neither adds capability we lack.

---

## Cost-aware level routing

| Level | Work | When | Cost |
|---|---|---|---|
| 1 | MarkItDown conversion | always | negligible |
| 2 | pdfplumber tables + pypdf images | PDFs only | ~0.01–0.05s/page |
| 3 | tesseract OCR | only images likely to contain text | ~0.3s/image |
| 4 | Vision/LLM | **never by default** — policy-gated, not built | expensive |

The level actually used is recorded per document, so a reader can tell
whether a result came from cheap extraction or expensive interpretation.
