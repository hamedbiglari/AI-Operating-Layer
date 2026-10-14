"""Relationship (graph edge) endpoints - tenant-scoped."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.relationship import Relationship
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.relationship import RelationshipCreate, RelationshipRead, RelationshipUpdate
from app.security.dependencies import get_current_user, require_roles
from app.services import relationship_service

router = APIRouter(prefix="/relationships", tags=["relationships"])


@router.get("", response_model=Page[RelationshipRead])
def list_relationships(
    subject_id: UUID | None = Query(default=None),
    object_id: UUID | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[RelationshipRead]:
    items, total = relationship_service.list_relationships(
        db,
        organization_id=current_user.organization_id,
        subject_id=subject_id,
        object_id=object_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("", response_model=RelationshipRead, status_code=status.HTTP_201_CREATED)
def create_relationship(
    payload: RelationshipCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Relationship:
    return relationship_service.create_relationship(
        db,
        organization_id=current_user.organization_id,
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        predicate=payload.predicate,
        object_type=payload.object_type,
        object_id=payload.object_id,
        confidence=payload.confidence,
        source_id=payload.source_id,
        actor_user_id=current_user.id,
    )


@router.get("/{relationship_id}", response_model=RelationshipRead)
def get_relationship(
    relationship_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Relationship:
    return relationship_service.get_relationship_or_404(
        db, relationship_id=relationship_id, organization_id=current_user.organization_id
    )


@router.patch("/{relationship_id}", response_model=RelationshipRead)
def update_relationship(
    relationship_id: UUID,
    payload: RelationshipUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Relationship:
    edge = relationship_service.get_relationship_or_404(
        db, relationship_id=relationship_id, organization_id=current_user.organization_id
    )
    return relationship_service.update_relationship(
        db, relationship=edge, confidence=payload.confidence, status=payload.status, actor_user_id=current_user.id
    )
