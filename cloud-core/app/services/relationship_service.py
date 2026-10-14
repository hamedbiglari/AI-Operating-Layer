"""
Relationship (graph edge) service.

`_NODE_TYPE_TO_MODEL` is the resolver for the polymorphic subject/object
references described in app/models/relationship.py: given a
GraphNodeType tag and a UUID, look the row up in the RIGHT table AND
verify it belongs to the caller's organization, using the same
`get_tenant_scoped_or_404` every other tenant-owned lookup uses. This is
what stops a relationship from being created pointing at another
organization's Entity or Knowledge Object.
"""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.entity import Entity
from app.models.enums import GraphNodeType, RelationshipStatus
from app.models.knowledge_object import KnowledgeObject
from app.models.relationship import Relationship
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log

_NODE_TYPE_TO_MODEL = {
    GraphNodeType.ENTITY: Entity,
    GraphNodeType.KNOWLEDGE_OBJECT: KnowledgeObject,
}


def _resolve_and_check_node(db: Session, *, node_type: GraphNodeType, node_id: UUID, organization_id: UUID) -> None:
    model = _NODE_TYPE_TO_MODEL[node_type]
    get_tenant_scoped_or_404(
        db, model, node_id, organization_id=organization_id,
        not_found_message=f"{node_type.value} not found",
    )


def list_relationships(
    db: Session,
    *,
    organization_id: UUID,
    subject_id: UUID | None,
    object_id: UUID | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Relationship], int]:
    base = select(Relationship).where(Relationship.organization_id == organization_id)
    if subject_id:
        base = base.where(Relationship.subject_id == subject_id)
    if object_id:
        base = base.where(Relationship.object_id == object_id)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, Relationship, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def list_relationships_for_node(
    db: Session,
    *,
    organization_id: UUID,
    node_id: UUID,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Relationship], int]:
    """All relationships where node_id is EITHER the subject or the
    object, as a single query with an OR condition.

    Fixes a Phase 2 review finding: the previous implementation behind
    GET /knowledge/{id}/relations ran `list_relationships` twice (once
    filtered by subject_id, once by object_id), applied limit/offset to
    EACH call independently, and only merged + deduplicated the two
    already-paginated pages afterwards in Python. That broke both the
    total count (subject_total + object_total double-counts a
    self-loop edge where subject_id == object_id == node_id) and the
    limit/offset contract (page 2 of the combined set has no relation to
    "skip `offset` rows of the true combined set"). A single OR query
    counted and paginated once has neither problem: a self-loop row
    matches the OR condition once and is returned once, and
    limit/offset apply to the real result set.
    """
    base = select(Relationship).where(
        Relationship.organization_id == organization_id,
        or_(Relationship.subject_id == node_id, Relationship.object_id == node_id),
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, Relationship, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_relationship_or_404(db: Session, *, relationship_id: UUID, organization_id: UUID) -> Relationship:
    return get_tenant_scoped_or_404(
        db,
        Relationship,
        relationship_id,
        organization_id=organization_id,
        not_found_message="Relationship not found",
    )


def create_relationship(
    db: Session,
    *,
    organization_id: UUID,
    subject_type: GraphNodeType,
    subject_id: UUID,
    predicate: str,
    object_type: GraphNodeType,
    object_id: UUID,
    confidence: float | None,
    source_id: UUID | None,
    actor_user_id: UUID,
) -> Relationship:
    _resolve_and_check_node(db, node_type=subject_type, node_id=subject_id, organization_id=organization_id)
    _resolve_and_check_node(db, node_type=object_type, node_id=object_id, organization_id=organization_id)

    edge = Relationship(
        organization_id=organization_id,
        subject_type=subject_type,
        subject_id=subject_id,
        predicate=predicate,
        object_type=object_type,
        object_id=object_id,
        confidence=confidence,
        source_id=source_id,
        status=RelationshipStatus.ACTIVE,
    )
    db.add(edge)
    db.flush()

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="relationship.created",
        resource_type="relationship",
        resource_id=edge.id,
        new_value={"predicate": edge.predicate, "subject_id": str(edge.subject_id), "object_id": str(edge.object_id)},
    )
    db.commit()
    db.refresh(edge)
    return edge


def update_relationship(
    db: Session,
    *,
    relationship: Relationship,
    confidence: float | None,
    status: RelationshipStatus | None,
    actor_user_id: UUID,
) -> Relationship:
    old_value = {"status": relationship.status.value}

    if confidence is not None:
        relationship.confidence = confidence
    if status is not None:
        relationship.status = status

    db.flush()
    record_audit_log(
        db,
        organization_id=relationship.organization_id,
        user_id=actor_user_id,
        action="relationship.updated",
        resource_type="relationship",
        resource_id=relationship.id,
        old_value=old_value,
        new_value={"status": relationship.status.value},
    )
    db.commit()
    db.refresh(relationship)
    return relationship
