"""Phase 17 closure — harden AIExecution immutability at the database level.

WHY A NEW MIGRATION (not an edit of 0017): 0017 was already delivered in the
Phase 17 package; rewriting it would make any database that applied it
silently diverge. This migration replaces the guard functions in place.

DEFECTS FIXED (each demonstrated with raw SQL against the 0017 schema):
  1. A terminal execution could be DELETED — accounting history erasable.
  2. Parent / actor / attribution FK columns (visibility_run_id,
     knowledge_object_id, user_id, installation_id) were not protected: a
     terminal row's parent could be nulled or repointed while the parent
     still existed.
  3. Creation facts (organization_id, provider, model, started_at,
     previous_execution_id, ...) were mutable while the row was RUNNING.
  4. (performance) The default list order `started_at DESC NULLS LAST, id`
     could not use ix_ai_executions_org_started (whose order is
     NULLS FIRST), so every page-1 read sorted the tenant's whole history
     (measured 15 ms at 20k rows, linear). Adds a matching index.

NEW RULES: see app/models/ai_execution.py (statements are textually shared).

Revision ID: 0018
Revises: 0017
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATEMENTS = ["\n    CREATE OR REPLACE FUNCTION ai_executions_require_parent() RETURNS trigger AS $$\n    BEGIN\n        IF num_nonnulls(NEW.visibility_run_id) <> 1 THEN\n            RAISE EXCEPTION 'ai_executions: exactly one parent is required on insert'\n                USING ERRCODE = 'check_violation';\n        END IF;\n        RETURN NEW;\n    END;\n    $$ LANGUAGE plpgsql\n    ", 'DROP TRIGGER IF EXISTS trg_ai_executions_require_parent ON ai_executions', '\n    CREATE TRIGGER trg_ai_executions_require_parent\n        BEFORE INSERT ON ai_executions\n        FOR EACH ROW EXECUTE FUNCTION ai_executions_require_parent()\n    ', "\n    CREATE OR REPLACE FUNCTION ai_executions_immutable_terminal() RETURNS trigger AS $$\n    BEGIN\n        IF NEW.id IS DISTINCT FROM OLD.id OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.organization_id IS DISTINCT FROM OLD.organization_id OR NEW.parent_type IS DISTINCT FROM OLD.parent_type OR NEW.operation_type IS DISTINCT FROM OLD.operation_type OR NEW.provider IS DISTINCT FROM OLD.provider OR NEW.model IS DISTINCT FROM OLD.model OR NEW.stage IS DISTINCT FROM OLD.stage OR NEW.started_at IS DISTINCT FROM OLD.started_at OR NEW.prompt_reference IS DISTINCT FROM OLD.prompt_reference OR NEW.input_hash IS DISTINCT FROM OLD.input_hash OR NEW.previous_execution_id IS DISTINCT FROM OLD.previous_execution_id OR NEW.attempt_reason IS DISTINCT FROM OLD.attempt_reason OR NEW.request_id IS DISTINCT FROM OLD.request_id THEN\n            RAISE EXCEPTION 'ai_executions: creation facts are immutable'\n                USING ERRCODE = 'check_violation';\n        END IF;\n        IF OLD.status <> 'running' AND (\n            NEW.status IS DISTINCT FROM OLD.status OR NEW.completed_at IS DISTINCT FROM OLD.completed_at OR NEW.duration_ms IS DISTINCT FROM OLD.duration_ms OR NEW.error_code IS DISTINCT FROM OLD.error_code OR NEW.error_message IS DISTINCT FROM OLD.error_message OR NEW.input_tokens IS DISTINCT FROM OLD.input_tokens OR NEW.output_tokens IS DISTINCT FROM OLD.output_tokens OR NEW.total_tokens IS DISTINCT FROM OLD.total_tokens OR NEW.estimated_provider_cost IS DISTINCT FROM OLD.estimated_provider_cost OR NEW.actual_provider_cost IS DISTINCT FROM OLD.actual_provider_cost OR NEW.currency IS DISTINCT FROM OLD.currency OR NEW.provider_request_id IS DISTINCT FROM OLD.provider_request_id OR NEW.model_version IS DISTINCT FROM OLD.model_version\n        ) THEN\n            RAISE EXCEPTION 'ai_executions: a terminal execution is immutable'\n                USING ERRCODE = 'check_violation';\n        END IF;\n        IF NEW.visibility_run_id IS DISTINCT FROM OLD.visibility_run_id THEN\n            IF NEW.visibility_run_id IS NOT NULL\n               OR EXISTS (SELECT 1 FROM visibility_runs WHERE id = OLD.visibility_run_id) THEN\n                RAISE EXCEPTION 'ai_executions: visibility_run_id is immutable (only ON DELETE SET NULL of a deleted target may clear it)'\n                    USING ERRCODE = 'check_violation';\n            END IF;\n        END IF;\n        IF NEW.knowledge_object_id IS DISTINCT FROM OLD.knowledge_object_id THEN\n            IF NEW.knowledge_object_id IS NOT NULL\n               OR EXISTS (SELECT 1 FROM knowledge_objects WHERE id = OLD.knowledge_object_id) THEN\n                RAISE EXCEPTION 'ai_executions: knowledge_object_id is immutable (only ON DELETE SET NULL of a deleted target may clear it)'\n                    USING ERRCODE = 'check_violation';\n            END IF;\n        END IF;\n        IF NEW.user_id IS DISTINCT FROM OLD.user_id THEN\n            IF NEW.user_id IS NOT NULL\n               OR EXISTS (SELECT 1 FROM users WHERE id = OLD.user_id) THEN\n                RAISE EXCEPTION 'ai_executions: user_id is immutable (only ON DELETE SET NULL of a deleted target may clear it)'\n                    USING ERRCODE = 'check_violation';\n            END IF;\n        END IF;\n        IF NEW.installation_id IS DISTINCT FROM OLD.installation_id THEN\n            IF NEW.installation_id IS NOT NULL\n               OR EXISTS (SELECT 1 FROM installations WHERE id = OLD.installation_id) THEN\n                RAISE EXCEPTION 'ai_executions: installation_id is immutable (only ON DELETE SET NULL of a deleted target may clear it)'\n                    USING ERRCODE = 'check_violation';\n            END IF;\n        END IF;\n        RETURN NEW;\n    END;\n    $$ LANGUAGE plpgsql\n    ", 'DROP TRIGGER IF EXISTS trg_ai_executions_immutable_terminal ON ai_executions', '\n    CREATE TRIGGER trg_ai_executions_immutable_terminal\n        BEFORE UPDATE ON ai_executions\n        FOR EACH ROW EXECUTE FUNCTION ai_executions_immutable_terminal()\n    ', "\n    CREATE OR REPLACE FUNCTION ai_executions_guard_delete() RETURNS trigger AS $$\n    BEGIN\n        IF EXISTS (SELECT 1 FROM organizations WHERE id = OLD.organization_id) THEN\n            RAISE EXCEPTION 'ai_executions: execution records cannot be deleted (only tenant offboarding may remove them)'\n                USING ERRCODE = 'check_violation';\n        END IF;\n        RETURN OLD;\n    END;\n    $$ LANGUAGE plpgsql\n    ", 'DROP TRIGGER IF EXISTS trg_ai_executions_guard_delete ON ai_executions', '\n    CREATE TRIGGER trg_ai_executions_guard_delete\n        BEFORE DELETE ON ai_executions\n        FOR EACH ROW EXECUTE FUNCTION ai_executions_guard_delete()\n    ']

# The 0017 guard, restored verbatim on downgrade.
_PREVIOUS_UPDATE_GUARD = """
CREATE OR REPLACE FUNCTION ai_executions_immutable_terminal() RETURNS trigger AS $$
BEGIN
    IF OLD.status <> 'running' AND (
        NEW.organization_id IS DISTINCT FROM OLD.organization_id OR NEW.parent_type IS DISTINCT FROM OLD.parent_type
        OR NEW.stage IS DISTINCT FROM OLD.stage OR NEW.operation_type IS DISTINCT FROM OLD.operation_type
        OR NEW.provider IS DISTINCT FROM OLD.provider OR NEW.model IS DISTINCT FROM OLD.model
        OR NEW.model_version IS DISTINCT FROM OLD.model_version OR NEW.provider_request_id IS DISTINCT FROM OLD.provider_request_id
        OR NEW.started_at IS DISTINCT FROM OLD.started_at OR NEW.completed_at IS DISTINCT FROM OLD.completed_at
        OR NEW.duration_ms IS DISTINCT FROM OLD.duration_ms OR NEW.status IS DISTINCT FROM OLD.status
        OR NEW.error_code IS DISTINCT FROM OLD.error_code OR NEW.error_message IS DISTINCT FROM OLD.error_message
        OR NEW.input_tokens IS DISTINCT FROM OLD.input_tokens OR NEW.output_tokens IS DISTINCT FROM OLD.output_tokens
        OR NEW.total_tokens IS DISTINCT FROM OLD.total_tokens OR NEW.estimated_provider_cost IS DISTINCT FROM OLD.estimated_provider_cost
        OR NEW.actual_provider_cost IS DISTINCT FROM OLD.actual_provider_cost OR NEW.currency IS DISTINCT FROM OLD.currency
        OR NEW.prompt_reference IS DISTINCT FROM OLD.prompt_reference OR NEW.input_hash IS DISTINCT FROM OLD.input_hash
        OR NEW.previous_execution_id IS DISTINCT FROM OLD.previous_execution_id OR NEW.attempt_reason IS DISTINCT FROM OLD.attempt_reason
        OR NEW.request_id IS DISTINCT FROM OLD.request_id
    ) THEN
        RAISE EXCEPTION 'ai_executions: a terminal execution is immutable' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""


_LIST_INDEX = ("CREATE INDEX IF NOT EXISTS ix_ai_executions_org_list_order ON ai_executions "
               "(organization_id, started_at DESC NULLS LAST, id)")


def upgrade() -> None:
    for stmt in _STATEMENTS:
        op.execute(sa.text(stmt))
    op.execute(sa.text(_LIST_INDEX))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_ai_executions_org_list_order"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_ai_executions_guard_delete ON ai_executions"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS ai_executions_guard_delete()"))
    op.execute(sa.text(_PREVIOUS_UPDATE_GUARD))
