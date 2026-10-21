"""Per-user usage alert threshold for the Usage & quota view (ADR-127). Additive and reversible.

Revision ID: 0039
Revises: 0038
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("usage_alert_threshold", sa.SmallInteger(), nullable=False,
                                                server_default="80"))
    op.create_check_constraint("ck_user_preferences_usage_alert_threshold", "user_preferences",
                               "usage_alert_threshold BETWEEN 50 AND 100")


def downgrade() -> None:
    op.drop_constraint("ck_user_preferences_usage_alert_threshold", "user_preferences", type_="check")
    op.drop_column("user_preferences", "usage_alert_threshold")
