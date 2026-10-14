"""Entity endpoints - tenant-scoped, attached to a Knowledge Object."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entity import Entity
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.entity import EntityCreate, EntityRead, EntityUpdate
from app.security.dependencies import get_current_user, require_roles
from app.services import entity_service

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("", response_model=Page[EntityRead])
def list_entities(
    knowledge_object_id: UUID | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[EntityRead]:
    items, total = entity_service.list_entities(
        db,
        organization_id=current_user.organization_id,
        knowledge_object_id=knowledge_object_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("", response_model=EntityRead, status_code=201)
def create_entity(
    payload: EntityCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Entity:
    return entity_service.create_entity(
        db,
        organization_id=current_user.organization_id,
        knowledge_object_id=payload.knowledge_object_id,
        entity_type=payload.entity_type,
        canonical_name=payload.canonical_name,
        aliases=payload.aliases,
        external_ids=payload.external_ids,
        language=payload.language,
        actor_user_id=current_user.id,
    )


@router.get("/{entity_id}", response_model=EntityRead)
def get_entity(
    entity_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Entity:
    return entity_service.get_entity_or_404(
        db, entity_id=entity_id, organization_id=current_user.organization_id
    )


@router.patch("/{entity_id}", response_model=EntityRead)
def update_entity(
    entity_id: UUID,
    payload: EntityUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Entity:
    entity = entity_service.get_entity_or_404(
        db, entity_id=entity_id, organization_id=current_user.organization_id
    )
    return entity_service.update_entity(
        db,
        entity=entity,
        entity_type=payload.entity_type,
        canonical_name=payload.canonical_name,
        aliases=payload.aliases,
        external_ids=payload.external_ids,
        language=payload.language,
        actor_user_id=current_user.id,
    )
