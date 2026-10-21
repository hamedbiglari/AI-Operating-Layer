"""Task DAG for AI jobs (prompt v5 §10, §50; ADR-135): `ai_job_items.depends_on`, the item_keys of the same job
that must complete first. Additive and reversible; existing items get `{}` (no dependency), which is how they
already ran.

Revision ID: 0045
Revises: 0044
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_job_items", sa.Column("depends_on", postgresql.ARRAY(sa.String(200)), nullable=False,
                                            server_default="{}"))


def downgrade() -> None:
    op.drop_column("ai_job_items", "depends_on")
