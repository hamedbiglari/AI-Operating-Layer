"""
Site: a website/property owned by an Organization (master spec section
10). A single organization may have multiple sites. Sites are the future
attachment point for Knowledge, Products, Queries, etc. (Phase 2+).
"""

import uuid

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SitePlatform, SiteStatus


class Site(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("organization_id", "domain", name="uq_sites_organization_domain"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[SitePlatform] = mapped_column(
        SAEnum(SitePlatform, name="site_platform", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SitePlatform.WORDPRESS,
    )
    wordpress_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    woo_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[SiteStatus] = mapped_column(
        SAEnum(SiteStatus, name="site_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SiteStatus.ACTIVE,
        server_default=SiteStatus.ACTIVE.value,
    )

    organization: Mapped["Organization"] = relationship(back_populates="sites")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Site id={self.id} domain={self.domain!r} org={self.organization_id}>"
