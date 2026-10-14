# Source & Document UX

Status: **UX contract.**

## 1. Lifecycle the user can see

```
Add → Upload → Security → Convert → Structure → OCR → Chunk
    → [Extract] → Review → Knowledge → Completed
```

Stages in brackets are **not implemented today**. See
`PRODUCT_UX_ARCHITECTURE_CHECKPOINT_REPORT.md` finding UX-19: the ingestion
pipeline ends at chunking. Claims and Evidence are authored through the API,
not produced by the converter. The UI must not draw a stage the worker never
runs, and must not imply the system extracted a claim it did not.

Implemented stages map to real records:

| Stage shown | Where its truth lives |
|---|---|
| Upload | original bytes retained before the 202 (`OriginalSourceStore`) |
| Security validation | upload size/type validation in `ingestion_service` |
| MarkItDown conversion | `document_conversions.conversion_status` + `converter_version` |
| Structure detection | `document_tables` |
| Image detection | `document_assets` |
| OCR | `document_assets.ocr_status`, `ocr_block_count` |
| Semantic chunking | `document_chunks` |
| Completed | `documents.extraction_status = extracted` |

## 2. Status vocabulary is the backend's, not the UI's

The interface renders `DocumentConversionStatus`, `DocumentOcrStatus`,
`DocumentAssetStatus`, `SyncJobStatus` and `SourceAccessStatus` as they are.
It does not invent friendlier words, and in particular it never merges:

- `unsupported` with `failed` — a missing capability is not a bad file
- `no_text_found` with `unavailable` — "we read it, there was no text" is a
  finding; "we had no OCR engine" is not
- `empty` with `failed` — a PDF that converts to nothing did convert
- `failed` with `dead_letter` — one will be retried, one has stopped trying
- `absent` with `not_checked` — measuring absence is not the absence of a
  measurement

## 3. Counts

Every count shown must come from a record. If a subsystem produced no count,
the value is **Not available**, rendered distinctly, never `0`. `0` is a
measurement.

Counts that are derivable today by query: knowledge objects, claims, evidence
and research projects touched by a source (via `evidence.source_id` and
`claim_evidence`). Counts that are **not** available today: a per-source
processing cost, a per-source token usage, and any "extraction confidence"
for anything other than a table.

## 4. Upload

Preferred architecture is a signed direct-to-storage upload. What exists is a
multipart `POST /documents/upload` through the API, which returns `202` with
a durable job id after the bytes are safely stored. The UI is built against
the job model, so moving to signed URLs later changes the transfer step only
and not the status experience.

Progress during transfer is real (bytes sent / bytes total). Progress *after*
the 202 is not: the worker reports a stage, not a percentage, so the UI shows
the stage. A number with no semantic basis is forbidden (§42).

Bulk upload is a queue of independent jobs and is presented as one. It is
never presented as a single synchronous operation.

## 5. Duplicates

Three distinct verdicts, three distinct wordings, never presented as more
certain than the evidence:

| Verdict | Basis | Wording |
|---|---|---|
| Exact duplicate | identical `source_hash` (SHA-256 of the original bytes) | "This file is already here" |
| Likely duplicate | same document, differing metadata — **not implemented** | "Likely the same document" |
| Possible related version | near-match / newer edition — **not implemented** | "Possibly a newer version" |

Only the first is computable today; `source_hash` is indexed and the
default idempotency key is `ingest:<org>:<source_hash>`, so a re-upload
returns the same job with `job_created: false`. That signal is currently
invisible to the user — see UX-03. The other two verdicts are UX contracts
for later work and must not be shown until something real backs them.

Nothing is ever silently discarded. The user chooses: open the existing
source, keep both, or cancel.

## 6. Archive and delete

Delete is never one generic button (§22, finding UX-17). Three named
choices, each with a stated consequence, prototyped in
`visual-harness/index.html` (`#screen-states`, "Delete 'Toranjebin —
Scientific Review 2025'?"):

| Choice | Reversible | What actually happens |
|---|---|---|
| Archive source | Yes | Stops future use. Every existing claim, evidence record and knowledge contribution is untouched. Dependencies are enumerated before the dialog is shown — fetched, not estimated. |
| Remove from active knowledge | Yes | Can no longer be cited by new work. Existing claims and evidence stay published, unchanged. |
| Permanently delete | **No** | The original file and its derived Markdown/tables/OCR text are removed. Evidence rows pointing at the deleted document (`document_id`, `document_chunk_id`) are `ON DELETE SET NULL` — they do not vanish, but they degrade from passage-level citation to source-level only. The dialog states this specific consequence, not just a dependency count. |

The permanently-delete option is the one place in the design system where
bold text and `--danger` red are used together (`--weight-bold`,
`.text-danger`) — reserved for the choice that cannot be undone, never used
elsewhere, so it keeps its meaning (§77).

An already-archived source has nothing left to "remove from active"; its
dialog collapses to a choice between staying archived and permanent deletion.

None of the three choices exist as API routes yet (`Source` has no archive
state, and there is no `DELETE /sources/{id}` or `DELETE /documents/{id}`).
This is the UX contract Phase 13 must implement against.

A related, already-real action needs no tiers: removing one
claim–evidence *link* (`DELETE /claim-evidence/{link_id}`, a genuine 204
today) never cascades, so it is a single labelled icon-button next to each
evidence item in the provenance fan (`#screen-provenance`), not a dialog. It
removes the link, never the underlying evidence, document or source.

A knowledge object has only one tier today: `DELETE /knowledge/{id}` is
`archive_knowledge_object` under a REST-shaped name — it sets `status =
ARCHIVED` and nothing is actually removed. The prototype's retire dialog
(`#screen-states`) shows a second, "permanently delete knowledge content"
tier **disabled**, with the reason stated in the dialog itself, rather than
rendering a working-looking button an unbuilt API cannot honour (§67).

## 7. Reprocessing

Reprocessing creates a new processing version. It states, before running,
which converter, OCR configuration and extraction level the new run will use,
and that existing provenance is preserved. History is never overwritten in
place.

## 8. Filters and sorting

Sorting goes through the Phase 11 contract (`SortParams` +
`SORTABLE_FIELDS`). An unsupported field returns 422 naming the permitted
values; the UI surfaces that as a validation message and never silently
falls back to a different order.

Sortable today for `Source`: created_at, updated_at, title, source_type,
reliability_score, published_at. For `Document`: created_at, updated_at,
title, extraction_status.

Filterable today for `Source`: `source_type` only. The filter panel in this
architecture calls for status, date, origin, processing version, knowledge
contribution, research project, accessibility, language and duplicate state.
Those need server support that does not exist (UX-18). Ship the filters that
work; do not render controls that silently do nothing.

## 9. Knowledge gaps

A gap (`KnowledgeGap`: `gap_type`, `status`, `recommended_action`) is not one
generic "fill this in" prompt. The action offered follows `gap_type`, and
the prototype (`#screen-gap`) shows why that matters with four real
examples:

| Gap type | What closes it | Not offered |
|---|---|---|
| `EVIDENCE_GAP` (e.g. no human clinical trial found) | Search the literature (queues a `GAP_DRIVEN` research task) *or* add a source, if the user already holds one | — |
| `SOURCE_GAP` (e.g. a missing supplier certificate) | Add a source | Search the web — there is nothing public to find |
| `ACCESS_GAP` (e.g. a paywalled paper) | Add a source (the full text, if obtainable) | Marking it resolved without full text |
| `CONFLICT_GAP` | Review the conflict directly | Search or upload — the sources already exist; the conflict needs a decision, not more input |

"Search the literature" queues a task; it does not fabricate a result. Per
§64, anything it finds lands as a **review**, not a publish. "Add a source"
reuses the same Add Source flow — a gap accepts a source in any format (PDF,
spreadsheet, or a link), it is not a special-cased upload path.

`GapStatus` values (`OPEN`, `IN_PROGRESS`, `RESOLVED`, `DISMISSED`) are
rendered as-is, matching §69: a resolved gap is shown resolved, not deleted
from the list, so the history of what the knowledge layer once didn't know
stays visible.
