"""
Research Engine endpoints (master spec section 22/50).

POST   /research/projects
GET    /research/projects
GET    /research/projects/{id}
PATCH  /research/projects/{id}
POST   /research/projects/{id}/transition   -- the only path that changes status
POST   /research/tasks
GET    /research/tasks
GET    /research/tasks/{id}
PATCH  /research/tasks/{id}                 -- only while still PENDING
POST   /research/tasks/{id}/queue           -- PENDING -> QUEUED, dispatches the worker job
POST   /research/tasks/{id}/cancel
GET    /research/tasks/{id}/references      -- the task's provenance trail

Reads are open to any authenticated user in the organization; writes
require KNOWLEDGE_EDITOR_ROLES — the same split every other Phase 2-4
resource in this API uses, and section 16's "at minimum distinguish
read / create / update / execute-manage" is satisfied by that same
split (queueing/cancelling a task is a write, same role gate as
creating one) rather than a separate permission tier, since no prior
phase in this codebase distinguishes "write" from "execute" more
finely than that.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import (
    KNOWLEDGE_EDITOR_ROLES,
    ResearchMode,
    ResearchProjectStatus,
    ResearchTaskStatus,
)
from app.models.research_project import ResearchProject
from app.models.research_task import ResearchTask
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.research_project import (
    ResearchProjectCreate,
    ResearchProjectRead,
    ResearchProjectTransitionRequest,
    ResearchProjectUpdate,
)
from app.schemas.research_task import ResearchTaskCreate, ResearchTaskRead, ResearchTaskUpdate
from app.schemas.research_task_reference import ResearchTaskReferenceRead
from app.security.dependencies import get_current_user, require_roles
from app.services import research_project_service, research_task_service

router = APIRouter(prefix="/research", tags=["research"])


# --- Research Projects ------------------------------------------------


@router.get("/projects", response_model=Page[ResearchProjectRead])
def list_research_projects(
    mode: ResearchMode | None = Query(default=None),
    status_filter: ResearchProjectStatus | None = Query(default=None, alias="status"),
    knowledge_gap_id: UUID | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ResearchProjectRead]:
    items, total = research_project_service.list_research_projects(
        db,
        organization_id=current_user.organization_id,
        mode=mode,
        status=status_filter,
        knowledge_gap_id=knowledge_gap_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/projects", response_model=ResearchProjectRead, status_code=status.HTTP_201_CREATED)
def create_research_project(
    payload: ResearchProjectCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ResearchProject:
    return research_project_service.create_research_project(
        db,
        organization_id=current_user.organization_id,
        name=payload.name,
        objective=payload.objective,
        mode=payload.mode,
        knowledge_gap_id=payload.knowledge_gap_id,
        actor_user_id=current_user.id,
    )


@router.get("/projects/{project_id}", response_model=ResearchProjectRead)
def get_research_project(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchProject:
    return research_project_service.get_research_project_or_404(
        db, project_id=project_id, organization_id=current_user.organization_id
    )


@router.patch("/projects/{project_id}", response_model=ResearchProjectRead)
def update_research_project(
    project_id: UUID,
    payload: ResearchProjectUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ResearchProject:
    project = research_project_service.get_research_project_or_404(
        db, project_id=project_id, organization_id=current_user.organization_id
    )
    return research_project_service.update_research_project(
        db, project=project, name=payload.name, objective=payload.objective, actor_user_id=current_user.id,
    )


@router.post("/projects/{project_id}/transition", response_model=ResearchProjectRead)
def transition_research_project(
    project_id: UUID,
    payload: ResearchProjectTransitionRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ResearchProject:
    project = research_project_service.get_research_project_or_404(
        db, project_id=project_id, organization_id=current_user.organization_id
    )
    try:
        return research_project_service.transition_research_project(
            db, project=project, new_status=payload.status, actor_user_id=current_user.id,
        )
    except research_project_service.InvalidResearchProjectTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None


# --- Research Tasks -----------------------------------------------------


@router.get("/tasks", response_model=Page[ResearchTaskRead])
def list_research_tasks(
    research_project_id: UUID | None = Query(default=None),
    status_filter: ResearchTaskStatus | None = Query(default=None, alias="status"),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ResearchTaskRead]:
    items, total = research_task_service.list_research_tasks(
        db,
        organization_id=current_user.organization_id,
        research_project_id=research_project_id,
        status=status_filter,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/tasks", response_model=ResearchTaskRead, status_code=status.HTTP_201_CREATED)
def create_research_task(
    payload: ResearchTaskCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ResearchTask:
    return research_task_service.create_research_task(
        db,
        organization_id=current_user.organization_id,
        research_project_id=payload.research_project_id,
        task_type=payload.task_type,
        query=payload.query,
        actor_user_id=current_user.id,
    )


@router.get("/tasks/{task_id}", response_model=ResearchTaskRead)
def get_research_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResearchTask:
    return research_task_service.get_research_task_or_404(
        db, task_id=task_id, organization_id=current_user.organization_id
    )


@router.patch("/tasks/{task_id}", response_model=ResearchTaskRead)
def update_research_task(
    task_id: UUID,
    payload: ResearchTaskUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ResearchTask:
    task = research_task_service.get_research_task_or_404(
        db, task_id=task_id, organization_id=current_user.organization_id
    )
    try:
        return research_task_service.update_research_task(
            db, task=task, task_type=payload.task_type, query=payload.query, actor_user_id=current_user.id,
        )
    except research_task_service.ResearchTaskNotEditableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None


@router.post("/tasks/{task_id}/queue", response_model=ResearchTaskRead)
def queue_research_task(
    task_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ResearchTask:
    """Transitions PENDING -> QUEUED and dispatches the Celery job that
    will actually run the configured ResearchProvider. With no real
    provider configured (see app/integrations/research/base.py), the
    dispatched job will honestly complete with the task in FAILED
    status and `result.outcome_status == "not_configured"` — this is
    expected, documented behavior, not a bug in the queue action
    itself."""
    task = research_task_service.get_research_task_or_404(
        db, task_id=task_id, organization_id=current_user.organization_id
    )
    try:
        task = research_task_service.queue_research_task(db, task=task, actor_user_id=current_user.id)
    except research_task_service.InvalidResearchTaskTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None

    from app.workers.tasks import execute_research_task_job

    execute_research_task_job.delay(str(task.id), str(current_user.organization_id))
    db.refresh(task)
    return task


@router.post("/tasks/{task_id}/cancel", response_model=ResearchTaskRead)
def cancel_research_task(
    task_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ResearchTask:
    task = research_task_service.get_research_task_or_404(
        db, task_id=task_id, organization_id=current_user.organization_id
    )
    try:
        return research_task_service.cancel_research_task(db, task=task, actor_user_id=current_user.id)
    except research_task_service.InvalidResearchTaskTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None


@router.get("/tasks/{task_id}/references", response_model=Page[ResearchTaskReferenceRead])
def list_research_task_references(
    task_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ResearchTaskReferenceRead]:
    items, total = research_task_service.list_task_references(
        db,
        task_id=task_id,
        organization_id=current_user.organization_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)
