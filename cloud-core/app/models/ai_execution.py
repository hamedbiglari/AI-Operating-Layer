"""
AIExecution — one real invocation of one AI model provider operation
(Phase 16 architecture C "hybrid canonical execution", LOCKED; Phase 17
implementation).

WHAT A ROW IS
    Exactly one provider/model call the application actually made.
    Retries, provider fallback and model fallback are NEW rows chained by
    `previous_execution_id`. A fixture probe or a not-configured provider
    produces NO row — nothing was invoked.

WHAT A ROW IS NOT
    - not the business task (VisibilityRun, ResearchTask, SyncJob own that)
    - not the domain result (VisibilityTest owns the observation)
    - not the audit trail (audit_logs answers "who asked for what")
    - not a content store: no raw prompt, no raw response, ever

PARENT LINKAGE (exclusive arc)
    `parent_type` is a stored discriminator. Each parent domain that
    actually invokes a model gets ONE typed, nullable, composite tenant FK
    column. Today that is only `visibility_run_id` — the first and only
    domain with a real model path. Further columns are added with the
    domain, never speculatively.

    Integrity is enforced by the database, not by convention:
      * parent_type_known (ck_)  — discriminator vocabulary
      * ck_ai_executions_arc_cardinality     — at most one parent column set
      * ck_ai_executions_parent_type_matches — a set column agrees with the
                                               discriminator
      * trg_ai_executions_require_parent     — INSERT must set exactly one
                                               parent (a trigger, because a
                                               CHECK cannot tell "inserted
                                               without a parent" from
                                               "parent later deleted")
      * trg_ai_executions_immutable_terminal — a terminal row's accounting
                                               facts can never change

DELETION
    Deleting the business parent must NOT delete the accounting fact. The
    composite FKs use PostgreSQL 15+ column-list `ON DELETE SET NULL
    (<fk_col>)`, which nulls only the FK column and leaves
    `organization_id` intact. The plain composite `ON DELETE SET NULL`
    used by visibility_tests' older FKs would try to null
    organization_id (NOT NULL) and fail — that pattern is deliberately not
    reproduced here.

    SQLAlchemy's DDL compiler rejects column-list SET NULL, so these FKs
    and the triggers are issued as raw DDL: by migration 0017 for real
    databases, and by the metadata `after_create` listener below for
    databases built with `Base.metadata.create_all()` (the test fixtures).
    Both paths use the same statements, all idempotent.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AIAttemptReason, AIExecutionStatus, AIOperationType, AIParentType


def _in_list(values) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


# Every typed parent column in the arc. Adding a domain = append here AND
# add the column + FK in a migration.
ARC_COLUMNS: tuple[str, ...] = ("visibility_run_id", "ai_job_id")
PARENT_COLUMN_FOR_TYPE: dict[AIParentType, str] = {
    AIParentType.VISIBILITY_RUN: "visibility_run_id",
    AIParentType.AI_JOB: "ai_job_id",   # AI Center, migration 0020
}


class AIExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_executions"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_ai_executions_id_organization_id"),
        CheckConstraint(
            f"parent_type IN ({_in_list(AIParentType)})", name="parent_type_known"
        ),
        CheckConstraint(
            f"num_nonnulls({', '.join(ARC_COLUMNS)}) <= 1", name="arc_cardinality"
        ),
        CheckConstraint(
            " AND ".join(f"({col} IS NULL OR parent_type = '{pt.value}')" for pt, col in PARENT_COLUMN_FOR_TYPE.items()),
            name="parent_type_matches",
        ),
        CheckConstraint(f"status IN ({_in_list(AIExecutionStatus)})", name="status"),
        CheckConstraint(
            f"operation_type IN ({_in_list(AIOperationType)})", name="operation_type"
        ),
        CheckConstraint(
            f"attempt_reason IS NULL OR attempt_reason IN ({_in_list(AIAttemptReason)})",
            name="attempt_reason",
        ),
        # A chained attempt must say why it exists; a first attempt must not.
        CheckConstraint(
            "(previous_execution_id IS NULL) = (attempt_reason IS NULL)",
            name="chain_reason",
        ),
        # A cost without a currency is not a cost.
        CheckConstraint(
            "(estimated_provider_cost IS NULL AND actual_provider_cost IS NULL) OR currency IS NOT NULL",
            name="cost_currency",
        ),
        CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND (output_tokens IS NULL OR output_tokens >= 0)",
            name="tokens_nonnegative",
        ),
        CheckConstraint(
            "(status = 'running') = (completed_at IS NULL)", name="terminal_completed"
        ),
        Index("ix_ai_executions_org_started", "organization_id", "started_at"),
        # Serves the canonical list order (apply_sort: started_at DESC NULLS LAST, id).
        Index("ix_ai_executions_org_list_order", "organization_id", text("started_at DESC NULLS LAST"), "id"),
        Index("ix_ai_executions_org_provider_model", "organization_id", "provider", "model"),
        Index("ix_ai_executions_org_status", "organization_id", "status"),
        Index("ix_ai_executions_visibility_run", "visibility_run_id"),
        Index("ix_ai_executions_previous", "previous_execution_id"),
        Index("ix_ai_executions_knowledge_object", "knowledge_object_id"),
        # Stale-running sweep (reclaim_stale_executions).
        Index(
            "ix_ai_executions_running_started", "started_at",
            postgresql_where="status = 'running'",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Actor. Either may be NULL: /ai/ask-style machine callers have an
    # installation and no user; background work may have neither.
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    installation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    parent_type: Mapped[str] = mapped_column(String(40), nullable=False)
    visibility_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ai_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    # Attribution only — never a substitute for the business parent.
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(60), nullable=True)
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False)

    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AIExecutionStatus.RUNNING.value
    )
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # NULL = the provider did not report it. Never estimated from characters.
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # NULL = UNKNOWN. Never 0 unless the cost truly is 0; actual is never
    # copied from estimated.
    estimated_provider_cost: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    actual_provider_cost: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    prompt_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    previous_execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    attempt_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # AI Center (REQ-AIC-001/007): the provider ACCOUNT that served this call
    # (provider ≠ account ≠ model) and the normalised stop reason.
    provider_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    stop_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # HTTP-originated calls only; not propagated into Celery (Phase 16 §12).
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AIExecution {self.id} {self.provider}/{self.model} {self.status}>"


# ---------------------------------------------------------------------------
# Raw DDL shared (textually) with migration 0017. Every statement is
# idempotent so it is safe on a database already built by alembic.
# ---------------------------------------------------------------------------
_COMPOSITE_FKS = (
    # (table, name, local cols, target table, on-delete clause)
    ("ai_executions", "fk_ai_executions_visibility_run", "visibility_run_id, organization_id",
     "visibility_runs", "SET NULL (visibility_run_id)"),
    ("ai_executions", "fk_ai_executions_knowledge_object", "knowledge_object_id, organization_id",
     "knowledge_objects", "SET NULL (knowledge_object_id)"),
    ("ai_executions", "fk_ai_executions_user", "user_id, organization_id",
     "users", "SET NULL (user_id)"),
    ("ai_executions", "fk_ai_executions_installation", "installation_id, organization_id",
     "installations", "SET NULL (installation_id)"),
    ("ai_executions", "fk_ai_executions_previous", "previous_execution_id, organization_id",
     "ai_executions", "RESTRICT"),
    ("ai_executions", "fk_ai_executions_ai_job", "ai_job_id, organization_id",
     "ai_jobs", "SET NULL (ai_job_id)"),
    ("ai_executions", "fk_ai_executions_provider_account", "provider_account_id, organization_id",
     "ai_provider_accounts", "SET NULL (provider_account_id)"),
    ("visibility_tests", "fk_visibility_tests_ai_execution", "ai_execution_id, organization_id",
     "ai_executions", "SET NULL (ai_execution_id)"),
)

TARGET_UNIQUES = (
    ("visibility_runs", "uq_visibility_runs_id_organization_id"),
    ("knowledge_objects", "uq_knowledge_objects_id_organization_id"),
    ("users", "uq_users_id_organization_id"),
)


def composite_fk_statements() -> list[str]:
    stmts = []
    for table, name, cols, target, on_delete in _COMPOSITE_FKS:
        stmts.append(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        stmts.append(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({cols}) "
            f"REFERENCES {target} (id, organization_id) ON DELETE {on_delete}"
        )
    return stmts


# ---------------------------------------------------------------------------
# DB-level immutability (Phase 17 closure: replaces the first-cut trigger,
# which froze only outcome columns of terminal rows and left creation
# facts mutable while RUNNING, parent/actor FKs mutable forever, and
# DELETE unguarded — all three demonstrated with raw SQL before the fix).
#
#   CREATION FACTS  frozen from INSERT onward, in every status.
#   OUTCOME FACTS   writable only while status='running' (the single
#                   finalization); frozen once terminal.
#   LINK COLUMNS    (parent / actor / attribution FKs) may change in exactly
#                   one way: to NULL, and only when the referenced row no
#                   longer exists — i.e. the ON DELETE SET NULL (col)
#                   referential action. Nulling while the target exists,
#                   or pointing at a different row, is rejected.
#   updated_at      the only freely-changing column (ORM bookkeeping).
#   DELETE          rejected unless the owning organization no longer
#                   exists (tenant offboarding via ON DELETE CASCADE).
#                   There is no other sanctioned deletion path; a future
#                   retention purge must be added deliberately.
# ---------------------------------------------------------------------------
CREATION_FACT_COLUMNS = (
    "id", "created_at", "organization_id", "parent_type", "operation_type", "provider", "model", "stage",
    "started_at", "prompt_reference", "input_hash", "previous_execution_id",
    "attempt_reason", "request_id",
)
OUTCOME_FACT_COLUMNS = (
    "status", "completed_at", "duration_ms", "error_code", "error_message",
    "input_tokens", "output_tokens", "total_tokens", "estimated_provider_cost",
    "actual_provider_cost", "currency", "provider_request_id", "model_version",
    "stop_reason",
)
# column -> table it references (by id)
LINK_COLUMNS = {
    "visibility_run_id": "visibility_runs",
    "knowledge_object_id": "knowledge_objects",
    "user_id": "users",
    "installation_id": "installations",
    # AI Center (migration 0020): which provider account served the call.
    "provider_account_id": "ai_provider_accounts",
    "ai_job_id": "ai_jobs",
}


def _link_checks() -> str:
    parts = []
    for col, table in LINK_COLUMNS.items():
        parts.append(f"""
        IF NEW.{col} IS DISTINCT FROM OLD.{col} THEN
            IF NEW.{col} IS NOT NULL
               OR EXISTS (SELECT 1 FROM {table} WHERE id = OLD.{col}) THEN
                RAISE EXCEPTION 'ai_executions: {col} is immutable (only ON DELETE SET NULL of a deleted target may clear it)'
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;""")
    return "".join(parts)


TRIGGER_STATEMENTS: list[str] = [
    """
    CREATE OR REPLACE FUNCTION ai_executions_require_parent() RETURNS trigger AS $$
    BEGIN
        IF num_nonnulls(""" + ", ".join("NEW." + c for c in ARC_COLUMNS) + """) <> 1 THEN
            RAISE EXCEPTION 'ai_executions: exactly one parent is required on insert'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS trg_ai_executions_require_parent ON ai_executions",
    """
    CREATE TRIGGER trg_ai_executions_require_parent
        BEFORE INSERT ON ai_executions
        FOR EACH ROW EXECUTE FUNCTION ai_executions_require_parent()
    """,
    """
    CREATE OR REPLACE FUNCTION ai_executions_immutable_terminal() RETURNS trigger AS $$
    BEGIN
        IF """ + " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in CREATION_FACT_COLUMNS) + """ THEN
            RAISE EXCEPTION 'ai_executions: creation facts are immutable'
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.status <> 'running' AND (
            """ + " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in OUTCOME_FACT_COLUMNS) + """
        ) THEN
            RAISE EXCEPTION 'ai_executions: a terminal execution is immutable'
                USING ERRCODE = 'check_violation';
        END IF;""" + _link_checks() + """
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS trg_ai_executions_immutable_terminal ON ai_executions",
    """
    CREATE TRIGGER trg_ai_executions_immutable_terminal
        BEFORE UPDATE ON ai_executions
        FOR EACH ROW EXECUTE FUNCTION ai_executions_immutable_terminal()
    """,
    """
    CREATE OR REPLACE FUNCTION ai_executions_guard_delete() RETURNS trigger AS $$
    BEGIN
        IF EXISTS (SELECT 1 FROM organizations WHERE id = OLD.organization_id) THEN
            RAISE EXCEPTION 'ai_executions: execution records cannot be deleted (only tenant offboarding may remove them)'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS trg_ai_executions_guard_delete ON ai_executions",
    """
    CREATE TRIGGER trg_ai_executions_guard_delete
        BEFORE DELETE ON ai_executions
        FOR EACH ROW EXECUTE FUNCTION ai_executions_guard_delete()
    """,
]


def _after_create(target, connection, **kw):  # noqa: ANN001
    """create_all() path (test fixtures). No-op unless the canonical table
    is part of this metadata; every statement is idempotent."""
    if "ai_executions" not in target.tables:
        return
    for stmt in composite_fk_statements() + TRIGGER_STATEMENTS:
        connection.exec_driver_sql(stmt)


event.listen(Base.metadata, "after_create", _after_create)
