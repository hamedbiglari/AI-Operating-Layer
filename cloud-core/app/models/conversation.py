"""
Authenticated knowledge chat (master prompt §13, §14; ADR-128).

A conversation is not knowledge. It is one user's thread of questions and the answers this system was
able to ground in the canonical knowledge base at the time it answered.

    ChatSettings                 one row per organisation: which topics the chat may read, whether online
                                 research is allowed, which routing policy pays for it, retention, limits
    Conversation                 one thread, owned by one user
      └──< ConversationMessage        the turns, in order; an assistant turn carries its answer state,
           │                          the execution that produced it, and its token/cost accounting
           ├──< ConversationCitation  which claim/evidence/source each cited unit resolved to
           └──< ConversationFeedback  the reader's verdict on that answer
    ConversationResearchRequest  a knowledge gap the chat found, the scope it proposed, and the user's
                                 decision — research never starts without one (§13.6)

WHY THE ANSWER STATE IS A COLUMN AND NOT A SCORE (§13.5)
An answer either rests on evidence this system holds, or it does not. `answer_state` records which, so the
reader is never shown a confident paragraph that the knowledge base cannot support. `UNKNOWN`,
`NEEDS_WEB_RESEARCH` and `NEEDS_USER_SOURCE` are successful outcomes of the pipeline, not failures.

PRIVACY (§13.3, §13.8)
A conversation belongs to the user who opened it. No route lists or reads another user's conversation,
even inside the same organisation, and nothing here is promoted into canonical knowledge: that happens
only through the research-request workflow, which creates sources with their own provenance.

Attachments are the existing `documents.id` values, kept as a JSON list on the message rather than in a
sixth table — the same shape `workspace_command_versions.attachments` already uses.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON, TIMESTAMP, Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, SmallInteger,
    String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# §13.5 — every state the pipeline can honestly report. PROCESSING is the state of a turn whose model work
# is still running; it is never shown as an answer.
ANSWER_STATES = ("ANSWERED_FROM_KNOWLEDGE", "PARTIAL_ANSWER", "CONFLICTED", "NEEDS_WEB_RESEARCH",
                 "NEEDS_USER_SOURCE", "UNKNOWN", "PROVIDER_UNAVAILABLE", "PROCESSING")
MESSAGE_ROLES = ("user", "assistant")
# §13.6 — three administrator positions on online research, nothing in between.
RESEARCH_MODES = ("disabled", "ask_every_time", "preauthorized")
REQUEST_STATES = ("pending_approval", "approved", "running", "completed", "cancelled", "rejected", "failed")
FEEDBACK_RATINGS = ("helpful", "not_helpful", "wrong", "incomplete")
CONVERSATION_STATES = ("active", "archived")


def _q(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class ChatSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The dashboard's control surface for the website chat (§14). One row per organisation; absent means
    the chat is off, so a new tenant has no chat until someone turns it on deliberately."""

    __tablename__ = "chat_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_chat_settings_organization"),
        CheckConstraint(f"online_research IN ({_q(RESEARCH_MODES)})", name="online_research"),
        CheckConstraint("max_output_tokens BETWEEN 128 AND 32000", name="max_output_tokens_range"),
        CheckConstraint("context_token_budget BETWEEN 2000 AND 400000", name="context_token_budget_range"),
        CheckConstraint("retention_days IS NULL OR retention_days >= 1", name="retention_days_positive"),
        CheckConstraint("messages_per_user_per_day IS NULL OR messages_per_user_per_day >= 1",
                        name="daily_limit_positive"),
        CheckConstraint("max_cost_per_message IS NULL OR max_cost_per_message > 0", name="cost_cap_positive"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Empty list = every knowledge object in this organisation. A non-empty list is a allow-list of
    # knowledge_objects.id, enforced server-side on every question (§14).
    allowed_knowledge_object_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    online_research: Mapped[str] = mapped_column(String(20), nullable=False, default="ask_every_time")
    routing_policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_routing_policies.id", ondelete="SET NULL"))
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=1200)
    context_token_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=24000)
    show_citations: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    collect_feedback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # NULL = keep conversations until the owner deletes them. A number is enforced by the retention sweep.
    retention_days: Mapped[int | None] = mapped_column(Integer)
    messages_per_user_per_day: Mapped[int | None] = mapped_column(Integer, default=100)
    max_cost_per_message: Mapped[float | None] = mapped_column(Numeric(12, 4))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(f"state IN ({_q(CONVERSATION_STATES)})", name="state"),
        CheckConstraint("message_count >= 0", name="message_count_not_negative"),
        # the listing is always "this user's threads, newest activity first"
        Index("ix_conversations_owner", "organization_id", "user_id", "state", "last_message_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(300))
    # Optional pin: when set, every question in this thread is answered from this topic only.
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="SET NULL"), index=True)
    language: Mapped[str | None] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ConversationMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "position", name="uq_conversation_message_position"),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint(f"role IN ({_q(MESSAGE_ROLES)})", name="role"),
        CheckConstraint(f"answer_state IS NULL OR answer_state IN ({_q(ANSWER_STATES)})", name="answer_state"),
        # A user turn has no answer state; an assistant turn must declare one. This is the schema-level
        # half of §13.5: no answer can be stored without saying what kind of answer it is.
        CheckConstraint("(role = 'user' AND answer_state IS NULL) OR (role = 'assistant' AND answer_state IS NOT NULL)",
                        name="only_assistant_turns_have_an_answer_state"),
        Index("ix_conversation_messages_thread", "conversation_id", "position"),
        # A client that lost the reply to a question re-sends it with the same id and gets the stored
        # turn back instead of a second question (ADR-137). Unique per conversation, NULL for turns that
        # carried none (every turn written before migration 0049).
        Index("uq_conversation_messages_client_request", "conversation_id", "client_request_id", unique=True,
              postgresql_where=text("client_request_id IS NOT NULL")),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    answer_state: Mapped[str | None] = mapped_column(String(30))
    # What the reader is told when the knowledge base could not carry the answer. Separate from `text` so
    # the explanation is never mistaken for a grounded answer.
    limitation: Mapped[str | None] = mapped_column(Text)
    # documents.id values the user attached to this turn
    attachments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # The scope actually searched: topics, terms, how many claims were in scope, what the filters excluded.
    retrieval: Mapped[dict | None] = mapped_column(JSON)
    # Packing and grounding accounting: packs, units offered, units cited, markers the model invented.
    grounding: Mapped[dict | None] = mapped_column(JSON)
    ai_execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_executions.id", ondelete="SET NULL"))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    cost_currency: Mapped[str | None] = mapped_column(String(3))
    stop_reason: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text)
    # The user turn this assistant turn answers — set so a retry knows what to ask again.
    answers_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL"))
    # Client-generated idempotency key, user turns only.
    client_request_id: Mapped[str | None] = mapped_column(String(64))


class ConversationCitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One cited knowledge unit, resolved to the claim and the evidence it rests on. `ordinal` is the
    number shown in this answer, numbered by first appearance — the same first-appearance rule the
    publication resolver uses, but local to one message and never a publication reference number."""

    __tablename__ = "conversation_citations"
    __table_args__ = (
        UniqueConstraint("message_id", "ordinal", name="uq_conversation_citation_ordinal"),
        CheckConstraint("ordinal >= 1", name="ordinal_positive"),
        Index("ix_conversation_citations_message", "message_id", "ordinal"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL"))
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence.id", ondelete="SET NULL"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"))
    # Carried so a citation stays readable after the claim is edited, and so direct/indirect can never be
    # re-rendered as the other one (ADR-101/108).
    directness: Mapped[str | None] = mapped_column(String(20))
    page_number: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[dict | None] = mapped_column(JSON)
    contested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    claim_text: Mapped[str | None] = mapped_column(Text)


class ConversationFeedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_conversation_feedback_once"),
        CheckConstraint(f"rating IN ({_q(FEEDBACK_RATINGS)})", name="rating"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)


class ConversationResearchRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """§13.6. The chat may propose research; only a user decision moves it out of `pending_approval`, and
    `preauthorized` is a decision the administrator already made in ChatSettings — recorded here all the
    same, so every research action has a named authorisation."""

    __tablename__ = "conversation_research_requests"
    __table_args__ = (
        CheckConstraint(f"state IN ({_q(REQUEST_STATES)})", name="state"),
        CheckConstraint("state NOT IN ('approved', 'running', 'completed') OR decided_at IS NOT NULL",
                        name="a_started_request_has_a_decision"),
        CheckConstraint("state <> 'failed' OR error IS NOT NULL", name="a_failure_needs_a_reason"),
        Index("ix_conversation_research_requests_owner", "organization_id", "user_id", "state", "created_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    # The assistant turn that reported the gap, and the question it could not answer.
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="SET NULL"))
    # The scope shown to the user before they approved: terms, topics, source kinds, what it will not do.
    proposed_scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_approval")
    authorization_basis: Mapped[str | None] = mapped_column(String(40))   # user_approved | preauthorized
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    # Research runs in the existing research layer; this is the handle, not a second research engine.
    research_project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="SET NULL"))
    knowledge_gap_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_gaps.id", ondelete="SET NULL"))
    # Filled when the question is answered again after the knowledge changed (§13.6 step 9-10).
    reanswer_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="SET NULL"))
    sources_added: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
