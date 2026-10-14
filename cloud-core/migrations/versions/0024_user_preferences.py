"""Per-user interface preferences (REQ-SET-001). Additive.

Revision ID: 0024
Revises: 0023
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("language", sa.String(5), nullable=False, server_default="en"),
        sa.Column("theme", sa.String(10), nullable=False, server_default="system"),
        sa.Column("font", sa.String(60)),
        sa.Column("notifications", postgresql.JSON()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_user_preferences_user"),
        sa.CheckConstraint("language IN ('en', 'fa')", name="ck_user_preferences_language"),
        sa.CheckConstraint("theme IN ('light', 'dark', 'system')", name="ck_user_preferences_theme"),
    )
    op.create_foreign_key("fk_user_preferences_user_org", "user_preferences", "users",
                          ["user_id", "organization_id"], ["id", "organization_id"], ondelete="CASCADE")
    op.create_index("ix_user_preferences_organization_id", "user_preferences", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_user_preferences_organization_id", table_name="user_preferences")
    op.drop_table("user_preferences")
