"""Phase 17 — canonical AI execution (Phase 16 architecture C).

Creates `ai_executions` and links `visibility_tests.ai_execution_id`.
Adds three additive UNIQUE (id, organization_id) targets required by the
composite tenant FKs (ADR-037): visibility_runs, knowledge_objects, users.
`id` is already each table's primary key, so these cannot conflict with
existing data.

The composite FKs use PostgreSQL 15+ column-list `ON DELETE SET NULL
(<col>)` so deleting a parent/actor/attributed object nulls only that
column and preserves organization_id — deliberately NOT the plain
composite `ON DELETE SET NULL` visibility_tests' older FKs use (which
would try to null NOT NULL organization_id). SQLAlchemy's DDL compiler
rejects the column-list form, hence raw SQL. The statements are kept
textually identical to app/models/ai_execution.py (used by create_all in
tests).

Revision ID: 0017
Revises: 0016
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TARGET_UNIQUES = (
    ("visibility_runs", "uq_visibility_runs_id_organization_id"),
    ("knowledge_objects", "uq_knowledge_objects_id_organization_id"),
    ("users", "uq_users_id_organization_id"),
)

_FK_STATEMENTS = ['ALTER TABLE ai_executions DROP CONSTRAINT IF EXISTS fk_ai_executions_visibility_run', 'ALTER TABLE ai_executions ADD CONSTRAINT fk_ai_executions_visibility_run FOREIGN KEY (visibility_run_id, organization_id) REFERENCES visibility_runs (id, organization_id) ON DELETE SET NULL (visibility_run_id)', 'ALTER TABLE ai_executions DROP CONSTRAINT IF EXISTS fk_ai_executions_knowledge_object', 'ALTER TABLE ai_executions ADD CONSTRAINT fk_ai_executions_knowledge_object FOREIGN KEY (knowledge_object_id, organization_id) REFERENCES knowledge_objects (id, organization_id) ON DELETE SET NULL (knowledge_object_id)', 'ALTER TABLE ai_executions DROP CONSTRAINT IF EXISTS fk_ai_executions_user', 'ALTER TABLE ai_executions ADD CONSTRAINT fk_ai_executions_user FOREIGN KEY (user_id, organization_id) REFERENCES users (id, organization_id) ON DELETE SET NULL (user_id)', 'ALTER TABLE ai_executions DROP CONSTRAINT IF EXISTS fk_ai_executions_installation', 'ALTER TABLE ai_executions ADD CONSTRAINT fk_ai_executions_installation FOREIGN KEY (installation_id, organization_id) REFERENCES installations (id, organization_id) ON DELETE SET NULL (installation_id)', 'ALTER TABLE ai_executions DROP CONSTRAINT IF EXISTS fk_ai_executions_previous', 'ALTER TABLE ai_executions ADD CONSTRAINT fk_ai_executions_previous FOREIGN KEY (previous_execution_id, organization_id) REFERENCES ai_executions (id, organization_id) ON DELETE RESTRICT', 'ALTER TABLE visibility_tests DROP CONSTRAINT IF EXISTS fk_visibility_tests_ai_execution', 'ALTER TABLE visibility_tests ADD CONSTRAINT fk_visibility_tests_ai_execution FOREIGN KEY (ai_execution_id, organization_id) REFERENCES ai_executions (id, organization_id) ON DELETE SET NULL (ai_execution_id)']

_TRIGGER_STATEMENTS = ["\n    CREATE OR REPLACE FUNCTION ai_executions_require_parent() RETURNS trigger AS $$\n    BEGIN\n        IF num_nonnulls(NEW.visibility_run_id) <> 1 THEN\n            RAISE EXCEPTION 'ai_executions: exactly one parent is required on insert'\n                USING ERRCODE = 'check_violation';\n        END IF;\n        RETURN NEW;\n    END;\n    $$ LANGUAGE plpgsql\n    ", 'DROP TRIGGER IF EXISTS trg_ai_executions_require_parent ON ai_executions', '\n    CREATE TRIGGER trg_ai_executions_require_parent\n        BEFORE INSERT ON ai_executions\n        FOR EACH ROW EXECUTE FUNCTION ai_executions_require_parent()\n    ', "\n    CREATE OR REPLACE FUNCTION ai_executions_immutable_terminal() RETURNS trigger AS $$\n    BEGIN\n        IF OLD.status <> 'running' AND (\n            NEW.organization_id IS DISTINCT FROM OLD.organization_id OR NEW.parent_type IS DISTINCT FROM OLD.parent_type OR NEW.stage IS DISTINCT FROM OLD.stage OR NEW.operation_type IS DISTINCT FROM OLD.operation_type OR NEW.provider IS DISTINCT FROM OLD.provider OR NEW.model IS DISTINCT FROM OLD.model OR NEW.model_version IS DISTINCT FROM OLD.model_version OR NEW.provider_request_id IS DISTINCT FROM OLD.provider_request_id OR NEW.started_at IS DISTINCT FROM OLD.started_at OR NEW.completed_at IS DISTINCT FROM OLD.completed_at OR NEW.duration_ms IS DISTINCT FROM OLD.duration_ms OR NEW.status IS DISTINCT FROM OLD.status OR NEW.error_code IS DISTINCT FROM OLD.error_code OR NEW.error_message IS DISTINCT FROM OLD.error_message OR NEW.input_tokens IS DISTINCT FROM OLD.input_tokens OR NEW.output_tokens IS DISTINCT FROM OLD.output_tokens OR NEW.total_tokens IS DISTINCT FROM OLD.total_tokens OR NEW.estimated_provider_cost IS DISTINCT FROM OLD.estimated_provider_cost OR NEW.actual_provider_cost IS DISTINCT FROM OLD.actual_provider_cost OR NEW.currency IS DISTINCT FROM OLD.currency OR NEW.prompt_reference IS DISTINCT FROM OLD.prompt_reference OR NEW.input_hash IS DISTINCT FROM OLD.input_hash OR NEW.previous_execution_id IS DISTINCT FROM OLD.previous_execution_id OR NEW.attempt_reason IS DISTINCT FROM OLD.attempt_reason OR NEW.request_id IS DISTINCT FROM OLD.request_id\n        ) THEN\n            RAISE EXCEPTION 'ai_executions: a terminal execution is immutable'\n                USING ERRCODE = 'check_violation';\n        END IF;\n        RETURN NEW;\n    END;\n    $$ LANGUAGE plpgsql\n    ", 'DROP TRIGGER IF EXISTS trg_ai_executions_immutable_terminal ON ai_executions', '\n    CREATE TRIGGER trg_ai_executions_immutable_terminal\n        BEFORE UPDATE ON ai_executions\n        FOR EACH ROW EXECUTE FUNCTION ai_executions_immutable_terminal()\n    ']


def upgrade() -> None:
    server_version = op.get_bind().dialect.server_version_info or (0,)
    if server_version < (15,):
        raise RuntimeError(
            "Migration 0017 requires PostgreSQL 15+ (column-list ON DELETE SET NULL); "
            f"server reports {server_version}"
        )

    for table, name in _TARGET_UNIQUES:
        op.create_unique_constraint(name, table, ["id", "organization_id"])

    op.create_table(
        "ai_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parent_type", sa.String(40), nullable=False),
        sa.Column("visibility_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("knowledge_object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stage", sa.String(60), nullable=True),
        sa.Column("operation_type", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("model_version", sa.String(120), nullable=True),
        sa.Column("provider_request_id", sa.String(200), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_provider_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("actual_provider_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("prompt_reference", sa.String(200), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("previous_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempt_reason", sa.String(30), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "organization_id", name="uq_ai_executions_id_organization_id"),
        sa.CheckConstraint("parent_type IN ('visibility_run')", name="parent_type_known"),
        sa.CheckConstraint("num_nonnulls(visibility_run_id) <= 1", name="arc_cardinality"),
        sa.CheckConstraint("visibility_run_id IS NULL OR parent_type = 'visibility_run'",
                           name="parent_type_matches"),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed', 'timeout', 'rate_limited', "
                           "'cancelled', 'abandoned')", name="status"),
        sa.CheckConstraint("operation_type IN ('chat', 'completion', 'embedding', 'rerank', 'vision')",
                           name="operation_type"),
        sa.CheckConstraint("attempt_reason IS NULL OR attempt_reason IN ('retry', 'manual_retry', "
                           "'provider_fallback', 'model_fallback')", name="attempt_reason"),
        sa.CheckConstraint("(previous_execution_id IS NULL) = (attempt_reason IS NULL)",
                           name="chain_reason"),
        sa.CheckConstraint("(estimated_provider_cost IS NULL AND actual_provider_cost IS NULL) "
                           "OR currency IS NOT NULL", name="cost_currency"),
        sa.CheckConstraint("(input_tokens IS NULL OR input_tokens >= 0) AND "
                           "(output_tokens IS NULL OR output_tokens >= 0)",
                           name="tokens_nonnegative"),
        sa.CheckConstraint("(status = 'running') = (completed_at IS NULL)",
                           name="terminal_completed"),
    )
    op.create_index("ix_ai_executions_organization_id", "ai_executions", ["organization_id"])
    op.create_index("ix_ai_executions_org_started", "ai_executions", ["organization_id", "started_at"])
    op.create_index("ix_ai_executions_org_provider_model", "ai_executions",
                    ["organization_id", "provider", "model"])
    op.create_index("ix_ai_executions_org_status", "ai_executions", ["organization_id", "status"])
    op.create_index("ix_ai_executions_visibility_run", "ai_executions", ["visibility_run_id"])
    op.create_index("ix_ai_executions_previous", "ai_executions", ["previous_execution_id"])
    op.create_index("ix_ai_executions_knowledge_object", "ai_executions", ["knowledge_object_id"])
    op.create_index("ix_ai_executions_running_started", "ai_executions", ["started_at"],
                    postgresql_where=sa.text("status = 'running'"))

    op.add_column("visibility_tests",
                  sa.Column("ai_execution_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_visibility_tests_ai_execution_id", "visibility_tests", ["ai_execution_id"])

    for stmt in _FK_STATEMENTS + _TRIGGER_STATEMENTS:
        op.execute(sa.text(stmt))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE visibility_tests DROP CONSTRAINT IF EXISTS fk_visibility_tests_ai_execution"))
    op.drop_index("ix_visibility_tests_ai_execution_id", table_name="visibility_tests")
    op.drop_column("visibility_tests", "ai_execution_id")
    op.drop_table("ai_executions")  # drops its triggers and FKs with it
    op.execute(sa.text("DROP FUNCTION IF EXISTS ai_executions_require_parent()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS ai_executions_immutable_terminal()"))
    for table, name in reversed(_TARGET_UNIQUES):
        op.drop_constraint(name, table, type_="unique")
