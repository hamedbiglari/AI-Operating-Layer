"""Pending sign-in email changes (V5-self-email-verification): a code sent to the new address confirms the change.

Additive and reversible. No existing row is touched.

Revision ID: 0053
Revises: 0052
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_change_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("new_email", sa.String(320), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                                ondelete="CASCADE", name="fk_email_change_requests_user_org"),
    )
    op.create_index("ix_email_change_requests_user_id", "email_change_requests", ["user_id"])
    op.create_index("ix_email_change_requests_organization_id", "email_change_requests", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_email_change_requests_organization_id", table_name="email_change_requests")
    op.drop_index("ix_email_change_requests_user_id", table_name="email_change_requests")
    op.drop_table("email_change_requests")
