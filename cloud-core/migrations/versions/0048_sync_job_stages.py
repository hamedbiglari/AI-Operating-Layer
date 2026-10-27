"""`sync_job_stages` (Step 7C-3, decision D14b): the current state of each stage of a document-ingestion job, one
row per (job, stage), not an append-only log. Rows go with their job (ON DELETE CASCADE). No backfill: existing
jobs have no rows, and the Processing endpoint derives their stages instead. Like every tenant-scoped table, it
carries organization_id (decision A; tests/test_forensic_integrity.py enforces it).

Enum types follow 0002:24-55: created explicitly here, and every column uses create_type=False so create_table
does not try to create them a second time. Locally, run `python -m alembic upgrade head` before pytest: the test
suite's create_all would otherwise build this table first and this migration would then fail on it.

Revision ID: 0048
Revises: 0047
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STAGE_KEYS = ("upload", "security", "conversion", "structure", "ocr", "chunking", "evidence", "knowledge")
STAGE_STATES = ("pending", "active", "done", "failed", "not_tracked")


def upgrade() -> None:
    stage_key = postgresql.ENUM(*STAGE_KEYS, name="sync_job_stage_key", create_type=False)
    stage_state = postgresql.ENUM(*STAGE_STATES, name="sync_job_stage_state", create_type=False)
    bind = op.get_bind()
    stage_key.create(bind, checkfirst=True)
    stage_state.create(bind, checkfirst=True)

    op.create_table(
        "sync_job_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sync_job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_key", stage_key, nullable=False),
        sa.Column("state", stage_state, nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sync_job_stages_organization_id", "sync_job_stages", ["organization_id"])
    op.create_index("ix_sync_job_stages_sync_job_id", "sync_job_stages", ["sync_job_id"])
    op.create_unique_constraint("uq_sync_job_stages_job_stage", "sync_job_stages", ["sync_job_id", "stage_key"])


def downgrade() -> None:
    # The table first: PostgreSQL will not drop a type a column still uses.
    op.drop_table("sync_job_stages")
    bind = op.get_bind()
    postgresql.ENUM(name="sync_job_stage_state").drop(bind, checkfirst=True)
    postgresql.ENUM(name="sync_job_stage_key").drop(bind, checkfirst=True)
