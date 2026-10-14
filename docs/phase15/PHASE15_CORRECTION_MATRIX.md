# PHASE 15 CORRECTION MATRIX

| ID | Source | Finding | Classification | Severity | Correction | Test | Runtime Evidence | Status |
|---|---|---|---|---|---|---|---|---|
| P14-CORRECTION-001 | Phase14 master prompt §18 / Phase 15 pilot Case G | No user-facing manual retry endpoint existed for a failed ingestion job | PHASE14_REQUIREMENT_GAP_DISCOVERED_IN_PHASE15 | High | Added `POST /documents/ingestion-jobs/{job_id}/retry`; `ingestion_job_service.retry_job` (Model A, ADR-MANUAL-RETRY.md) | Manual, real HTTP calls against a real fresh DB (see below) | `docs/phase15/runtime-evidence/p14-correction-001.log` | CORRECTED, VERIFIED |
