"""Knowledge overview: knowledge objects with the counts behind the Knowledge
list, filtered, ordered and paged in one read.

Filters come from knowledge_service.filtered_knowledge_objects, so this and
GET /knowledge cannot disagree on what a search or filter matches. Counts are
three grouped queries over the organization (claims, linked evidence, open
gaps), joined to the objects, so ordering by "action needed" and hiding
finished objects happen in SQL across all pages, never per page in the
browser. There is no composite score (ADR-024): "action needed" is an order
of plain counts.
"""

from uuid import UUID

from sqlalchemy import and_, distinct, func, not_, select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.enums import ClaimEvidenceStrength, EvidenceStatus, GapStatus, KnowledgeObjectStatus
from app.models.evidence import Evidence
from app.models.knowledge_gap import KnowledgeGap
from app.models.knowledge_object import KnowledgeObject
from app.schemas.knowledge_overview import KnowledgeOverviewSort
from app.services.knowledge_service import filtered_knowledge_objects

COUNT_NAMES = ("sources", "claims", "claims_conflicting", "evidence", "evidence_verified",
               "evidence_pending_review", "gaps_open")


def get_overview(
    db: Session,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
    search: str | None = None,
    object_type: str | None = None,
    status: KnowledgeObjectStatus | None = None,
    sort: KnowledgeOverviewSort = KnowledgeOverviewSort.ACTION_NEEDED,
    include_finished: bool = False,
    object_id: UUID | None = None,
) -> tuple[list[dict], int]:
    claims = (
        select(
            Claim.knowledge_object_id.label("ko"),
            func.count().label("claims"),
            func.count().filter(Claim.evidence_strength == ClaimEvidenceStrength.CONFLICTING).label("claims_conflicting"),
        )
        .where(Claim.organization_id == organization_id)
        .group_by(Claim.knowledge_object_id)
        .subquery()
    )
    evidence = (
        select(
            Claim.knowledge_object_id.label("ko"),
            func.count(distinct(Evidence.source_id)).label("sources"),
            func.count(distinct(Evidence.id)).label("evidence"),
            func.count(distinct(Evidence.id)).filter(Evidence.status == EvidenceStatus.VERIFIED).label("evidence_verified"),
            func.count(distinct(Evidence.id))
            .filter(Evidence.status == EvidenceStatus.PENDING_REVIEW)
            .label("evidence_pending_review"),
        )
        .select_from(Claim)
        .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
        .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
        .where(Claim.organization_id == organization_id, Evidence.organization_id == organization_id)
        .group_by(Claim.knowledge_object_id)
        .subquery()
    )
    gaps = (
        select(KnowledgeGap.knowledge_object_id.label("ko"), func.count().label("gaps_open"))
        .where(KnowledgeGap.organization_id == organization_id, KnowledgeGap.status == GapStatus.OPEN)
        .group_by(KnowledgeGap.knowledge_object_id)
        .subquery()
    )

    col = {
        "claims": func.coalesce(claims.c.claims, 0),
        "claims_conflicting": func.coalesce(claims.c.claims_conflicting, 0),
        "sources": func.coalesce(evidence.c.sources, 0),
        "evidence": func.coalesce(evidence.c.evidence, 0),
        "evidence_verified": func.coalesce(evidence.c.evidence_verified, 0),
        "evidence_pending_review": func.coalesce(evidence.c.evidence_pending_review, 0),
        "gaps_open": func.coalesce(gaps.c.gaps_open, 0),
    }
    finished = and_(
        KnowledgeObject.status == KnowledgeObjectStatus.PUBLISHED,
        col["claims_conflicting"] == 0,
        col["gaps_open"] == 0,
        col["evidence_pending_review"] == 0,
    )

    query = (
        filtered_knowledge_objects(organization_id=organization_id, search=search, object_type=object_type, status=status)
        .outerjoin(claims, claims.c.ko == KnowledgeObject.id)
        .outerjoin(evidence, evidence.c.ko == KnowledgeObject.id)
        .outerjoin(gaps, gaps.c.ko == KnowledgeObject.id)
        .add_columns(*(col[name].label(name) for name in COUNT_NAMES), finished.label("finished"))
    )
    if object_id is not None:
        # One object's row for its detail page, whatever its status.
        query = query.where(KnowledgeObject.id == object_id)
    else:
        # Archived objects are not part of the overview list at all.
        query = query.where(KnowledgeObject.status != KnowledgeObjectStatus.ARCHIVED)
        if not include_finished:
            query = query.where(not_(finished))

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()

    if sort == KnowledgeOverviewSort.NAME:
        order = (KnowledgeObject.canonical_name.asc(),)
    elif sort == KnowledgeOverviewSort.UPDATED:
        order = (KnowledgeObject.updated_at.desc(),)
    else:
        order = (col["claims_conflicting"].desc(), col["gaps_open"].desc(),
                 col["evidence_pending_review"].desc(), KnowledgeObject.updated_at.desc())
    # The id makes the order total, so offset paging never repeats or skips a row.
    rows = db.execute(query.order_by(*order, KnowledgeObject.id).limit(limit).offset(offset)).all()

    items = [
        {"object": row[0], "counts": {name: getattr(row, name) for name in COUNT_NAMES}, "finished": row.finished}
        for row in rows
    ]
    return items, total
