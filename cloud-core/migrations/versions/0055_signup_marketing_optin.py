"""Product-updates consent given at sign-up (V5-signup-marketing-optin): a flag on the pending sign-up, then the date of
consent on the owner (users.marketing_optin_at; null = no consent).

Additive and reversible. No existing row is touched (users gets a nullable column; signup_codes a flag defaulting to false).

Revision ID: 0055
Revises: 0054
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("marketing_optin_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("signup_codes", sa.Column("marketing_optin", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("signup_codes", "marketing_optin")
    op.drop_column("users", "marketing_optin_at")
