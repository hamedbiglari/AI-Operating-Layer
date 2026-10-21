"""Browser sessions: the rotating refresh token behind the website's HttpOnly session cookie (ADR-129).
Additive and reversible — no existing table or column is changed.

Revision ID: 0041
Revises: 0040
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)

# Mirrors app/models/auth_session.py — the only words a revoked session may give for itself.
REVOKED_REASONS = ("logout", "reuse_detected", "expired")


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("user_id", UUID, nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        # The secret the last rotation replaced, accepted only until previous_until, so two tabs
        # refreshing at the same moment are not mistaken for a replay.
        sa.Column("previous_token_hash", sa.String(64)),
        sa.Column("previous_until", sa.TIMESTAMP(timezone=True)),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("rotations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("revoked_reason", sa.String(20)),
        sa.Column("user_agent", sa.String(200)),
        sa.Column("ip", sa.String(64)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                                ondelete="CASCADE", name="fk_auth_sessions_user_org"),
        sa.CheckConstraint(
            # The IS NOT NULL is load-bearing: NULL IN (...) is NULL, and a CHECK that evaluates
            # to NULL passes, so without it a revoked row with no reason would slip through.
            "(revoked_at IS NULL AND revoked_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revoked_reason IS NOT NULL AND revoked_reason IN ("
            + ", ".join(f"'{r}'" for r in REVOKED_REASONS) + "))",
            # Short name on purpose: the metadata naming convention adds the "ck_auth_sessions_"
            # prefix, so spelling it out here would produce it twice and the migrated name would
            # no longer match what the model declares.
            name="revoked_rows_say_why"),
    )
    op.create_index("ix_auth_sessions_user_live", "auth_sessions", ["user_id", "revoked_at"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_live", table_name="auth_sessions")
    op.drop_table("auth_sessions")
