"""
Website management (ADR-118): the marketing site's blog, page sections and newsletter list, administered from
the main dashboard and read by the public site through a small unauthenticated API.

    SitePost ──< SitePostRevision        every edit of a post is kept (prompt §41: update history)
    SiteSection                          which blocks a page shows, in which order, per language
    NewsletterSubscriber                 consent-first: no row without explicit consent; unsubscribe by token

Posts exist per language. An English post and its Persian translation share a `translation_group`, so the site
can link one to the other (hreflang) without guessing from slugs.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

SITE_LANGUAGES = ("en", "fa")
POST_STATUSES = ("draft", "published", "archived")
SUBSCRIBER_STATUSES = ("subscribed", "unsubscribed")


def _q(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class SitePost(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "site_posts"
    __table_args__ = (
        CheckConstraint(f"lang IN ({_q(SITE_LANGUAGES)})", name="lang"),
        CheckConstraint(f"status IN ({_q(POST_STATUSES)})", name="status"),
        # a published post must say when it was published and who wrote it
        CheckConstraint("status <> 'published' OR (published_at IS NOT NULL AND author_name IS NOT NULL)",
                        name="published_needs_date_and_author"),
        UniqueConstraint("organization_id", "lang", "slug", name="uq_site_post_slug"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    lang: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    translation_group: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    tags: Mapped[list | None] = mapped_column(JSON)
    references: Mapped[list | None] = mapped_column(JSON)          # [{title, publisher, url, accessed}]
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SitePostRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "site_post_revisions"
    __table_args__ = (UniqueConstraint("post_id", "version", name="uq_site_post_revision"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("site_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class SiteSection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "site_sections"
    __table_args__ = (
        CheckConstraint(f"lang IN ({_q(SITE_LANGUAGES)})", name="lang"),
        UniqueConstraint("organization_id", "page", "lang", "section_key", name="uq_site_section"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    page: Mapped[str] = mapped_column(String(50), nullable=False, default="home")
    lang: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    section_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    heading: Mapped[str | None] = mapped_column(String(300))          # optional override of the section title
    subheading: Mapped[str | None] = mapped_column(Text)


class NewsletterSubscriber(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "newsletter_subscribers"
    __table_args__ = (
        CheckConstraint(f"status IN ({_q(SUBSCRIBER_STATUSES)})", name="status"),
        CheckConstraint("consented_at IS NOT NULL", name="consent_required"),
        CheckConstraint("status <> 'unsubscribed' OR unsubscribed_at IS NOT NULL", name="unsubscribe_has_date"),
        UniqueConstraint("organization_id", "email", name="uq_newsletter_email"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    lang: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="subscribed")
    source: Mapped[str | None] = mapped_column(String(200))           # the page the form was on
    consent_text: Mapped[str] = mapped_column(Text, nullable=False)
    consented_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    unsubscribe_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
