"""
The Processing view of one document (Step 7C-1): its pipeline as far as the
backend records it, and what it has produced so far.

Each stage is derived from the current conversion. Conversion, structure
detection and OCR are one run (ingestion_service.orchestrator.run) and share
its processing_state; the count each produced is the stage's detail, never its
state, because "0 tables" is a finished stage. Evidence extraction and
knowledge contribution have no stage data at all and are reported as not
tracked rather than guessed.

Step 7C-5: the document's latest ingestion job (D21, "latest attempt") is
returned as `job`, and its sync_job_stages rows, where present, replace the
derived stage of the same key (D20). Stages without a row stay derived.
"""

from uuid import UUID

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import Session

from app.models.claim_evidence import ClaimEvidence
from app.models.document import Document
from app.models.document_artifact import DocumentConversion
from app.models.document_chunk import DocumentChunk
from app.models.enums import DocumentExtractionStatus
from app.models.evidence import Evidence
from app.models.sync_job import SyncJob
from app.models.sync_job_stage import SyncJobStage
from app.schemas.document import StageState
from app.services.document_service import get_document_or_404
from app.services.stage_events import format_count

# processing_state -> the state of each step of the conversion run
_RUN_STATE = {
    "queued": StageState.PENDING,
    "retrying": StageState.PENDING,      # will run again
    "processing": StageState.ACTIVE,
    "processed": StageState.DONE,
    "partially_processed": StageState.DONE,
    "needs_review": StageState.DONE,
    "completed": StageState.DONE,
    "failed": StageState.FAILED,
}


def _get_latest_job(db: Session, *, document_id: UUID, organization_id: UUID) -> SyncJob | None:
    """The latest attempt (D21). URL jobs have no document_id (D19), so they never match."""
    return db.execute(
        select(SyncJob)
        .where(SyncJob.document_id == document_id, SyncJob.organization_id == organization_id)
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _get_stage_rows(db: Session, *, job_id: UUID) -> dict[str, SyncJobStage]:
    """One row per stage at most: (sync_job_id, stage_key) is unique."""
    rows = db.execute(select(SyncJobStage).where(SyncJobStage.sync_job_id == job_id)).scalars()
    return {row.stage_key.value: row for row in rows}


def get_processing(db: Session, *, document_id: UUID, organization_id: UUID) -> dict:
    document = get_document_or_404(db, document_id=document_id, organization_id=organization_id)
    # One query: the current conversion's figures and the three counts.
    chunks = (select(func.count()).select_from(DocumentChunk)
              .where(DocumentChunk.organization_id == organization_id, DocumentChunk.document_id == document_id)
              .scalar_subquery())
    evidence = (select(func.count()).select_from(Evidence)
                .where(Evidence.organization_id == organization_id, Evidence.document_id == document_id)
                .scalar_subquery())
    claims = (select(func.count(distinct(ClaimEvidence.claim_id))).select_from(ClaimEvidence)
              .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
              .where(ClaimEvidence.organization_id == organization_id, Evidence.document_id == document_id)
              .scalar_subquery())
    row = db.execute(
        select(DocumentConversion.id, DocumentConversion.processing_state, DocumentConversion.page_count,
               DocumentConversion.table_count, DocumentConversion.image_count, DocumentConversion.ocr_block_count,
               chunks.label("chunks"), evidence.label("evidence"), claims.label("claims"))
        .select_from(Document)
        .outerjoin(DocumentConversion, and_(DocumentConversion.document_id == Document.id, DocumentConversion.is_current))
        .where(Document.id == document_id)
    ).one()

    has_conversion = row.id is not None
    if has_conversion:
        received = StageState.DONE              # the upload request stored the file and its conversion row
    elif document.extraction_status == DocumentExtractionStatus.FAILED:
        received = StageState.FAILED
    else:
        received = StageState.PENDING
    run = _RUN_STATE.get(row.processing_state, StageState.PENDING) if has_conversion else StageState.PENDING
    finished = run == StageState.DONE

    def stage(key, state, detail=None):
        return {"key": key, "state": state, "detail": detail}

    stages = [
        stage("upload", received),
        stage("security", received),         # validated inside the upload request: the same signal
        stage("conversion", run),
        stage("structure", run, format_count(row.table_count, "table", "tables") if finished else None),
        stage("ocr", run, format_count(row.ocr_block_count, "OCR block", "OCR blocks") if finished else None),
        # Done once chunks exist. No "active": extraction_status is also set by ingestion itself.
        stage("chunking", StageState.DONE if row.chunks else StageState.PENDING),
        stage("evidence", StageState.NOT_TRACKED),
        stage("knowledge", StageState.NOT_TRACKED),
    ]

    job = _get_latest_job(db, document_id=document_id, organization_id=organization_id)
    if job is not None:
        rows = _get_stage_rows(db, job_id=job.id)
        stages = [stage(s["key"], StageState(rows[s["key"]].state.value), rows[s["key"]].detail)
                  if s["key"] in rows else s for s in stages]

    return {
        "document_id": document_id,
        "document_title": document.title,
        "mime_type": document.mime_type,   # the screen maps it to a short label such as DOCX (D27)
        "stages": stages,
        "metrics": {
            "pages": row.page_count, "tables": row.table_count if has_conversion else None,
            "images": row.image_count if has_conversion else None,
            "ocr_blocks": row.ocr_block_count if has_conversion else None,
            "chunks": row.chunks, "claims": row.claims, "evidence": row.evidence,
        },
        "job": None if job is None else {
            "id": job.id, "status": job.status.value, "attempts": job.attempts, "created_at": job.created_at,
            "started_at": job.started_at, "completed_at": job.completed_at,
        },
    }
