# Forensic audit — Phases 0–12 gap matrix

**Method:** every row below was established by executing code in this
environment, not by reading a prior phase report. Where a claim could not be
executed, it is marked ENVIRONMENT BLOCKED rather than assumed.

---

## PART 1 — Document Intelligence / MarkItDown (executed, not assumed)

I installed MarkItDown 0.1.7 and ran it against **real fixture documents I
generated** (not mocks). The results contradict the assumption in the brief
that "MarkItDown already provides the capability" for images and tables.

| Fixture | Result | Verdict |
|---|---|---|
| `simple.pdf` (text) | 71 chars, correct | **WORKS** |
| `tables.pdf` (real table) | Columns **flattened**: `Compound Amount Unit / Mannitol / Glucose / Water / 42.1 / 18.7 / 12.0` — rows and columns scrambled, no Markdown table | **FAILS the table requirement (§7)** |
| `with_image.pdf` (embedded figure) | `See figure below.` — **the image is silently dropped**, no placeholder, no warning | **FAILS the image requirement (§6)** |
| `persian.docx` | Correct Markdown table + Persian preserved (`ماده`/`مقدار`, `۴۲ گرم`, correct ی/ک) | **WORKS** |
| `data.xlsx` | Correct Markdown table incl. Persian cell | **WORKS** |
| `broken.pdf` (malformed) | Returns the literal string `"None"` — a **silent garbage success**, not an error | **UNSAFE — needs guarding (§16)** |
| `empty.pdf` | Raises `FileConversionException` | **Correct failure** |

**With the official `markitdown-ocr` plugin enabled (`enable_plugins=True`):**

| Case | Result |
|---|---|
| `with_image.pdf` | Adds `## Page 1` structure but **still drops the embedded image** |
| `figure.png` direct | **0 characters returned** |
| Same PNG via `tesseract` directly | `FIGURE yield by year` — **reads fine** |

**FACT:** `tesseract 5.3.4` is present and functional. The OCR capability
exists; MarkItDown 0.1.7 does not wire it to these cases.

**INFERENCE:** satisfying §6 (images), §7 (tables) and §8 (OCR) requires our
own extraction layer *around* MarkItDown — MarkItDown alone is necessary but
not sufficient. Claiming otherwise would be the "fake completion" §0.3
forbids.

---

## PART 2 — Repository gaps

| # | Requirement | Expected | Actual | Status | Owner |
|---|---|---|---|---|---|
| G1 | §4/§5 file ingestion | Accept PDF/DOCX/XLSX/PPTX | **No upload endpoint.** `Document.content` accepts JSON plain text only | **RED** | Phase 3 |
| G2 | §5 MarkItDown engine | Default converter | **Not a dependency; zero references** | **RED** | Phase 3 |
| G3 | §6 images | Detect/extract/OCR, never discard | **No image handling anywhere** | **RED** | Phase 3 |
| G4 | §7 tables | Structured + Markdown, traceable | **No table extraction** | **RED** | Phase 3 |
| G5 | §8/§9 OCR | Cost-aware level routing | **No OCR path** | **RED** | Phase 3 |
| G6 | §14 provenance | 20+ fields incl. `source_hash`, `converter_version` | **0 of 20.** `content_hash` hashes *text*, `storage_path` never written | **RED** | Phase 3 |
| G7 | §10 original preserved | Never destroy original | **No file storage at all** | **RED** | Phase 3 |
| G8 | §11/§25 machine representation | Knowledge Object → Markdown/JSON/JSON-LD | **Absent from Core.** Plugin `?aiol_format=md` renders **WordPress `post_content`**, not the canonical Knowledge Object | **RED — §12 violation** | Phase 3/9 |
| G9 | §17 ingestion security | MIME/size/zip-bomb/quarantine | **None** (no ingestion to secure) | **RED** | Phase 3 |
| G10 | §18 document cost control | Budget guard for OCR/Vision | Visibility budget exists (ADR-063); **nothing for documents** | **RED** | Phase 3 |
| G11 | §51 status docs agree | All documents consistent | **`CURRENT_STATE.md` says "Phase 9"** while `ACTIVE_TASK.md` says "Next: Phase 13" | **RED** | docs |
| G12 | §38 budget concurrency | Atomic reservation | **read→decide→write**, racy under concurrency | **AMBER** | Phase 12 |
| G13 | §39 probe vs observation | Separate concepts | Only observation exists; `collection_method` distinguishes provenance | **AMBER — partially met** | Phase 12 |
| G14 | §0.2 no destructive Git in mutation testing | Isolated restore | **VIOLATED in Phase 11** — a `git checkout` reverted unrelated work and needed repair | **FIXED PROCESS** | process |

## PART 3 — Verified correct (no action)

| Area | Evidence |
|---|---|
| Phase 1 tenant isolation | Composite FKs + negative tests, 559 Core tests green |
| Phase 4 two-layer verification | ADR-032, enforced at read time |
| Phase 7 Product ≠ Offer | ADR-050 directional rule, tested |
| Phase 8 abstention | Recommendation can refuse, tested |
| Phase 11 UNKNOWN ≠ NEGATIVE | `coverage` block, 21 tests |
| Phase 11 sorting | 39/41 routes, 6/6 mutations caught |
| Phase 12 tri-state signals | 7/7 mutations caught |
| Dead code | No dead enums, no unregistered routers, Celery task dispatched |

## PART 4 — Environment reality

| Dependency | Status |
|---|---|
| PostgreSQL 16 + pgvector | **AVAILABLE** |
| MarkItDown 0.1.7 | **AVAILABLE** (pypi allow-listed) |
| tesseract 5.3.4 | **AVAILABLE** |
| WordPress runtime | **ENVIRONMENT BLOCKED** |
| WooCommerce runtime | **ENVIRONMENT BLOCKED** |
| Browser / RTL visual | **ENVIRONMENT BLOCKED** (Chrome CDN not allow-listed) |
| Real AI platform APIs | **ENVIRONMENT BLOCKED** (no credentials) |

---

## Conclusion

The **entire document-intelligence chain (G1–G10) is unimplemented**, and it
is the backbone of the architecture in §60. Everything downstream —
entities, claims, evidence, knowledge — currently depends on a human pasting
plain text into a JSON field.

Crucially, this is **no longer environment-blocked**: MarkItDown and
tesseract both install and run here. It can be built for real.
