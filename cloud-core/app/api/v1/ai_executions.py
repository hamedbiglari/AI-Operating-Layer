"""
AI execution read API (Phase 17). Tenant-scoped, read-only.

There is deliberately NO create/update/delete endpoint: executions are
written only by the shared invocation wrapper, and a terminal execution's
accounting facts (status, tokens, cost, provider) are immutable — no client
may POST a fake execution or PATCH its status or cost.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.enums import ADMIN_ROLES
from app.schemas.ai_execution import AIExecutionRead, to_read
from app.schemas.common import Page, PaginationParams, SortParams
from app.security.dependencies import get_current_user
from app.services import ai_execution_service as service

router = APIRouter(prefix="/ai-executions", tags=["ai-executions"])


def _can_see_cost(user: User) -> bool:
    """Provider (wholesale) cost is admin-only per the billing design; within
    a tenant that is OWNER/ADMIN. No platform-admin role exists in this
    codebase, and none is invented here."""
    return user.role in ADMIN_ROLES


@router.get("", response_model=Page[AIExecutionRead])
def list_ai_executions(
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    status_filter: str | None = Query(default=None, alias="status"),
    provider: str | None = None,
    model: str | None = None,
    parent_type: str | None = None,
    visibility_run_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[AIExecutionRead]:
    items, total = service.list_executions(
        db, organization_id=current_user.organization_id, limit=pagination.limit,
        offset=pagination.offset, status=status_filter, provider=provider, model=model,
        parent_type=parent_type, visibility_run_id=visibility_run_id, sort=sort,
    )
    return Page[AIExecutionRead](items=[to_read(i, can_see_cost=_can_see_cost(current_user)) for i in items],
                                 total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/{execution_id}", response_model=AIExecutionRead)
def get_ai_execution(
    execution_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> AIExecutionRead:
    execution = service.get_execution(db, execution_id=execution_id,
                                      organization_id=current_user.organization_id)
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI execution not found")
    return to_read(execution, can_see_cost=_can_see_cost(current_user))


@router.get("/{execution_id}/chain", response_model=list[AIExecutionRead])
def get_ai_execution_chain(
    execution_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
) -> list[AIExecutionRead]:
    chain = service.execution_chain(db, execution_id=execution_id,
                                    organization_id=current_user.organization_id)
    if not chain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI execution not found")
    return [to_read(e, can_see_cost=_can_see_cost(current_user)) for e in chain]
