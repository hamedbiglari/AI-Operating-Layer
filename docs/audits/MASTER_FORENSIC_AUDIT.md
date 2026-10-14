# Master forensic audit — pre-remediation inventory

Executed before any remediation code. Every row verified by running code.

## Phase 12 blocking defects (confirmed)

| ID | Defect | Evidence | Severity |
|---|---|---|---|
| **P12-01** | Original uploaded bytes discarded | `ingestion_service.py:223` — `storage_path=None` hardcoded | **P0 — data loss** |
| **P12-02** | Ingestion is synchronous | `upload_document` calls `ingest_document` inline; conversion + OCR run in the request | **P0** |
| **P12-16** | Budget is read→decide→write | `check_budget()` reads, decides, then `_record_spend` writes — two concurrent probes can both pass | **P0 — race** |
| **P12-17** | `VisibilityJobStatus` is **dead** | referenced exactly 1× (its own definition). Shipped as a PostgreSQL enum type in migration 0012 | **P1 — dead architecture** |

**P12-17 is self-inflicted.** I created `VisibilityJobStatus` during Phase 12
"mirroring SyncJobStatus's shape" and never wired it to anything. It is
precisely the unexplained artifact §52 forbids, and I introduced it while
auditing others for the same fault.

## Dead-code sweep

| Check | Result |
|---|---|
| Dead enums | **1** — `VisibilityJobStatus` |
| Unregistered routers | 0 |
| Celery tasks defined but never dispatched | 0 (`research.execute_task` only) |
| Duplicate domain models | 0 |

## Reconciliation entry — job architecture

**Conflict.** P12-02 requires async ingestion with job states
QUEUED/RUNNING/SUCCEEDED/FAILED/RETRYING/CANCELLED. Two candidate models
exist: `SyncJob` (Phase 10, canonical, in use) and `VisibilityJobStatus`
(Phase 12, dead).

**Selected interpretation:** extend `SyncJob` — the contract says "if an
existing canonical job model can be extended, extend it". `SyncJobStatus`
already has QUEUED/RUNNING/SUCCEEDED/FAILED/DEAD_LETTER/CANCELLED; only
RETRYING is missing.

**Consequence:** `VisibilityJobStatus` is **removed**, not wired. Keeping a
second job-state vocabulary would be the duplicate-domain fault §0.7
forbids. Requires a migration to drop the PostgreSQL enum type.

**ADR required:** yes — ADR-068.
