"""Platform administrators (Step 14B): one row per user who may read across organizations.

Additive and reversible. No row is created here: an operator grants the role in the database.

Revision ID: 0052
Revises: 0051
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_platform_admins_user_id"),
        sa.ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                                ondelete="CASCADE", name="fk_platform_admins_user_org"),
    )
    op.create_index("ix_platform_admins_organization_id", "platform_admins", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_platform_admins_organization_id", table_name="platform_admins")
    op.drop_table("platform_admins")
