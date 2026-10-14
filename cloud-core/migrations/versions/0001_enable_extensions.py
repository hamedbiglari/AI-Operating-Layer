"""enable required postgres extensions

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00

Phase 0: no domain tables yet. This migration only enables the
extensions every later phase depends on: pgvector for embeddings
(section 15/53) and pgcrypto/uuid-ossp as a fallback for UUID
generation if the app layer ever needs DB-side defaults.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')


def downgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
    op.execute("DROP EXTENSION IF EXISTS vector")
