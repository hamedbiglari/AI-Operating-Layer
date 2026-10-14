"""KnowledgeGap service."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import GapPriority, GapRecommendedAction, GapStatus, GapType
from app.models.knowledge_gap import KnowledgeGap
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.knowledge_service import get_knowledge_object_or_404


def list_knowledge_gaps(
    db: Session,
    *,
    organization_id: UUID,
    knowledge_object_id: UUID | None,
    status: GapStatus | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[KnowledgeGap], int]:
    base = select(KnowledgeGap).where(KnowledgeGap.organization_id == organization_id)
    if knowledge_object_id:
        base = base.where(KnowledgeGap.knowledge_object_id == knowledge_object_id)
    if status:
        base = base.where(KnowledgeGap.status == status)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, KnowledgeGap, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_knowledge_gap_or_404(db: Session, *, gap_id: UUID, organization_id: UUID) -> KnowledgeGap:
    return get_tenant_scoped_or_404(
        db, KnowledgeGap, gap_id, organization_id=organization_id, not_found_message="Knowledge gap not found"
    )


def create_knowledge_gap(
    db: Session,
    *,
    organization_id: UUID,
    knowledge_object_id: UUID,
    gap_type: GapType,
    description: str,
    priority: GapPriority,
    recommended_action: GapRecommendedAction | None,
    actor_user_id: UUID,
) -> KnowledgeGap:
    get_knowledge_object_or_404(db, object_id=knowledge_object_id, organization_id=organization_id)

    gap = KnowledgeGap(
        organization_id=organization_id,
        knowledge_object_id=knowledge_object_id,
        gap_type=gap_type,
        description=description,
        priority=priority,
        status=GapStatus.OPEN,
        recommended_action=recommended_action,
    )
    db.add(gap)
    db.flush()

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="knowledge_gap.created",
        resource_type="knowledge_gap",
        resource_id=gap.id,
        new_value={"gap_type": gap.gap_type.value, "priority": gap.priority.value},
    )
    db.commit()
    db.refresh(gap)
    return gap


def update_knowledge_gap(
    db: Session,
    *,
    gap: KnowledgeGap,
    description: str | None,
    priority: GapPriority | None,
    status: GapStatus | None,
    recommended_action: GapRecommendedAction | None,
    actor_user_id: UUID,
) -> KnowledgeGap:
    old_value = {"status": gap.status.value, "priority": gap.priority.value}

    if description is not None:
        gap.description = description
    if priority is not None:
        gap.priority = priority
    if status is not None:
        gap.status = status
    if recommended_action is not None:
        gap.recommended_action = recommended_action

    db.flush()
    record_audit_log(
        db,
        organization_id=gap.organization_id,
        user_id=actor_user_id,
        action="knowledge_gap.updated",
        resource_type="knowledge_gap",
        resource_id=gap.id,
        old_value=old_value,
        new_value={"status": gap.status.value, "priority": gap.priority.value},
    )
    db.commit()
    db.refresh(gap)
    return gap
