"""Dashboard summary: every number behind the Dashboard's count cards, in one read.

Each count uses the same filter as the list endpoint that shows those rows, so
a card and the list it links to cannot disagree. There is no composite score
(ADR-024): "needs human review" stays two numbers for the page to show as such.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.document_artifact import DocumentConversion
from app.models.enums import ClaimEvidenceStrength, EvidenceStatus, GapStatus
from app.models.evidence import Evidence
from app.models.knowledge_gap import KnowledgeGap
from app.models.source import Source

# processing_state (ADR-122) split into disjoint groups. A partial or flagged
# extraction is never a success: it is counted under review only.
IN_PROGRESS_STATES = ("queued", "processing", "retrying")
SUCCEEDED_STATES = ("processed", "completed")
FAILED_STATES = ("failed",)
REVIEW_STATES = ("partially_processed", "needs_review")

RECENT_SOURCES_DAYS = 30


def get_summary(db: Session, *, organization_id: UUID) -> dict:
    now = datetime.now(timezone.utc)

    sources_total, sources_recent = db.execute(
        select(func.count(), func.count().filter(Source.created_at >= now - timedelta(days=RECENT_SOURCES_DAYS)))
        .where(Source.organization_id == organization_id)
    ).one()

    # In-flight attempts count whether or not they are current: a reprocess runs
    # as a non-current row until it succeeds. Outcomes count the current
    # conversion only, i.e. one per document.
    conv = DocumentConversion
    current = conv.is_current.is_(True)
    in_progress, oldest_queued_at, succeeded, failed, to_review = db.execute(
        select(
            func.count().filter(conv.processing_state.in_(IN_PROGRESS_STATES)),
            func.min(conv.created_at).filter(conv.processing_state == "queued"),
            func.count().filter(current, conv.processing_state.in_(SUCCEEDED_STATES)),
            func.count().filter(current, conv.processing_state.in_(FAILED_STATES)),
            func.count().filter(current, conv.processing_state.in_(REVIEW_STATES)),
        ).where(conv.organization_id == organization_id)
    ).one()

    def count(model, *criteria) -> int:
        return db.execute(
            select(func.count()).select_from(model).where(model.organization_id == organization_id, *criteria)
        ).scalar_one()

    return {
        "sources": {"total": sources_total, "added_last_30d": sources_recent},
        "conversions": {
            "in_progress": in_progress,
            "oldest_queued_at": oldest_queued_at,
            "succeeded": succeeded,
            "failed": failed,
        },
        "review": {
            "conversions": to_review,
            "evidence_pending": count(Evidence, Evidence.status == EvidenceStatus.PENDING_REVIEW),
            "claims_conflicting": count(Claim, Claim.evidence_strength == ClaimEvidenceStrength.CONFLICTING),
            "gaps_open": count(KnowledgeGap, KnowledgeGap.status == GapStatus.OPEN),
        },
        # Not tracked anywhere yet. null means "no data", never zero.
        "duplicate_decisions": None,
        "generated_at": now,
    }
