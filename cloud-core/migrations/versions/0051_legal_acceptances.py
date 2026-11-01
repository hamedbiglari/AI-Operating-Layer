"""Legal acceptance at sign-in (ADR-139): one row per (user, terms version).

Additive and reversible.

Revision ID: 0051
Revises: 0050
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051"
down_revision: Union[str, None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "legal_acceptances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("terms_version", sa.String(40), nullable=False),
        sa.Column("consents", sa.JSON(), nullable=False),
        sa.Column("client_platform", sa.String(20), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "terms_version", name="uq_legal_acceptances_user_version"),
        sa.ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                                ondelete="CASCADE", name="fk_legal_acceptances_user_org"),
    )
    op.create_index("ix_legal_acceptances_organization_id", "legal_acceptances", ["organization_id"])
    op.create_index("ix_legal_acceptances_user_id", "legal_acceptances", ["user_id"])


def downgrade() -> None:
    op.drop_table("legal_acceptances")
