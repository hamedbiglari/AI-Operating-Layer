"""KnowledgeGap endpoints - tenant-scoped, attached to a Knowledge Object."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES, GapStatus
from app.models.knowledge_gap import KnowledgeGap
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.knowledge_gap import KnowledgeGapCreate, KnowledgeGapRead, KnowledgeGapUpdate
from app.security.dependencies import get_current_user, require_roles
from app.services import knowledge_gap_service

router = APIRouter(prefix="/knowledge-gaps", tags=["knowledge-gaps"])


@router.get("", response_model=Page[KnowledgeGapRead])
def list_knowledge_gaps(
    knowledge_object_id: UUID | None = Query(default=None),
    status_filter: GapStatus | None = Query(default=None, alias="status"),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[KnowledgeGapRead]:
    items, total = knowledge_gap_service.list_knowledge_gaps(
        db,
        organization_id=current_user.organization_id,
        knowledge_object_id=knowledge_object_id,
        status=status_filter,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("", response_model=KnowledgeGapRead, status_code=status.HTTP_201_CREATED)
def create_knowledge_gap(
    payload: KnowledgeGapCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> KnowledgeGap:
    return knowledge_gap_service.create_knowledge_gap(
        db,
        organization_id=current_user.organization_id,
        knowledge_object_id=payload.knowledge_object_id,
        gap_type=payload.gap_type,
        description=payload.description,
        priority=payload.priority,
        recommended_action=payload.recommended_action,
        actor_user_id=current_user.id,
    )


@router.get("/{gap_id}", response_model=KnowledgeGapRead)
def get_knowledge_gap(
    gap_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeGap:
    return knowledge_gap_service.get_knowledge_gap_or_404(
        db, gap_id=gap_id, organization_id=current_user.organization_id
    )


@router.patch("/{gap_id}", response_model=KnowledgeGapRead)
def update_knowledge_gap(
    gap_id: UUID,
    payload: KnowledgeGapUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> KnowledgeGap:
    gap = knowledge_gap_service.get_knowledge_gap_or_404(
        db, gap_id=gap_id, organization_id=current_user.organization_id
    )
    return knowledge_gap_service.update_knowledge_gap(
        db,
        gap=gap,
        description=payload.description,
        priority=payload.priority,
        status=payload.status,
        recommended_action=payload.recommended_action,
        actor_user_id=current_user.id,
    )
