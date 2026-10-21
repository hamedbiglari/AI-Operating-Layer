"""
Carrying out an approved chat research request — master prompt §13.6 steps 5-9 (ADR-130).

ADR-128 stopped at step 4: the chat could detect a gap, propose a scope and record a decision, but
nothing ever acted on that decision. A request sat at `approved` for ever. This is the part that
acts on it.

WHAT THIS IS NOT
It is not a research engine. The project already has one — `research_projects` → `research_tasks`,
executed by whatever `ResearchProvider` is registered — and §18 is explicit that there must be
exactly one and that a missing provider is reported, never simulated. So an approved request creates
a real project and task through the existing services and hands them to the existing worker. If no
provider is configured, the task honestly ends `NOT_CONFIGURED`, and so does the request: the user is
told that no research could be performed, which is the truth, instead of being left with a request
that silently goes nowhere.

THE FIVE STEPS
  5. perform      a ResearchProject + ResearchTask are created and executed
  6. register     whatever sources the task produced are counted on the request
  7. reconcile    the question is retrieved again, against the knowledge base as it now stands
  8. re-answer    only if something actually changed, a new assistant turn answers the question
  9. report       the request ends `completed` or `failed`, and a failure always says why

Step 8 is deliberately conditional. Re-answering an unchanged knowledge base would spend a model
call to produce the same answer and present it as progress. When nothing was added, the request
completes and says so — `sources_added = 0`, no re-answer, and the original answer stands.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationResearchRequest
from app.models.enums import (
    ResearchMode, ResearchProjectStatus, ResearchReferenceType, ResearchTaskStatus,
)
from app.models.research_task import ResearchTask
from app.models.research_task_reference import ResearchTaskReference
from app.models.user import User
from app.services import chat_service, research_project_service, research_task_service
from app.services.audit import record_audit_log

logger = logging.getLogger(__name__)

# One task per request. The chat asks one question; splitting it into a plan of sub-tasks is what the
# research planner is for, and a chat gap does not carry enough intent to justify one.
TASK_TYPE = "chat_knowledge_gap"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fail(db: Session, req: ConversationResearchRequest, reason: str) -> ConversationResearchRequest:
    """A failure always carries its reason — the schema refuses `failed` with a null `error`."""
    req.state = "failed"
    req.error = reason
    record_audit_log(db, organization_id=req.organization_id, user_id=req.user_id,
                     action="chat.research_failed", resource_type="conversation_research_request",
                     resource_id=req.id, new_value={"state": req.state, "error": reason[:500]})
    db.commit()
    db.refresh(req)
    return req


def _source_count(db: Session, task: ResearchTask) -> int:
    """How many sources this task actually put in front of the organisation. Counted from the
    reference rows the research layer wrote, not from the provider's own summary."""
    rows = db.execute(
        select(ResearchTaskReference.reference_id).where(
            ResearchTaskReference.research_task_id == task.id,
            ResearchTaskReference.reference_type == ResearchReferenceType.SOURCE,
        )
    ).scalars().all()
    return len({r for r in rows})


def _objective(req: ConversationResearchRequest) -> str:
    terms = ", ".join((req.proposed_scope or {}).get("terms", [])[:12])
    question = " ".join(req.question.split())[:600]
    return (f"Answer a workspace chat question that the knowledge base could not support: {question}"
            + (f"\n\nTerms the chat retrieved on: {terms}" if terms else ""))


def run(db: Session, *, req: ConversationResearchRequest, actor: User | None = None,
        provider=None) -> ConversationResearchRequest:  # noqa: ANN001
    """Carry out one approved request. Safe to call once; a request already past `approved` is left
    alone rather than run twice."""
    if req.state != "approved":
        logger.info("chat research %s is %s, not approved — nothing to run", req.id, req.state)
        return req

    actor_user_id = actor.id if actor is not None else req.user_id
    req.state = "running"
    db.commit()

    # --- step 5: perform, through the one research engine this project has -------------------
    try:
        project = research_project_service.create_research_project(
            db, organization_id=req.organization_id,
            name=f"Chat question: {' '.join(req.question.split())[:80]}",
            objective=_objective(req),
            # `gap_driven` is only honest when a gap was actually recorded — the schema refuses it
            # otherwise. A question with no topic pinned produced no gap row, and the reason the
            # investigation exists is then the user's own question.
            mode=ResearchMode.GAP_DRIVEN if req.knowledge_gap_id else ResearchMode.USER_DRIVEN,
            knowledge_gap_id=req.knowledge_gap_id, actor_user_id=actor_user_id)
        req.research_project_id = project.id
        db.commit()

        research_project_service.transition_research_project(
            db, project=project, new_status=ResearchProjectStatus.ACTIVE, actor_user_id=actor_user_id)

        task = research_task_service.create_research_task(
            db, organization_id=req.organization_id, research_project_id=project.id,
            task_type=TASK_TYPE, query=req.question, actor_user_id=actor_user_id)

        # The task lifecycle is pending -> queued -> running; execution refuses to start from
        # pending, which is what stops two callers racing the same task into RUNNING.
        task = research_task_service.queue_research_task(db, task=task, actor_user_id=actor_user_id)

        task = research_task_service.execute_research_task(
            db, task_id=task.id, organization_id=req.organization_id,
            actor_user_id=actor_user_id, provider=provider)
    except Exception as exc:                       # noqa: BLE001 - the reason is reported, not swallowed
        logger.exception("chat research %s could not be executed", req.id)
        return _fail(db, req, f"Research could not be started: {exc}")

    if task.status != ResearchTaskStatus.COMPLETED:
        # The commonest case in a deployment with no provider configured. The research layer already
        # recorded exactly why; it is repeated here so the chat user sees it without a second lookup.
        reason = (task.result or {}).get("summary") or f"The research task ended {task.status.value}."
        return _fail(db, req, reason)

    # --- step 6: register what it found -------------------------------------------------------
    req.sources_added = _source_count(db, task)
    db.commit()

    # --- step 7 & 8: reconcile, and re-answer only if the knowledge actually changed -----------
    if req.sources_added == 0:
        req.state = "completed"
        record_audit_log(db, organization_id=req.organization_id, user_id=req.user_id,
                         action="chat.research_completed", resource_type="conversation_research_request",
                         resource_id=req.id,
                         new_value={"state": req.state, "sources_added": 0, "reanswered": False})
        db.commit()
        db.refresh(req)
        return req

    convo = db.get(Conversation, req.conversation_id)
    user = db.get(User, req.user_id)
    if convo is None or user is None:
        return _fail(db, req, "The conversation this request belongs to no longer exists.")

    try:
        answer = chat_service.ask(db, convo=convo, user=user, question=req.question)
    except Exception as exc:                       # noqa: BLE001
        logger.exception("chat research %s: re-answer failed", req.id)
        # The research itself succeeded; only the re-answer did not. Both facts are recorded.
        return _fail(db, req, f"Research added {req.sources_added} source(s), but the question could "
                              f"not be answered again: {exc}")

    req.reanswer_message_id = answer.id
    req.state = "completed"
    record_audit_log(db, organization_id=req.organization_id, user_id=req.user_id,
                     action="chat.research_completed", resource_type="conversation_research_request",
                     resource_id=req.id,
                     new_value={"state": req.state, "sources_added": req.sources_added,
                                "reanswered": True, "answer_state": answer.answer_state})
    db.commit()
    db.refresh(req)
    return req


def run_by_id(db: Session, *, request_id: UUID, organization_id: UUID,
              provider=None) -> ConversationResearchRequest | None:  # noqa: ANN001
    """Entry point for the worker, which has an id and a tenant and nothing else."""
    req = db.execute(
        select(ConversationResearchRequest).where(
            ConversationResearchRequest.id == request_id,
            ConversationResearchRequest.organization_id == organization_id)
    ).scalar_one_or_none()
    if req is None:
        logger.warning("chat research %s not found for organization %s", request_id, organization_id)
        return None
    return run(db, req=req, provider=provider)
