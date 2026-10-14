"""
WordPressMapping (master spec section 39) — ADAPTER STATE, not
canonical truth.

This table records that a Core object is *projected into* a particular
WordPress post. It is the only place a WordPress concept
(`wordpress_post_id`, `wordpress_post_type`, `wordpress_url`) is
allowed to exist in this codebase, and it exists here precisely so
those concepts never leak into `Product`, `KnowledgeObject`, or any
other Core model (ADR-038).

Direction of truth is fixed and one-way for content: **Core owns the
object; WordPress owns only its own post id.** A mapping row can tell
you where a Core object was published; it can never tell you what the
object *is*. Nothing in Core reads this table to decide anything about
a product or a piece of knowledge.

`object_id` is a polymorphic pointer (see MappedObjectType), resolved
and tenant-checked in the service layer before any row is written —
the same discipline as Relationship, ResearchTaskReference and
TrustRecord.

Idempotency is enforced by the database, not by application logic:
`uq_wordpress_mappings_site_object` makes "this Core object on this
site" unique, and `uq_wordpress_mappings_site_post` makes "this
WordPress post on this site" unique. A webhook delivered five times
therefore produces one row, whatever the application does.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MappedObjectType, SyncStatus


class WordPressMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wordpress_mappings"
    __table_args__ = (
        UniqueConstraint(
            "site_id", "object_type", "object_id", name="uq_wordpress_mappings_site_object"
        ),
        UniqueConstraint(
            "site_id", "wordpress_post_id", name="uq_wordpress_mappings_site_post"
        ),
        # Composite FK (ADR-037): the database itself refuses a mapping
        # whose site belongs to a different organization. Not left to
        # the service layer to remember.
        ForeignKeyConstraint(
            ["site_id", "organization_id"],
            ["sites.id", "sites.organization_id"],
            name="fk_wordpress_mappings_site_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["installation_id", "organization_id"],
            ["installations.id", "installations.organization_id"],
            name="fk_wordpress_mappings_installation_organization",
            ondelete="SET NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # Which installation last wrote this mapping, for audit. Nullable
    # so that revoking an installation doesn't delete the mapping.
    installation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    object_type: Mapped[MappedObjectType] = mapped_column(
        SAEnum(MappedObjectType, name="mapped_object_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    wordpress_post_id: Mapped[int] = mapped_column(Integer, nullable=False)
    wordpress_post_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    wordpress_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    sync_status: Mapped[SyncStatus] = mapped_column(
        SAEnum(SyncStatus, name="sync_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SyncStatus.PENDING,
        server_default=SyncStatus.PENDING.value,
        index=True,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # When WordPress last reported the post changed on its side. Purely
    # informational: Core never treats this as authority over its own
    # object.
    remote_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<WordPressMapping site={self.site_id} {self.object_type.value}:{self.object_id} "
            f"-> wp_post {self.wordpress_post_id} ({self.sync_status.value})>"
        )
