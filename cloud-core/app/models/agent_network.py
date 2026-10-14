"""
Agent Orchestration Layer — tenant-scoped, provider-neutral (ADR-096).

Completely separate from app/models/ai_agent.py which detects crawler traffic.
Every table carries organization_id; composite FKs enforce tenant isolation.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_definitions"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False)   # planner, research, content, …
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")  # draft/active/disabled
    protocol: Mapped[str] = mapped_column(String(30), nullable=False, default="internal")  # internal/mcp/rest/webhook
    endpoint_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    auth_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    trust_level: Mapped[str] = mapped_column(String(20), nullable=False, default="tenant")
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)   # ["research","summarize",…]
    allowed_tools: Mapped[list | None] = mapped_column(JSON, nullable=True)
    allowed_ai_accounts: Mapped[list | None] = mapped_column(JSON, nullable=True)  # list of account UUIDs
    memory_profile_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_agent_definitions_name"),)


class AgentSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Active agent execution session, groups tasks and messages."""
    __tablename__ = "agent_sessions"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_key: Mapped[str] = mapped_column(String(200), nullable=False)
    initiator_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    __table_args__ = (UniqueConstraint("organization_id", "session_key", name="uq_agent_sessions_key"),)


class AgentTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A unit of work within an agent session."""
    __tablename__ = "agent_tasks"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    task_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    priority: Mapped[int] = mapped_column(nullable=False, default=0)
    input_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # references, never secrets
    output_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    depends_on: Mapped[list | None] = mapped_column(JSON, nullable=True)  # list of task UUIDs
    ai_execution_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    __table_args__ = (UniqueConstraint("organization_id", "session_id", "task_key", name="uq_agent_tasks_key"),)


class AgentMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable, auditable agent-to-agent message."""
    __tablename__ = "agent_messages"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    from_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    to_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)  # task_assignment/result/handoff/error
    payload_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # references only; never raw secrets
    memory_references: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="sent")
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentHandoff(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable handoff record when Agent A hands work to Agent B."""
    __tablename__ = "agent_handoffs"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    from_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    to_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    working_memory_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    package: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    accepted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class AgentMemoryBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Explicit permission for an agent to access a memory profile."""
    __tablename__ = "agent_memory_bindings"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_definition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    memory_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    access_level: Mapped[str] = mapped_column(String(20), nullable=False, default="read")  # read/write/admin
    __table_args__ = (UniqueConstraint("organization_id", "agent_definition_id", "memory_profile_id",
                                       name="uq_agent_memory_binding"),)
