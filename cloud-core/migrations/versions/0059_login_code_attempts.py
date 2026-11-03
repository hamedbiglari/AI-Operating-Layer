"""Wrong guesses counted per issued login code (SEC-login-code-lockout, option B).

Each emailed code is bound to the challenge returned when it was requested (the code row's own id), and wrong
guesses are counted on that row: too many cancel that one code, never the account. Additive and reversible; existing
rows start at 0. login_code_throttles.lock_level / locked_until are no longer read but are left as they are (data kept
for forensics).

Revision ID: 0059
Revises: 0058
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0059"
down_revision: Union[str, None] = "0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("login_codes", sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("login_codes", "failed_attempts")
