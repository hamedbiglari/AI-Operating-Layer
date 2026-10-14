"""Website management: blog posts with revisions, page sections, newsletter subscribers (ADR-118). Additive.

Revision ID: 0036
Revises: 0035
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)


def _ts():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False)]


def _org():
    return sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


def upgrade() -> None:
    op.create_table("site_posts",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("lang", sa.String(5), nullable=False, server_default="en"),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("translation_group", UUID, index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("excerpt", sa.Text()), sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("author_name", sa.String(200)),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("tags", postgresql.JSON()), sa.Column("references", postgresql.JSON()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"), *_ts(),
        sa.CheckConstraint("lang IN ('en', 'fa')", name="lang"),
        sa.CheckConstraint("status IN ('draft', 'published', 'archived')", name="status"),
        sa.CheckConstraint("status <> 'published' OR (published_at IS NOT NULL AND author_name IS NOT NULL)", name="published_needs_date_and_author"),
        sa.UniqueConstraint("organization_id", "lang", "slug", name="uq_site_post_slug"))
    op.create_table("site_post_revisions",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("post_id", UUID, sa.ForeignKey("site_posts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False), sa.Column("body", sa.Text(), nullable=False),
        sa.Column("note", sa.String(500)),
        sa.Column("changed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")), *_ts(),
        sa.UniqueConstraint("post_id", "version", name="uq_site_post_revision"))
    op.create_table("site_sections",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("page", sa.String(50), nullable=False, server_default="home"),
        sa.Column("lang", sa.String(5), nullable=False, server_default="en"),
        sa.Column("section_key", sa.String(80), nullable=False), sa.Column("label", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("heading", sa.String(300)), sa.Column("subheading", sa.Text()), *_ts(),
        sa.CheckConstraint("lang IN ('en', 'fa')", name="lang"),
        sa.UniqueConstraint("organization_id", "page", "lang", "section_key", name="uq_site_section"))
    op.create_table("newsletter_subscribers",
        sa.Column("id", UUID, primary_key=True), _org(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("lang", sa.String(5), nullable=False, server_default="en"),
        sa.Column("status", sa.String(20), nullable=False, server_default="subscribed"),
        sa.Column("source", sa.String(200)), sa.Column("consent_text", sa.Text(), nullable=False),
        sa.Column("consented_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("unsubscribed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("unsubscribe_token", sa.String(64), nullable=False, unique=True), *_ts(),
        sa.CheckConstraint("status IN ('subscribed', 'unsubscribed')", name="status"),
        sa.CheckConstraint("consented_at IS NOT NULL", name="consent_required"),
        sa.CheckConstraint("status <> 'unsubscribed' OR unsubscribed_at IS NOT NULL", name="unsubscribe_has_date"),
        sa.UniqueConstraint("organization_id", "email", name="uq_newsletter_email"))


def downgrade() -> None:
    for t in ("newsletter_subscribers", "site_sections", "site_post_revisions", "site_posts"):
        op.drop_table(t)
