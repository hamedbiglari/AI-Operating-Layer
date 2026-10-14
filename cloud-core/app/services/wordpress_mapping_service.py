"""
WordPress mapping service — adapter state only (ADR-038).

**Idempotency is structural, not procedural.** `upsert_mapping` matches
on the database's own unique constraint
(`site_id, object_type, object_id`). A webhook delivered five times
produces one row because the constraint says so, not because this
function remembered to check. The `IntegrityError` path exists for the
genuine concurrent-duplicate race, where two workers upsert the same
mapping simultaneously — one wins, the other re-reads rather than
erroring.

**Core truth is never mutated here.** This module writes exactly two
tables: `wordpress_mappings`, and nothing else. It cannot publish a
product, verify evidence, or change a knowledge object — those are
Core decisions that no adapter scope grants access to. A merchant who
publishes a post in WordPress has not thereby published anything in
Core.

The polymorphic `object_id` is resolved and tenant-checked against the
real owning table before any write, using the existing domain getters
— the adapter never asserts that an object exists.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import MappedObjectType, SyncStatus
from app.models.knowledge_object import KnowledgeObject
from app.models.product import Product
from app.models.wordpress_mapping import WordPressMapping
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log

_OBJECT_TYPE_TO_MODEL = {
    MappedObjectType.KNOWLEDGE_OBJECT: KnowledgeObject,
    MappedObjectType.PRODUCT: Product,
}


def _resolve_object(db: Session, *, object_type: MappedObjectType, object_id: UUID, organization_id: UUID) -> None:
    """Same resolver discipline as relationship_service /
    research_task_service / trust: the pointer is verified against the
    real table in the caller's own tenant, never trusted."""
    model = _OBJECT_TYPE_TO_MODEL[object_type]
    get_tenant_scoped_or_404(
        db, model, object_id, organization_id=organization_id,
        not_found_message=f"{object_type.value} not found",
    )


def upsert_mapping(
    db: Session,
    *,
    organization_id: UUID,
    site_id: UUID,
    installation_id: UUID | None,
    object_type: MappedObjectType,
    object_id: UUID,
    wordpress_post_id: int,
    wordpress_post_type: str | None,
    wordpress_url: str | None,
    remote_updated_at: datetime | None,
    actor_user_id: UUID | None,
) -> tuple[WordPressMapping, bool]:
    """Returns (mapping, created). Idempotent — see module docstring."""
    _resolve_object(db, object_type=object_type, object_id=object_id, organization_id=organization_id)

    existing = db.execute(
        select(WordPressMapping).where(
            WordPressMapping.organization_id == organization_id,
            WordPressMapping.site_id == site_id,
            WordPressMapping.object_type == object_type,
            WordPressMapping.object_id == object_id,
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing is not None:
        # A repeat delivery of the same post id is a no-op that still
        # refreshes sync state. A DIFFERENT post id for the same object
        # is a genuine conflict: WordPress is claiming this Core object
        # now lives at a different post. That is not silently accepted -
        # overwriting would lose the record of where it used to be.
        if existing.wordpress_post_id != wordpress_post_id:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=(
                    f"This {object_type.value} is already mapped to WordPress post "
                    f"{existing.wordpress_post_id} on this site. Delete the existing mapping "
                    "before remapping it to a different post."
                ),
            )
        existing.wordpress_post_type = wordpress_post_type or existing.wordpress_post_type
        existing.wordpress_url = wordpress_url or existing.wordpress_url
        existing.remote_updated_at = remote_updated_at or existing.remote_updated_at
        existing.sync_status = SyncStatus.SYNCED
        existing.last_synced_at = now
        existing.installation_id = installation_id or existing.installation_id
        db.commit()
        db.refresh(existing)
        return existing, False

    mapping = WordPressMapping(
        organization_id=organization_id,
        site_id=site_id,
        installation_id=installation_id,
        object_type=object_type,
        object_id=object_id,
        wordpress_post_id=wordpress_post_id,
        wordpress_post_type=wordpress_post_type,
        wordpress_url=wordpress_url,
        remote_updated_at=remote_updated_at,
        sync_status=SyncStatus.SYNCED,
        last_synced_at=now,
    )
    db.add(mapping)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        # Concurrent duplicate (two workers, same event). The row the
        # other writer created is the correct answer.
        concurrent = db.execute(
            select(WordPressMapping).where(
                WordPressMapping.organization_id == organization_id,
                WordPressMapping.site_id == site_id,
                WordPressMapping.object_type == object_type,
                WordPressMapping.object_id == object_id,
            )
        ).scalar_one_or_none()
        if concurrent is not None:
            return concurrent, False
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="This WordPress post is already mapped to a different object on this site.",
        ) from None

    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="wordpress_mapping.created", resource_type="wordpress_mapping", resource_id=mapping.id,
        new_value={
            "object_type": object_type.value, "object_id": str(object_id),
            "wordpress_post_id": wordpress_post_id,
        },
    )
    db.commit()
    db.refresh(mapping)
    return mapping, True


def list_mappings(
    db: Session, *, organization_id: UUID, site_id: UUID | None, object_type: MappedObjectType | None,
    sync_status: SyncStatus | None, limit: int, offset: int,
    sort: SortParams | None = None,
) -> tuple[list[WordPressMapping], int]:
    base = select(WordPressMapping).where(WordPressMapping.organization_id == organization_id)
    if site_id:
        base = base.where(WordPressMapping.site_id == site_id)
    if object_type:
        base = base.where(WordPressMapping.object_type == object_type)
    if sync_status:
        base = base.where(WordPressMapping.sync_status == sync_status)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        apply_sort(base, WordPressMapping, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)
    ).scalars().all()
    return list(rows), total


def get_mapping_or_404(db: Session, *, mapping_id: UUID, organization_id: UUID) -> WordPressMapping:
    return get_tenant_scoped_or_404(
        db, WordPressMapping, mapping_id, organization_id=organization_id,
        not_found_message="Mapping not found",
    )


def delete_mapping(db: Session, *, mapping: WordPressMapping, actor_user_id: UUID | None) -> None:
    record_audit_log(
        db, organization_id=mapping.organization_id, user_id=actor_user_id,
        action="wordpress_mapping.deleted", resource_type="wordpress_mapping", resource_id=mapping.id,
        old_value={"object_id": str(mapping.object_id), "wordpress_post_id": mapping.wordpress_post_id},
    )
    db.delete(mapping)
    db.commit()
