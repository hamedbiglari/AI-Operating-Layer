"""Finer source access states + user-supplied full text (ADR-107). Additive.

Revision ID: 0028
Revises: 0027
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = "'full_text_available', 'abstract_only', 'metadata_only', 'restricted', 'unavailable', 'unknown'"
NEW = (OLD + ", 'title_only', 'landing_page_only', 'paywalled', 'registration_required', 'access_blocked'")


def upgrade() -> None:
    op.drop_constraint(op.f("ck_sources_content_access"), "sources", type_="check")
    op.create_check_constraint("content_access", "sources", f"content_access IN ({NEW})")
    # how the system came to hold the full text, and who supplied it
    op.add_column("sources", sa.Column("full_text_origin", sa.String(20)))
    op.add_column("sources", sa.Column("full_text_document_id", postgresql.UUID(as_uuid=True),
                                       sa.ForeignKey("documents.id", ondelete="SET NULL")))
    op.add_column("sources", sa.Column("access_checked_at", sa.TIMESTAMP(timezone=True)))
    op.add_column("sources", sa.Column("access_blocked_reason", sa.Text()))
    op.create_check_constraint("full_text_origin", "sources",
                               "full_text_origin IS NULL OR full_text_origin IN ('open_access_fetch', 'user_upload')")
    # a full-text claim must name where the text came from
    op.create_check_constraint("full_text_origin_required", "sources",
                               "NOT full_text_accessed OR full_text_origin IS NOT NULL")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_sources_full_text_origin_required"), "sources", type_="check")
    op.drop_constraint(op.f("ck_sources_full_text_origin"), "sources", type_="check")
    for c in ("access_blocked_reason", "access_checked_at", "full_text_document_id", "full_text_origin"):
        op.drop_column("sources", c)
    op.execute(f"UPDATE sources SET content_access = 'unknown' WHERE content_access NOT IN ({OLD})")
    op.drop_constraint(op.f("ck_sources_content_access"), "sources", type_="check")
    op.create_check_constraint("content_access", "sources", f"content_access IN ({OLD})")
