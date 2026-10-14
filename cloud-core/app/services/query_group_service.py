"""
QueryGroup service (master spec section 25).

Knowledge Need is deliberately NOT its own persisted model — it is a
JUDGMENT computed at read time by `assess_knowledge_need`, not a
database row. A QueryGroup is a curated bucket of queries (persisted,
section-25-defined); a Knowledge Need is the answer to "is this bucket
of demand adequately served by existing Knowledge/Evidence right now?"
— a question whose answer can change every time a new Claim or Evidence
row is added, without anyone touching the QueryGroup itself. Treating
QueryGroup as if it WERE the Knowledge Need would mean every group
automatically implies a content gap, which is false — a group can be
fully, adequately covered already.

If `assess_knowledge_need` concludes a gap exists, THIS module never
creates one itself — per the approved design decision, gap creation
stays exclusively on the EXISTING `knowledge_gap_service.create_knowledge_gap`
(Phase 2) / `POST /knowledge-gaps` endpoint. Phase 6's job here ends at
surfacing the judgment; acting on it is a separate, existing, human-
triggered action.
"""

from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.claim import Claim
from app.models.entity import Entity
from app.models.enums import ClaimEvidenceStrength, IntentType, QueryPriority
from app.models.query_group import QueryGroup
from app.models.query_group_membership import QueryGroupMembership
from app.schemas.query_group import KnowledgeNeedAssessment
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.entity_service import get_entity_or_404
from app.services.query_service import get_query_or_404

# Claim evidence_strength values counted as "adequately evidenced" for
# the purposes of this assessment — a documented, revisitable
# threshold, same spirit as claim_evidence_service's own conflict
# threshold constant.
_ADEQUATE_EVIDENCE_STRENGTHS = frozenset({ClaimEvidenceStrength.MODERATE, ClaimEvidenceStrength.STRONG})


def list_query_groups(
    db: Session,
    *,
    organization_id: UUID,
    primary_intent: IntentType | None,
    priority: QueryPriority | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[QueryGroup], int]:
    base = select(QueryGroup).where(QueryGroup.organization_id == organization_id)
    if primary_intent:
        base = base.where(QueryGroup.primary_intent == primary_intent)
    if priority:
        base = base.where(QueryGroup.priority == priority)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(apply_sort(base, QueryGroup, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_query_group_or_404(db: Session, *, group_id: UUID, organization_id: UUID) -> QueryGroup:
    return get_tenant_scoped_or_404(
        db, QueryGroup, group_id, organization_id=organization_id, not_found_message="Query group not found"
    )


def create_query_group(
    db: Session,
    *,
    organization_id: UUID,
    name: str,
    primary_intent: IntentType,
    target_entity_id: UUID | None,
    priority: QueryPriority,
    actor_user_id: UUID,
) -> QueryGroup:
    if target_entity_id is not None:
        get_entity_or_404(db, entity_id=target_entity_id, organization_id=organization_id)

    group = QueryGroup(
        organization_id=organization_id,
        name=name,
        primary_intent=primary_intent,
        target_entity_id=target_entity_id,
        priority=priority,
    )
    db.add(group)
    db.flush()
    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="query_group.created",
        resource_type="query_group",
        resource_id=group.id,
        new_value={"name": group.name, "primary_intent": group.primary_intent.value},
    )
    db.commit()
    db.refresh(group)
    return group


def update_query_group(
    db: Session,
    *,
    group: QueryGroup,
    name: str | None,
    priority: QueryPriority | None,
    actor_user_id: UUID,
) -> QueryGroup:
    old_value = {"name": group.name, "priority": group.priority.value}

    if name is not None:
        group.name = name
    if priority is not None:
        group.priority = priority

    db.flush()
    record_audit_log(
        db,
        organization_id=group.organization_id,
        user_id=actor_user_id,
        action="query_group.updated",
        resource_type="query_group",
        resource_id=group.id,
        old_value=old_value,
        new_value={"name": group.name, "priority": group.priority.value},
    )
    db.commit()
    db.refresh(group)
    return group


def add_query_to_group(
    db: Session, *, group: QueryGroup, query_id: UUID, actor_user_id: UUID
) -> QueryGroupMembership:
    get_query_or_404(db, query_id=query_id, organization_id=group.organization_id)

    membership = QueryGroupMembership(
        organization_id=group.organization_id, query_group_id=group.id, query_id=query_id
    )
    db.add(membership)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="This query is already a member of this query group.",
        ) from None
    record_audit_log(
        db,
        organization_id=group.organization_id,
        user_id=actor_user_id,
        action="query_group.query_added",
        resource_type="query_group_membership",
        resource_id=membership.id,
        new_value={"query_group_id": str(group.id), "query_id": str(query_id)},
    )
    db.commit()
    db.refresh(membership)
    return membership


def remove_query_from_group(db: Session, *, group: QueryGroup, membership: QueryGroupMembership, actor_user_id: UUID) -> None:
    record_audit_log(
        db,
        organization_id=group.organization_id,
        user_id=actor_user_id,
        action="query_group.query_removed",
        resource_type="query_group_membership",
        resource_id=membership.id,
        old_value={"query_group_id": str(group.id), "query_id": str(membership.query_id)},
    )
    db.delete(membership)
    db.commit()


def list_group_members(
    db: Session, *, group_id: UUID, organization_id: UUID, limit: int, offset: int, sort: SortParams | None = None
) -> tuple[list[QueryGroupMembership], int]:
    get_query_group_or_404(db, group_id=group_id, organization_id=organization_id)
    base = select(QueryGroupMembership).where(
        QueryGroupMembership.query_group_id == group_id,
        QueryGroupMembership.organization_id == organization_id,
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(apply_sort(base, QueryGroupMembership, sort, "created_at", SortDirection.ASC).limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_membership_or_404(db: Session, *, membership_id: UUID, organization_id: UUID) -> QueryGroupMembership:
    return get_tenant_scoped_or_404(
        db, QueryGroupMembership, membership_id, organization_id=organization_id,
        not_found_message="Query group membership not found",
    )


def assess_knowledge_need(db: Session, *, group: QueryGroup) -> KnowledgeNeedAssessment:
    """Documented heuristic (see module docstring) — not a final
    scientific-adequacy algorithm, same spirit as
    claim_evidence_service.recompute_claim_aggregate's own heuristic."""
    if group.target_entity_id is None:
        return KnowledgeNeedAssessment(
            query_group_id=group.id,
            has_target_entity=False,
            knowledge_object_id=None,
            claim_count=0,
            adequately_evidenced_claim_count=0,
            is_gap_worthy=False,
            reason="No target_entity_id set on this query group; coverage cannot be assessed.",
        )

    entity = db.get(Entity, group.target_entity_id)
    knowledge_object_id = entity.knowledge_object_id if entity else None

    claims = db.execute(
        select(Claim).where(
            Claim.organization_id == group.organization_id,
            Claim.subject_entity_id == group.target_entity_id,
        )
    ).scalars().all()

    if not claims:
        return KnowledgeNeedAssessment(
            query_group_id=group.id,
            has_target_entity=True,
            knowledge_object_id=knowledge_object_id,
            claim_count=0,
            adequately_evidenced_claim_count=0,
            is_gap_worthy=True,
            reason="No claims exist yet for this query group's target entity.",
        )

    adequate = [c for c in claims if c.evidence_strength in _ADEQUATE_EVIDENCE_STRENGTHS]
    if not adequate:
        return KnowledgeNeedAssessment(
            query_group_id=group.id,
            has_target_entity=True,
            knowledge_object_id=knowledge_object_id,
            claim_count=len(claims),
            adequately_evidenced_claim_count=0,
            is_gap_worthy=True,
            reason=(
                f"{len(claims)} claim(s) exist for this entity, but none have "
                "moderate-or-stronger evidence backing them yet."
            ),
        )

    return KnowledgeNeedAssessment(
        query_group_id=group.id,
        has_target_entity=True,
        knowledge_object_id=knowledge_object_id,
        claim_count=len(claims),
        adequately_evidenced_claim_count=len(adequate),
        is_gap_worthy=False,
        reason=f"{len(adequate)} of {len(claims)} claim(s) for this entity have adequate evidence backing.",
    )
