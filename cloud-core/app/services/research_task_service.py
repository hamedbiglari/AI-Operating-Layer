"""
ResearchTask service.

Tenant isolation is the two-hop pattern established for Document
(source_id) and Evidence (source_id/document_id) in earlier phases:
`research_project_id` must belong to the caller's org (via
research_project_service.get_research_project_or_404) before a Task can
be created under it — "a task must never be able to escape the
organization of its ResearchProject" (master spec section 7), enforced
here at the service layer AND, structurally, via the FK itself only
ever pointing at a real project row.

`execute_research_task` is the "worker execution foundation" (section
17): it runs the configured ResearchProvider, maps its
ResearchOutcomeStatus onto ResearchTaskStatus, persists any references
it reported (each resolved and tenant-checked exactly like
research_task_service._resolve_reference does for CREATE), and leaves a
clear audit trail (started / completed / failed). It is deliberately
plain, synchronous, DB-agnostic-of-caller code — app/workers/
research_tasks.py wraps it in a Celery task; nothing here assumes it is
called from a worker versus called directly (same "the function doesn't
assume synchronous execution" principle Phase 3 established for
document_chunk_service.process_document).
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.integrations.research.base import ResearchOutcomeStatus, ResearchProvider
from app.integrations.research.base import get_research_provider as _default_get_research_provider
from app.models.claim import Claim
from app.models.document import Document
from app.models.enums import ResearchReferenceRole, ResearchReferenceType, ResearchTaskStatus
from app.models.evidence import Evidence
from app.models.knowledge_gap import KnowledgeGap
from app.models.knowledge_object import KnowledgeObject
from app.models.research_task import ResearchTask
from app.models.research_task_reference import ResearchTaskReference
from app.models.source import Source
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.research_project_service import get_research_project_or_404


class InvalidResearchTaskTransitionError(Exception):
    """Raised when a requested status transition is not in
    _VALID_TRANSITIONS for the task's current status."""


class ResearchTaskNotEditableError(Exception):
    """Raised when a plain field edit is attempted on a task that is no
    longer PENDING (see ResearchTaskUpdate's docstring)."""


# The literal lifecycle master spec section 17 describes, plus one
# escape hatch (CANCELLED) — see ResearchTaskStatus's docstring.
_VALID_TRANSITIONS: dict[ResearchTaskStatus, frozenset[ResearchTaskStatus]] = {
    ResearchTaskStatus.PENDING: frozenset({ResearchTaskStatus.QUEUED, ResearchTaskStatus.CANCELLED}),
    ResearchTaskStatus.QUEUED: frozenset({ResearchTaskStatus.RUNNING, ResearchTaskStatus.CANCELLED}),
    ResearchTaskStatus.RUNNING: frozenset(
        {ResearchTaskStatus.COMPLETED, ResearchTaskStatus.FAILED, ResearchTaskStatus.CANCELLED}
    ),
    ResearchTaskStatus.COMPLETED: frozenset(),
    ResearchTaskStatus.FAILED: frozenset(),
    ResearchTaskStatus.CANCELLED: frozenset(),
}

# Polymorphic resolver for ResearchTaskReference.reference_id, the same
# technique relationship_service.py's _NODE_TYPE_TO_MODEL uses for
# Relationship's subject/object.
_REFERENCE_TYPE_TO_MODEL = {
    ResearchReferenceType.SOURCE: Source,
    ResearchReferenceType.DOCUMENT: Document,
    ResearchReferenceType.EVIDENCE: Evidence,
    ResearchReferenceType.CLAIM: Claim,
    ResearchReferenceType.KNOWLEDGE_OBJECT: KnowledgeObject,
    ResearchReferenceType.KNOWLEDGE_GAP: KnowledgeGap,
}

_OUTCOME_TO_TASK_STATUS = {
    ResearchOutcomeStatus.RESULT_FOUND: ResearchTaskStatus.COMPLETED,
    ResearchOutcomeStatus.NOT_CONFIGURED: ResearchTaskStatus.FAILED,
    ResearchOutcomeStatus.PROVIDER_FAILED: ResearchTaskStatus.FAILED,
    ResearchOutcomeStatus.NO_RESULT_FOUND: ResearchTaskStatus.FAILED,
    ResearchOutcomeStatus.RESULT_INACCESSIBLE: ResearchTaskStatus.FAILED,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_reference(db: Session, *, reference_type: ResearchReferenceType, reference_id: UUID, organization_id: UUID) -> None:
    model = _REFERENCE_TYPE_TO_MODEL[reference_type]
    get_tenant_scoped_or_404(
        db, model, reference_id, organization_id=organization_id,
        not_found_message=f"{reference_type.value} not found",
    )


def list_research_tasks(
    db: Session,
    *,
    organization_id: UUID,
    research_project_id: UUID | None,
    status: ResearchTaskStatus | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[ResearchTask], int]:
    base = select(ResearchTask).where(ResearchTask.organization_id == organization_id)
    if research_project_id:
        base = base.where(ResearchTask.research_project_id == research_project_id)
    if status:
        base = base.where(ResearchTask.status == status)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, ResearchTask, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_research_task_or_404(db: Session, *, task_id: UUID, organization_id: UUID) -> ResearchTask:
    return get_tenant_scoped_or_404(
        db, ResearchTask, task_id, organization_id=organization_id, not_found_message="Research task not found"
    )


def create_research_task(
    db: Session,
    *,
    organization_id: UUID,
    research_project_id: UUID,
    task_type: str,
    query: str,
    actor_user_id: UUID,
) -> ResearchTask:
    # Raises 404 if the project doesn't exist or belongs to another
    # organization — this IS the tenant-isolation check for task
    # creation (mirrors entity_service.create_entity's own comment).
    get_research_project_or_404(db, project_id=research_project_id, organization_id=organization_id)

    task = ResearchTask(
        organization_id=organization_id,
        research_project_id=research_project_id,
        task_type=task_type,
        query=query,
        status=ResearchTaskStatus.PENDING,
    )
    db.add(task)
    db.flush()

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="research_task.created",
        resource_type="research_task",
        resource_id=task.id,
        new_value={"task_type": task.task_type, "research_project_id": str(research_project_id)},
    )
    db.commit()
    db.refresh(task)
    return task


def update_research_task(
    db: Session,
    *,
    task: ResearchTask,
    task_type: str | None,
    query: str | None,
    actor_user_id: UUID,
) -> ResearchTask:
    if task.status != ResearchTaskStatus.PENDING:
        raise ResearchTaskNotEditableError(
            f"Cannot edit a research task once it is past PENDING (current status: '{task.status.value}')."
        )

    old_value = {"task_type": task.task_type, "query": task.query}

    if task_type is not None:
        task.task_type = task_type
    if query is not None:
        task.query = query

    db.flush()
    record_audit_log(
        db,
        organization_id=task.organization_id,
        user_id=actor_user_id,
        action="research_task.updated",
        resource_type="research_task",
        resource_id=task.id,
        old_value=old_value,
        new_value={"task_type": task.task_type, "query": task.query},
    )
    db.commit()
    db.refresh(task)
    return task


def _transition(db: Session, *, task: ResearchTask, new_status: ResearchTaskStatus, actor_user_id: UUID | None, action: str) -> ResearchTask:
    allowed = _VALID_TRANSITIONS.get(task.status, frozenset())
    if new_status not in allowed:
        raise InvalidResearchTaskTransitionError(
            f"Cannot transition research task from '{task.status.value}' to '{new_status.value}'. "
            f"Valid transitions from '{task.status.value}': "
            f"{sorted(s.value for s in allowed) or 'none (terminal state)'}."
        )

    old_status = task.status
    task.status = new_status

    db.flush()
    record_audit_log(
        db,
        organization_id=task.organization_id,
        user_id=actor_user_id,
        action=action,
        resource_type="research_task",
        resource_id=task.id,
        old_value={"status": old_status.value},
        new_value={"status": task.status.value},
    )
    db.commit()
    db.refresh(task)
    return task


def queue_research_task(db: Session, *, task: ResearchTask, actor_user_id: UUID) -> ResearchTask:
    """PENDING -> QUEUED. The API layer calls this, then dispatches
    app/workers/research_tasks.py::execute_research_task_job (a Celery
    task) — this function only records the state transition; it does
    NOT run the provider itself (see execute_research_task for that)."""
    return _transition(db, task=task, new_status=ResearchTaskStatus.QUEUED, actor_user_id=actor_user_id, action="research_task.queued")


def cancel_research_task(db: Session, *, task: ResearchTask, actor_user_id: UUID) -> ResearchTask:
    return _transition(db, task=task, new_status=ResearchTaskStatus.CANCELLED, actor_user_id=actor_user_id, action="research_task.cancelled")


def list_task_references(
    db: Session, *, task_id: UUID, organization_id: UUID, limit: int, offset: int, sort: SortParams | None = None
) -> tuple[list[ResearchTaskReference], int]:
    get_research_task_or_404(db, task_id=task_id, organization_id=organization_id)
    base = select(ResearchTaskReference).where(
        ResearchTaskReference.research_task_id == task_id,
        ResearchTaskReference.organization_id == organization_id,
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, ResearchTaskReference, sort, "created_at", SortDirection.ASC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def execute_research_task(
    db: Session,
    *,
    task_id: UUID,
    organization_id: UUID,
    actor_user_id: UUID | None,
    provider: ResearchProvider | None = None,
) -> ResearchTask:
    """Run the configured ResearchProvider for one task and persist the
    outcome. Callable directly (used by the tests below) or via the
    Celery wrapper in app/workers/research_tasks.py — this function
    itself has no dependency on Celery.

    Only PENDING or QUEUED tasks can be executed (RUNNING/terminal
    tasks raise InvalidResearchTaskTransitionError via the same
    transition table every other status change goes through, so a task
    can never be "executed" twice concurrently by two racing callers
    without at least one of them failing the transition check first).

    Section 12's boundary is enforced by NOT enforcing anything here:
    this function only ever writes to `research_tasks` and
    `research_task_references`. It never creates, updates, or reviews a
    Claim or Evidence row itself — a real provider that discovers new
    evidence would call evidence_service.create_evidence directly
    (which defaults status=DRAFT, human_reviewed=False, exactly the
    "discovery is not verification" guarantee section 12 requires), not
    have this function do it on its provider's behalf.
    """
    task = get_tenant_scoped_or_404(
        db, ResearchTask, task_id, organization_id=organization_id, not_found_message="Research task not found"
    )

    task.started_at = _utcnow()
    task = _transition(
        db, task=task, new_status=ResearchTaskStatus.RUNNING, actor_user_id=actor_user_id,
        action="research_task.started",
    )

    active_provider = provider or _default_get_research_provider()
    outcome = active_provider.run(task_type=task.task_type, query=task.query)

    for ref in outcome.references:
        ref_type = ResearchReferenceType(ref.reference_type)
        ref_role = ResearchReferenceRole(ref.role)
        _resolve_reference(db, reference_type=ref_type, reference_id=UUID(ref.reference_id), organization_id=organization_id)
        db.add(
            ResearchTaskReference(
                organization_id=organization_id,
                research_task_id=task.id,
                reference_type=ref_type,
                reference_id=UUID(ref.reference_id),
                role=ref_role,
            )
        )
    if outcome.references:
        db.flush()

    final_status = _OUTCOME_TO_TASK_STATUS[outcome.status]
    task.result = {
        "outcome_status": outcome.status.value,
        "summary": outcome.summary,
        "raw": outcome.raw,
        "reference_count": len(outcome.references),
    }
    task.completed_at = _utcnow()

    task = _transition(
        db, task=task, new_status=final_status, actor_user_id=actor_user_id,
        action="research_task.completed" if final_status == ResearchTaskStatus.COMPLETED else "research_task.failed",
    )
    # result/completed_at were set on `task` above, before this call —
    # _transition's own db.flush()/db.commit() picks up every pending
    # attribute change on the session, not just the status assignment
    # it makes itself, so no separate write is needed for them here.
    return task
