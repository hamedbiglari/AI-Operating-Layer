"""Durable AI-job execution (prompt v5 §10/§74, ADR-131): a worker lease so a job whose worker died can be
recovered, and a resume time so a job blocked only by a provider's rate limit or quota resumes by itself.
Additive and reversible; existing rows get no lease, no resume time and a zero resume count.

`resume_after` is acted on only while a job is `blocked` (the recovery sweep filters on it, and `run_job`
clears it); it is deliberately not a CHECK, because existing callers re-queue a blocked job by status alone.

Revision ID: 0042
Revises: 0041
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_jobs", sa.Column("lease_owner", sa.String(120), nullable=True))
    op.add_column("ai_jobs", sa.Column("lease_expires_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("ai_jobs", sa.Column("resume_after", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("ai_jobs", sa.Column("auto_resume_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint(op.f("ck_ai_jobs_lease_pair"), "ai_jobs",
                               "(lease_owner IS NULL) = (lease_expires_at IS NULL)")
    op.create_index("ix_ai_jobs_recovery", "ai_jobs", ["status", "lease_expires_at", "resume_after"])


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_recovery", table_name="ai_jobs")
    op.drop_constraint(op.f("ck_ai_jobs_lease_pair"), "ai_jobs", type_="check")
    op.drop_column("ai_jobs", "auto_resume_count")
    op.drop_column("ai_jobs", "resume_after")
    op.drop_column("ai_jobs", "lease_expires_at")
    op.drop_column("ai_jobs", "lease_owner")
