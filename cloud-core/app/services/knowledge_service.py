"""
Knowledge Object service.

Centerpiece of this module: every meaningful update to a KnowledgeObject
writes an immutable KnowledgeVersion snapshot first (master spec section
21: "diff, audit, rollback, review, publishing status"). This is not
optional/best-effort — `update_knowledge_object` and `publish` both go
through `_snapshot_and_bump_version`, so there is no code path that
mutates a KnowledgeObject without leaving a version behind.
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import KnowledgeObjectStatus
from app.models.knowledge_object import KnowledgeObject
from app.models.knowledge_version import KnowledgeVersion
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.slugs import slugify


class SlugConflictError(Exception):
    pass


def _serialize_snapshot(obj: KnowledgeObject) -> dict:
    return {
        "canonical_name": obj.canonical_name,
        "slug": obj.slug,
        "object_type": obj.object_type,
        "description": obj.description,
        "status": obj.status.value,
        "language": obj.language,
        "confidence": float(obj.confidence) if obj.confidence is not None else None,
        "public_visibility": obj.public_visibility,
        "ai_visibility": obj.ai_visibility,
        "version": obj.version,
    }


def _snapshot_and_bump_version(
    db: Session, *, obj: KnowledgeObject, change_summary: str | None, actor_user_id: UUID
) -> None:
    obj.version += 1
    db.flush()
    version_row = KnowledgeVersion(
        organization_id=obj.organization_id,
        knowledge_object_id=obj.id,
        version=obj.version,
        snapshot=_serialize_snapshot(obj),
        change_summary=change_summary,
        created_by=actor_user_id,
    )
    db.add(version_row)


def list_knowledge_objects(
    db: Session,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
    search: str | None = None,
    object_type: str | None = None,
    status: KnowledgeObjectStatus | None = None,
    sort: SortParams | None = None,
) -> tuple[list[KnowledgeObject], int]:
    base = select(KnowledgeObject).where(KnowledgeObject.organization_id == organization_id)
    if search:
        pattern = f"%{search}%"
        base = base.where(
            KnowledgeObject.canonical_name.ilike(pattern) | KnowledgeObject.description.ilike(pattern)
        )
    if object_type:
        base = base.where(KnowledgeObject.object_type == object_type)
    if status:
        base = base.where(KnowledgeObject.status == status)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, KnowledgeObject, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_knowledge_object_or_404(db: Session, *, object_id: UUID, organization_id: UUID) -> KnowledgeObject:
    return get_tenant_scoped_or_404(
        db,
        KnowledgeObject,
        object_id,
        organization_id=organization_id,
        not_found_message="Knowledge object not found",
    )


def create_knowledge_object(
    db: Session,
    *,
    organization_id: UUID,
    canonical_name: str,
    slug: str | None,
    object_type: str,
    description: str | None,
    language: str,
    confidence: float | None,
    actor_user_id: UUID,
) -> KnowledgeObject:
    base_slug = slugify(slug or canonical_name)
    candidate = base_slug
    suffix = 1
    while db.execute(
        select(KnowledgeObject).where(
            KnowledgeObject.organization_id == organization_id, KnowledgeObject.slug == candidate
        )
    ).scalar_one_or_none():
        suffix += 1
        candidate = f"{base_slug}-{suffix}"

    obj = KnowledgeObject(
        organization_id=organization_id,
        canonical_name=canonical_name,
        slug=candidate,
        object_type=object_type,
        description=description,
        status=KnowledgeObjectStatus.DRAFT,
        language=language,
        confidence=confidence,
    )
    db.add(obj)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise SlugConflictError(candidate) from exc

    # Version 1 is the creation snapshot itself.
    version_row = KnowledgeVersion(
        organization_id=obj.organization_id,
        knowledge_object_id=obj.id,
        version=obj.version,
        snapshot=_serialize_snapshot(obj),
        change_summary="Created",
        created_by=actor_user_id,
    )
    db.add(version_row)

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="knowledge_object.created",
        resource_type="knowledge_object",
        resource_id=obj.id,
        new_value={"canonical_name": obj.canonical_name, "slug": obj.slug},
    )
    db.commit()
    db.refresh(obj)
    return obj


def update_knowledge_object(
    db: Session,
    *,
    obj: KnowledgeObject,
    canonical_name: str | None,
    description: str | None,
    status: KnowledgeObjectStatus | None,
    language: str | None,
    confidence: float | None,
    public_visibility: bool | None,
    ai_visibility: bool | None,
    change_summary: str | None,
    actor_user_id: UUID,
    category_id: UUID | None = None,
) -> KnowledgeObject:
    old_value = _serialize_snapshot(obj)

    if canonical_name is not None:
        obj.canonical_name = canonical_name
    if description is not None:
        obj.description = description
    if status is not None:
        obj.status = status
    if language is not None:
        obj.language = language
    if confidence is not None:
        obj.confidence = confidence
    if public_visibility is not None:
        obj.public_visibility = public_visibility
    if ai_visibility is not None:
        obj.ai_visibility = ai_visibility
    if category_id is not None:
        # ADR-114: the category must belong to this tenant, or the topic could inherit a foreign schema
        from app.models.knowledge_schema import Category

        cat = db.execute(
            select(Category).where(Category.id == category_id, Category.organization_id == obj.organization_id)
        ).scalar_one_or_none()
        if cat is None:
            raise HTTPException(status_code=404, detail="Category not found.")
        obj.category_id = category_id

    _snapshot_and_bump_version(
        db, obj=obj, change_summary=change_summary, actor_user_id=actor_user_id
    )

    record_audit_log(
        db,
        organization_id=obj.organization_id,
        user_id=actor_user_id,
        action="knowledge_object.updated",
        resource_type="knowledge_object",
        resource_id=obj.id,
        old_value=old_value,
        new_value=_serialize_snapshot(obj),
    )
    db.commit()
    db.refresh(obj)
    return obj


def publish_knowledge_object(db: Session, *, obj: KnowledgeObject, actor_user_id: UUID) -> KnowledgeObject:
    return update_knowledge_object(
        db,
        obj=obj,
        canonical_name=None,
        description=None,
        status=KnowledgeObjectStatus.PUBLISHED,
        language=None,
        confidence=None,
        public_visibility=True,
        ai_visibility=None,
        change_summary="Published",
        actor_user_id=actor_user_id,
    )


def archive_knowledge_object(db: Session, *, obj: KnowledgeObject, actor_user_id: UUID) -> KnowledgeObject:
    return update_knowledge_object(
        db,
        obj=obj,
        canonical_name=None,
        description=None,
        status=KnowledgeObjectStatus.ARCHIVED,
        language=None,
        confidence=None,
        public_visibility=False,
        ai_visibility=False,
        change_summary="Archived",
        actor_user_id=actor_user_id,
    )


def list_knowledge_versions(
    db: Session, *, knowledge_object_id: UUID, organization_id: UUID
) -> list[KnowledgeVersion]:
    rows = (
        db.execute(
            select(KnowledgeVersion)
            .where(
                KnowledgeVersion.knowledge_object_id == knowledge_object_id,
                KnowledgeVersion.organization_id == organization_id,
            )
            .order_by(KnowledgeVersion.version.desc())
        )
        .scalars()
        .all()
    )
    return list(rows)
