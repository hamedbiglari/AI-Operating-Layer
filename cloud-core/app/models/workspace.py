"""
Persistent AI command workspace (prompt v4.0 §46–§54; ADR-125).

A command is not a chat message. It is a durable, versioned piece of user intent with an explicit scope,
an execution state that lives on the server, and a result linked to the knowledge it came from.

    WorkspaceCommand            one line of work: owner, topic/category, state, current + last-run version
      └──< WorkspaceCommandVersion   v1, v2, v3 … the text as typed, its scope, budget, routing choice,
                                     and — once executed — what it produced. An executed version is frozen
                                     by a database trigger; editing it creates the next version (§49).

Drafts are saved here, server-side, as the user types (§48). The browser may cache a draft too, but this
table is the authority: closing the page, losing the tab or signing in elsewhere finds the same draft.

PRIVACY (§64): a command belongs to the user who wrote it. Nothing in the API lists or reads another
user's commands, even inside the same organisation.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

COMMAND_STATES = ("draft", "queued", "running", "completed", "completed_with_gaps", "blocked", "failed",
                  "cancelled")
INTENTS = ("evidence_research", "synthesis", "find_evidence_for_claim", "contradictions", "section_applicability",
           "matrix_cell_research", "reprocess_document", "claims_from_page", "unsupported_statements",
           "coverage_audit", "continue_previous", "unknown")


def _q(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class WorkspaceCommand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_commands"
    __table_args__ = (
        CheckConstraint(f"state IN ({_q(COMMAND_STATES)})", name="state"),
        CheckConstraint("state NOT IN ('failed', 'blocked') OR error IS NOT NULL", name="a_failure_needs_a_reason"),
        Index("ix_workspace_commands_owner", "organization_id", "user_id", "archived_at", "updated_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(300))
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"))
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="SET NULL"), index=True)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_executed_version: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class WorkspaceCommandVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_command_versions"
    __table_args__ = (
        UniqueConstraint("command_id", "version", name="uq_workspace_command_version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(f"intent IS NULL OR intent IN ({_q(INTENTS)})", name="intent"),
        CheckConstraint(f"execution_state IN ({_q(COMMAND_STATES)})", name="execution_state"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    command_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspace_commands.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # autosave counter: the client sends the revision it edited; a stale one is refused (409) rather than
    # silently overwriting a newer draft typed in another tab
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    intent: Mapped[str | None] = mapped_column(String(40))
    scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    selected_source_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    attachments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)   # document ids
    model_config_: Mapped[dict] = mapped_column("model_config", JSON, nullable=False, default=dict)
    budget: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    plan: Mapped[dict | None] = mapped_column(JSON)                  # the parsed, explicit plan shown before running
    execution_state: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    executed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    synthesis_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("synthesis_runs.id", ondelete="SET NULL"))
    sync_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cost: Mapped[dict | None] = mapped_column(JSON)


# §49: once executed, what was asked can never be rewritten — only its outcome can be filled in.
TRIGGER_STATEMENTS = [
    """
    CREATE OR REPLACE FUNCTION workspace_versions_freeze_executed() RETURNS trigger AS $$
    BEGIN
        IF OLD.executed_at IS NOT NULL AND (
            NEW.text IS DISTINCT FROM OLD.text OR NEW.scope::text IS DISTINCT FROM OLD.scope::text
            OR NEW.intent IS DISTINCT FROM OLD.intent OR NEW.version IS DISTINCT FROM OLD.version
            OR NEW.selected_source_ids::text IS DISTINCT FROM OLD.selected_source_ids::text
            OR NEW.attachments::text IS DISTINCT FROM OLD.attachments::text
            OR NEW.budget::text IS DISTINCT FROM OLD.budget::text
            OR NEW.model_config::text IS DISTINCT FROM OLD.model_config::text
            OR NEW.executed_at IS DISTINCT FROM OLD.executed_at
        ) THEN
            RAISE EXCEPTION 'workspace_command_versions: an executed version is immutable; edit creates a new version'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS trg_workspace_versions_freeze ON workspace_command_versions",
    """
    CREATE TRIGGER trg_workspace_versions_freeze
        BEFORE UPDATE ON workspace_command_versions
        FOR EACH ROW EXECUTE FUNCTION workspace_versions_freeze_executed()
    """,
]


def _after_create(target, connection, **kw):  # noqa: ANN001
    if "workspace_command_versions" not in target.tables:
        return
    for stmt in TRIGGER_STATEMENTS:
        connection.exec_driver_sql(stmt)


event.listen(Base.metadata, "after_create", _after_create)
