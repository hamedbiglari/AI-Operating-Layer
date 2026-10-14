"""
Entity service. Every entity is created under an explicit, tenant-owned
Knowledge Object — `knowledge_service.get_knowledge_object_or_404` is
used to verify that before an Entity row is ever written, so an entity
can never be attached to another organization's Knowledge Object.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.entity import Entity
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.knowledge_service import get_knowledge_object_or_404


def list_entities(
    db: Session,
    *,
    organization_id: UUID,
    knowledge_object_id: UUID | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Entity], int]:
    base = select(Entity).where(Entity.organization_id == organization_id)
    if knowledge_object_id:
        base = base.where(Entity.knowledge_object_id == knowledge_object_id)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, Entity, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)).scalars().all()
    )
    return list(rows), total


def get_entity_or_404(db: Session, *, entity_id: UUID, organization_id: UUID) -> Entity:
    return get_tenant_scoped_or_404(
        db, Entity, entity_id, organization_id=organization_id, not_found_message="Entity not found"
    )


def create_entity(
    db: Session,
    *,
    organization_id: UUID,
    knowledge_object_id: UUID,
    entity_type: str,
    canonical_name: str,
    aliases: list[str] | None,
    external_ids: dict[str, str] | None,
    language: str,
    actor_user_id: UUID,
) -> Entity:
    # Raises 404 if the knowledge object doesn't exist or belongs to
    # another organization — this IS the tenant-isolation check for
    # entity creation, not a separate step.
    get_knowledge_object_or_404(db, object_id=knowledge_object_id, organization_id=organization_id)

    entity = Entity(
        organization_id=organization_id,
        knowledge_object_id=knowledge_object_id,
        entity_type=entity_type,
        canonical_name=canonical_name,
        aliases=aliases,
        external_ids=external_ids,
        language=language,
    )
    db.add(entity)
    db.flush()

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="entity.created",
        resource_type="entity",
        resource_id=entity.id,
        new_value={"canonical_name": entity.canonical_name, "entity_type": entity.entity_type},
    )
    db.commit()
    db.refresh(entity)
    return entity


def update_entity(
    db: Session,
    *,
    entity: Entity,
    entity_type: str | None,
    canonical_name: str | None,
    aliases: list[str] | None,
    external_ids: dict[str, str] | None,
    language: str | None,
    actor_user_id: UUID,
) -> Entity:
    old_value = {"canonical_name": entity.canonical_name, "entity_type": entity.entity_type}

    if entity_type is not None:
        entity.entity_type = entity_type
    if canonical_name is not None:
        entity.canonical_name = canonical_name
    if aliases is not None:
        entity.aliases = aliases
    if external_ids is not None:
        entity.external_ids = external_ids
    if language is not None:
        entity.language = language

    db.flush()
    record_audit_log(
        db,
        organization_id=entity.organization_id,
        user_id=actor_user_id,
        action="entity.updated",
        resource_type="entity",
        resource_id=entity.id,
        old_value=old_value,
        new_value={"canonical_name": entity.canonical_name, "entity_type": entity.entity_type},
    )
    db.commit()
    db.refresh(entity)
    return entity
