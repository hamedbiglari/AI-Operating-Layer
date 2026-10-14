# Phase 12 remediation — final report

## Blocking items addressed

| ID | Defect | Status | Evidence |
|---|---|---|---|
| **P12-01** | Original bytes discarded, `storage_path=NULL` | **FIXED** | ADR-070; 11 tests; byte-identical round-trip asserted |
| **P12-16** | Budget read→decide→write race | **FIXED** | ADR-069; 10 tests incl. real thread concurrency; 5/5 mutations |
| **P12-17** | `VisibilityJobStatus` dead enum | **FIXED** | ADR-068; removed; migration 0014 drops the PG type |
| **P12-25** | Contradictory status docs | **FIXED** | `CURRENT_STATE.md` no longer says "Phase 9" |
| **P12-05/08/09/10/11** | MarkItDown boundary, tables, images, OCR, provenance | **DONE (prior turn)** | ADR-065/066; 31 tests; 9/9 mutations |
| **P12-12/13** | Machine representation from Knowledge Object | **DONE (prior turn)** | ADR-067; 8 tests |

## NOT addressed — stated plainly

| ID | Item | Status |
|---|---|---|
| **P12-02/03** | Async ingestion via Celery; upload is still synchronous | **NOT IMPLEMENTED.** Enum + job type added (`DOCUMENT_INGESTION`, `RETRYING`); the worker task and 202 flow are not built |
| **P12-06/07** | URL / website ingestion, SSRF controls | **NOT IMPLEMENTED** |
| **P12-18/19** | Visibility project/run/snapshot/competitor models; Search Console boundary | **NOT IMPLEMENTED** |
| **P12-14** | Per-page/per-image ingestion workload caps beyond existing bounds | **PARTIAL** — extractor caps exist; no cost estimation for OCR |

## Test results — exact

```
command: python -m pytest -q
result:  619 passed, 0 failed, 0 skipped        (245.21s)

command: bash scripts/verify_migration_cycle.sh
result:  base -> head -> base -> head verified  (0014 included)
```

## Mutation results

Budget (5/5): read→decide→write reverted (1 fail) · limit check removed
(7) · release floor removed (1) · settlement ignores actual (2) · tenant
filter removed (1, after the test was strengthened).

All restores used **isolated file backups. No Git operation was used**
(§0.2/§0.3).

## Phase 12 gate

**NOT PASSED.** P12-02/03 (async ingestion) is a listed blocking
requirement and is not implemented. Per the contract's own rule —
"do not move unresolved Phase 12 requirements into Phase 13" — Phase 13
has not been started.
