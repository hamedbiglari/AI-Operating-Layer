"""
The Processing view of one document (Step 7C-1): its pipeline as far as the
backend records it, and what it has produced so far.

There is no per-stage record. Conversion, structure detection and OCR are one
run (ingestion_service.orchestrator.run) and share its processing_state; the
count each produced is the stage's detail, never its state, because "0 tables"
is a finished stage. Evidence extraction and knowledge contribution have no
stage data at all and are reported as not tracked rather than guessed.
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
from app.schemas.document import StageState
from app.services.document_service import get_document_or_404

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

    return {
        "document_id": document_id,
        "stages": [
            stage("upload", received),
            stage("security", received),         # validated inside the upload request: the same signal
            stage("conversion", run),
            stage("structure", run, f"{row.table_count} tables" if finished else None),
            stage("ocr", run, f"{row.ocr_block_count} OCR blocks" if finished else None),
            # Done once chunks exist. No "active": extraction_status is also set by ingestion itself.
            stage("chunking", StageState.DONE if row.chunks else StageState.PENDING),
            stage("evidence", StageState.NOT_TRACKED),
            stage("knowledge", StageState.NOT_TRACKED),
        ],
        "metrics": {
            "pages": row.page_count, "tables": row.table_count if has_conversion else None,
            "images": row.image_count if has_conversion else None,
            "ocr_blocks": row.ocr_block_count if has_conversion else None,
            "chunks": row.chunks, "claims": row.claims, "evidence": row.evidence,
        },
    }
