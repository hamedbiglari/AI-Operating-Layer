"""Archive state for sources (V5-source-archive-state, V5-source-detail-archive): when a source was archived and why.

Additive and reversible. No existing row is touched: both columns are nullable, and NULL means "not archived".

Revision ID: 0056
Revises: 0055
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("archived_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("archive_reason", sa.Text(), nullable=True))
    op.create_index("ix_sources_archived_at", "sources", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_sources_archived_at", table_name="sources")
    op.drop_column("sources", "archive_reason")
    op.drop_column("sources", "archived_at")
