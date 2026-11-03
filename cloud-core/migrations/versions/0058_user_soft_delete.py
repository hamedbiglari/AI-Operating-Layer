"""User soft delete for the admin trash (V5-admin-trash): when a user was deleted and by whom.

Additive and reversible. No existing row is touched: both columns are nullable (NULL = not deleted). deleted_by_id
points at the platform admin who deleted the user; it is cleared (SET NULL) if that admin is ever purged.

Revision ID: 0058
Revises: 0057
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deleted_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_users_deleted_by_id_users", "users", "users", ["deleted_by_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_users_deleted_at", "users", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_users_deleted_at", table_name="users")
    op.drop_constraint("fk_users_deleted_by_id_users", "users", type_="foreignkey")
    op.drop_column("users", "deleted_by_id")
    op.drop_column("users", "deleted_at")
