"""
Authenticated knowledge chat API (master prompt §13, §14; ADR-128).

    GET    /chat/config                                 what this user may do, before the UI renders
    GET    /chat/conversations                          mine only; search, state filter, sorting
    POST   /chat/conversations                          new thread
    GET    /chat/conversations/{id}
    PATCH  /chat/conversations/{id}                     rename
    POST   /chat/conversations/{id}/archive · /unarchive
    DELETE /chat/conversations/{id}
    GET    /chat/conversations/{id}/messages            the turns, with their citations
    POST   /chat/conversations/{id}/messages            ask a question -> one answer with a state
    POST   /chat/messages/{id}/retry                    ask the same question again as a new turn
    POST   /chat/messages/{id}/feedback                 helpful / not_helpful / wrong / incomplete
    GET    /chat/research-requests                      gaps the chat proposed researching
    POST   /chat/research-requests/{id}/approve · /reject · /cancel
    GET    /chat/settings                               owner/admin (§14)
    PUT    /chat/settings                               owner/admin (§14)

EVERY ROUTE REQUIRES A SESSION. There is no anonymous mode and no fail-open branch: the dependency
`get_current_user` rejects a missing or invalid token with 401 before any handler body runs, and the
per-user routes then resolve the conversation by (organization, user) so another user's id answers 404.
Authorisation is decided here in application code, never by the model.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.conversation import (
    CONVERSATION_STATES, FEEDBACK_RATINGS, RESEARCH_MODES, Conversation, ConversationMessage,
    ConversationResearchRequest,
)
from app.models.enums import ADMIN_ROLES
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import chat_service as svc
from app.services.audit import record_audit_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])
Reader = Depends(get_current_user)
Admin = Depends(require_roles(*ADMIN_ROLES))


# ---------------------------------------------------------------------- bodies
class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    knowledge_object_id: UUID | None = None
    language: str | None = Field(default=None, max_length=10)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    attachments: list[UUID] | None = None


class FeedbackIn(BaseModel):
    rating: str = Field(pattern="^(" + "|".join(FEEDBACK_RATINGS) + ")$")
    note: str | None = Field(default=None, max_length=2000)


class SettingsIn(BaseModel):
    enabled: bool | None = None
    allowed_knowledge_object_ids: list[UUID] | None = None
    online_research: str | None = Field(default=None, pattern="^(" + "|".join(RESEARCH_MODES) + ")$")
    routing_policy_id: UUID | None = None
    max_output_tokens: int | None = Field(default=None, ge=128, le=32000)
    context_token_budget: int | None = Field(default=None, ge=2000, le=400000)
    show_citations: bool | None = None
    collect_feedback: bool | None = None
    retention_days: int | None = Field(default=None, ge=1)
    messages_per_user_per_day: int | None = Field(default=None, ge=1)
    max_cost_per_message: float | None = Field(default=None, gt=0)

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------- config
@router.get("/config")
def config(user: User = Reader, db: Session = Depends(get_db)) -> dict:
    """Asked before the chat UI renders. A disabled chat answers 200 with `enabled: false` rather than an
    error, so the page can show the real reason instead of a failure."""
    return svc.config_for(db, user)


# ---------------------------------------------------------------- conversations
@router.get("/conversations", response_model=Page[dict])
def list_conversations(p: PaginationParams = Depends(), sort: SortParams = Depends(),
                       state: str | None = Query(default=None), q: str | None = Query(default=None, max_length=200),
                       user: User = Reader, db: Session = Depends(get_db)) -> Page[dict]:
    if state is not None and state not in CONVERSATION_STATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"state must be one of: {', '.join(CONVERSATION_STATES)}")
    where = [Conversation.organization_id == user.organization_id, Conversation.user_id == user.id]
    if state:
        where.append(Conversation.state == state)
    if q:
        # Title match, or any turn in the thread containing the text — conversation search (§13.2).
        like = f"%{q}%"
        inner = select(ConversationMessage.conversation_id).where(ConversationMessage.text.ilike(like))
        where.append(or_(Conversation.title.ilike(like), Conversation.id.in_(inner)))
    total = db.execute(select(func.count()).select_from(Conversation).where(*where)).scalar_one()
    stmt = apply_sort(select(Conversation).where(*where), Conversation, sort, "last_message_at")
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.conversation_out(c) for c in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(body: ConversationCreate, user: User = Reader,
                        db: Session = Depends(get_db)) -> dict:
    convo = svc.create_conversation(db, organization_id=user.organization_id, user=user, title=body.title,
                                    knowledge_object_id=body.knowledge_object_id, language=body.language)
    return svc.conversation_out(convo)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.conversation_out(_mine(db, user, conversation_id))


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: UUID, body: ConversationPatch, user: User = Reader,
                        db: Session = Depends(get_db)) -> dict:
    convo = _mine(db, user, conversation_id)
    convo.title = body.title or None
    db.commit()
    db.refresh(convo)
    return svc.conversation_out(convo)


@router.post("/conversations/{conversation_id}/archive")
def archive_conversation(conversation_id: UUID, user: User = Reader,
                         db: Session = Depends(get_db)) -> dict:
    convo = _mine(db, user, conversation_id)
    convo.state, convo.archived_at = "archived", datetime.now(timezone.utc)
    db.commit()
    db.refresh(convo)
    return svc.conversation_out(convo)


@router.post("/conversations/{conversation_id}/unarchive")
def unarchive_conversation(conversation_id: UUID, user: User = Reader,
                           db: Session = Depends(get_db)) -> dict:
    convo = _mine(db, user, conversation_id)
    convo.state, convo.archived_at = "active", None
    db.commit()
    db.refresh(convo)
    return svc.conversation_out(convo)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: UUID, user: User = Reader,
                        db: Session = Depends(get_db)) -> Response:
    convo = _mine(db, user, conversation_id)
    record_audit_log(db, organization_id=user.organization_id, user_id=user.id,
                     action="chat.conversation_deleted", resource_type="conversation",
                     resource_id=convo.id, old_value={"message_count": convo.message_count})
    db.delete(convo)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------------- messages
@router.get("/conversations/{conversation_id}/messages", response_model=Page[dict])
def list_messages(conversation_id: UUID, p: PaginationParams = Depends(), sort: SortParams = Depends(),
                  user: User = Reader, db: Session = Depends(get_db)) -> Page[dict]:
    convo = _mine(db, user, conversation_id)
    where = [ConversationMessage.conversation_id == convo.id]
    total = db.execute(select(func.count()).select_from(ConversationMessage).where(*where)).scalar_one()
    # Reading order by default: a transcript read out of order is not a transcript. `sort` can still ask
    # for the newest first, which is how a long thread loads its tail.
    stmt = apply_sort(select(ConversationMessage).where(*where), ConversationMessage, sort, "position",
                      default_dir=SortDirection.ASC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    show = svc.get_settings(db, user.organization_id)
    with_citations = show is None or show.show_citations
    return Page(items=[svc.message_out(db, m, with_citations=with_citations) for m in rows],
                total=total, limit=p.limit, offset=p.offset)


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
def ask(conversation_id: UUID, body: Ask, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    convo = _mine(db, user, conversation_id)
    if convo.state == "archived":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This conversation is archived. Unarchive it to continue.")
    msg = svc.ask(db, convo=convo, user=user, question=body.question, attachments=body.attachments)
    return svc.message_out(db, msg)


@router.post("/messages/{message_id}/retry", status_code=status.HTTP_201_CREATED)
def retry(message_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    msg = _my_message(db, user, message_id)
    convo = _mine(db, user, msg.conversation_id)
    return svc.message_out(db, svc.retry(db, convo=convo, user=user, message=msg))


@router.post("/messages/{message_id}/feedback", status_code=status.HTTP_201_CREATED)
def feedback(message_id: UUID, body: FeedbackIn, user: User = Reader,
             db: Session = Depends(get_db)) -> dict:
    msg = _my_message(db, user, message_id)
    convo = _mine(db, user, msg.conversation_id)
    row = svc.give_feedback(db, convo=convo, user=user, message=msg, rating=body.rating, note=body.note)
    return {"message_id": str(msg.id), "rating": row.rating, "note": row.note,
            "created_at": row.created_at}


# ----------------------------------------------------------- research requests
@router.get("/research-requests", response_model=Page[dict])
def list_research_requests(p: PaginationParams = Depends(), sort: SortParams = Depends(),
                           state: str | None = Query(default=None), user: User = Reader,
                           db: Session = Depends(get_db)) -> Page[dict]:
    where = [ConversationResearchRequest.organization_id == user.organization_id,
             ConversationResearchRequest.user_id == user.id]
    if state:
        where.append(ConversationResearchRequest.state == state)
    total = db.execute(select(func.count()).select_from(ConversationResearchRequest)
                       .where(*where)).scalar_one()
    stmt = apply_sort(select(ConversationResearchRequest).where(*where), ConversationResearchRequest,
                      sort, "created_at")
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.request_out(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/research-requests/{request_id}/approve")
def approve_research(request_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    req = svc.get_research_request(db, organization_id=user.organization_id, user_id=user.id,
                                  request_id=request_id)
    return svc.request_out(svc.decide_research_request(db, req=req, user=user, approve=True))


@router.post("/research-requests/{request_id}/reject")
def reject_research(request_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    req = svc.get_research_request(db, organization_id=user.organization_id, user_id=user.id,
                                  request_id=request_id)
    return svc.request_out(svc.decide_research_request(db, req=req, user=user, approve=False))


@router.post("/research-requests/{request_id}/cancel")
def cancel_research(request_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    req = svc.get_research_request(db, organization_id=user.organization_id, user_id=user.id,
                                  request_id=request_id)
    return svc.request_out(svc.cancel_research_request(db, req=req, user=user))


# -------------------------------------------------------------- settings (§14)
@router.get("/settings")
def get_chat_settings(user: User = Admin, db: Session = Depends(get_db)) -> dict:
    return svc.settings_out(svc.get_settings(db, user.organization_id))


@router.put("/settings")
def put_chat_settings(body: SettingsIn, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No settings were supplied.")
    row = svc.save_settings(db, organization_id=user.organization_id, actor=user, fields=fields)
    return svc.settings_out(row)


# --------------------------------------------------------------------- helpers
def _mine(db: Session, user: User, conversation_id: UUID) -> Conversation:
    return svc.get_conversation(db, organization_id=user.organization_id, user_id=user.id,
                               conversation_id=conversation_id)


def _my_message(db: Session, user: User, message_id: UUID) -> ConversationMessage:
    """Resolved through the owning conversation, so a message id belonging to another user — or to another
    tenant — is a 404 and never a readable row."""
    msg = db.execute(select(ConversationMessage).join(
        Conversation, Conversation.id == ConversationMessage.conversation_id).where(
        ConversationMessage.id == message_id,
        ConversationMessage.organization_id == user.organization_id,
        Conversation.user_id == user.id)).scalar_one_or_none()
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found.")
    return msg
