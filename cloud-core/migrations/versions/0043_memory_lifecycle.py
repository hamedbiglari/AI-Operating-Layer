"""Working-memory lifecycle (prompt v5 §11-12, §87; ADR-133): CREATED -> VALIDATED -> ACTIVE -> SUPERSEDED ->
ARCHIVED as a CHECK, a link from a superseded state record to its successor, and a CHECK on agent memory
access levels. Additive and reversible.

Existing rows: every row was written as `active` and stays so, except that for the state-like kinds only the
newest version of each (tenant, job, kind) stays active; older versions become `superseded`, because that is
what they already were. Downgrade turns every status back into `active` (the old column held nothing else).

Revision ID: 0043
Revises: 0042
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATES = "('created', 'validated', 'active', 'superseded', 'archived')"
_SINGLETON_KINDS = "('job_state', 'current_synthesis', 'processing_checkpoint', 'ai_handoff', 'next_action')"


def upgrade() -> None:
    op.add_column("ai_working_memory", sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_ai_working_memory_superseded_by", "ai_working_memory", "ai_working_memory",
                          ["superseded_by_id"], ["id"], ondelete="SET NULL")
    op.execute(f"""
        UPDATE ai_working_memory m SET status = 'superseded'
        WHERE m.kind IN {_SINGLETON_KINDS} AND m.version < (
            SELECT max(n.version) FROM ai_working_memory n
            WHERE n.organization_id = m.organization_id AND n.job_key = m.job_key AND n.kind = m.kind)""")
    op.create_check_constraint(op.f("ck_ai_working_memory_status"), "ai_working_memory", f"status IN {_STATES}")
    op.create_check_constraint(op.f("ck_ai_working_memory_successor_only_when_superseded"),
                               "ai_working_memory", "superseded_by_id IS NULL OR status IN ('superseded', 'archived')")
    op.execute("UPDATE agent_memory_bindings SET access_level = 'read' "
               "WHERE access_level NOT IN ('read', 'write', 'admin')")
    op.create_check_constraint(op.f("ck_agent_memory_bindings_access_level"), "agent_memory_bindings",
                               "access_level IN ('read', 'write', 'admin')")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_agent_memory_bindings_access_level"), "agent_memory_bindings", type_="check")
    op.drop_constraint(op.f("ck_ai_working_memory_successor_only_when_superseded"), "ai_working_memory",
                       type_="check")
    op.drop_constraint(op.f("ck_ai_working_memory_status"), "ai_working_memory", type_="check")
    op.execute("UPDATE ai_working_memory SET status = 'active'")
    op.drop_constraint("fk_ai_working_memory_superseded_by", "ai_working_memory", type_="foreignkey")
    op.drop_column("ai_working_memory", "superseded_by_id")
