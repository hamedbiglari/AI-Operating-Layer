"""
ResearchProject service.

Tenant isolation for `knowledge_gap_id` (when given) follows the same
pattern as every other cross-resource reference in this codebase:
resolved via `knowledge_gap_service.get_knowledge_gap_or_404`, which
404s if the gap doesn't exist or belongs to another organization —
before the ResearchProject row is ever written.

Status only changes via `transition_research_project`, never via a
plain field edit (see ResearchProjectUpdate's docstring) — the same
review/status split every reviewable resource in this codebase follows.
`_VALID_TRANSITIONS` is the single source of truth for which moves are
allowed; anything else is rejected with a clear error rather than
silently applied or left to a database CHECK constraint to catch.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import ResearchProjectStatus
from app.models.research_project import ResearchProject
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.knowledge_gap_service import get_knowledge_gap_or_404


class InvalidResearchProjectTransitionError(Exception):
    """Raised when a requested status transition is not in
    _VALID_TRANSITIONS for the project's current status."""


# The validated lifecycle — see ResearchProjectStatus's docstring for
# why this is a smaller set than the master spec's full illustrative
# list, and why QUEUED/RUNNING/FAILED don't appear here at all (those
# describe task execution, not the project as a whole).
_VALID_TRANSITIONS: dict[ResearchProjectStatus, frozenset[ResearchProjectStatus]] = {
    ResearchProjectStatus.DRAFT: frozenset({ResearchProjectStatus.ACTIVE, ResearchProjectStatus.CANCELLED}),
    ResearchProjectStatus.ACTIVE: frozenset({ResearchProjectStatus.COMPLETED, ResearchProjectStatus.CANCELLED}),
    ResearchProjectStatus.COMPLETED: frozenset({ResearchProjectStatus.ARCHIVED}),
    ResearchProjectStatus.CANCELLED: frozenset({ResearchProjectStatus.ARCHIVED}),
    ResearchProjectStatus.ARCHIVED: frozenset(),
}


def list_research_projects(
    db: Session,
    *,
    organization_id: UUID,
    mode=None,
    status: ResearchProjectStatus | None = None,
    knowledge_gap_id: UUID | None = None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[ResearchProject], int]:
    base = select(ResearchProject).where(ResearchProject.organization_id == organization_id)
    if mode:
        base = base.where(ResearchProject.mode == mode)
    if status:
        base = base.where(ResearchProject.status == status)
    if knowledge_gap_id:
        base = base.where(ResearchProject.knowledge_gap_id == knowledge_gap_id)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, ResearchProject, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_research_project_or_404(db: Session, *, project_id: UUID, organization_id: UUID) -> ResearchProject:
    return get_tenant_scoped_or_404(
        db, ResearchProject, project_id, organization_id=organization_id,
        not_found_message="Research project not found",
    )


def create_research_project(
    db: Session,
    *,
    organization_id: UUID,
    name: str,
    objective: str,
    mode,
    knowledge_gap_id: UUID | None,
    actor_user_id: UUID,
) -> ResearchProject:
    if knowledge_gap_id is not None:
        get_knowledge_gap_or_404(db, gap_id=knowledge_gap_id, organization_id=organization_id)

    project = ResearchProject(
        organization_id=organization_id,
        name=name,
        objective=objective,
        mode=mode,
        knowledge_gap_id=knowledge_gap_id,
        status=ResearchProjectStatus.DRAFT,
    )
    db.add(project)
    db.flush()

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="research_project.created",
        resource_type="research_project",
        resource_id=project.id,
        new_value={"name": project.name, "mode": project.mode.value, "status": project.status.value},
    )
    db.commit()
    db.refresh(project)
    return project


def update_research_project(
    db: Session,
    *,
    project: ResearchProject,
    name: str | None,
    objective: str | None,
    actor_user_id: UUID,
) -> ResearchProject:
    old_value = {"name": project.name, "objective": project.objective}

    if name is not None:
        project.name = name
    if objective is not None:
        project.objective = objective

    db.flush()
    record_audit_log(
        db,
        organization_id=project.organization_id,
        user_id=actor_user_id,
        action="research_project.updated",
        resource_type="research_project",
        resource_id=project.id,
        old_value=old_value,
        new_value={"name": project.name, "objective": project.objective},
    )
    db.commit()
    db.refresh(project)
    return project


def transition_research_project(
    db: Session,
    *,
    project: ResearchProject,
    new_status: ResearchProjectStatus,
    actor_user_id: UUID,
) -> ResearchProject:
    allowed = _VALID_TRANSITIONS.get(project.status, frozenset())
    if new_status not in allowed:
        raise InvalidResearchProjectTransitionError(
            f"Cannot transition research project from '{project.status.value}' to '{new_status.value}'. "
            f"Valid transitions from '{project.status.value}': "
            f"{sorted(s.value for s in allowed) or 'none (terminal state)'}."
        )

    old_status = project.status
    project.status = new_status

    db.flush()
    record_audit_log(
        db,
        organization_id=project.organization_id,
        user_id=actor_user_id,
        action="research_project.status_changed",
        resource_type="research_project",
        resource_id=project.id,
        old_value={"status": old_status.value},
        new_value={"status": project.status.value},
    )
    db.commit()
    db.refresh(project)
    return project
