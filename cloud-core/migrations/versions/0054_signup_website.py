"""Optional company website given at sign-up (V5-signup-website-field): kept on the pending sign-up and then on the organization.

Additive and reversible. No existing row is touched (both columns are nullable).

Revision ID: 0054
Revises: 0053
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("website", sa.String(255), nullable=True))
    op.add_column("signup_codes", sa.Column("website", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("signup_codes", "website")
    op.drop_column("organizations", "website")
