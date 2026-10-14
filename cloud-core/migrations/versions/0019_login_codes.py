"""Email one-time login codes (owner requirement; phases 1/13, closed in the
final existing-owner closure pass — not a new phase).

Revision ID: 0019
Revises: 0018
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_foreign_key("fk_login_codes_user_org", "login_codes", "users",
                          ["user_id", "organization_id"], ["id", "organization_id"], ondelete="CASCADE")
    op.create_index("ix_login_codes_user_id", "login_codes", ["user_id"])
    op.create_index("ix_login_codes_organization_id", "login_codes", ["organization_id"])
    op.create_table(
        "login_code_throttles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resend_available_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lock_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


    op.create_foreign_key("fk_login_code_throttles_user_org", "login_code_throttles", "users",
                          ["user_id", "organization_id"], ["id", "organization_id"], ondelete="CASCADE")
    op.create_index("ix_login_code_throttles_organization_id", "login_code_throttles", ["organization_id"])


def downgrade() -> None:
    op.drop_table("login_code_throttles")
    op.drop_table("login_codes")
