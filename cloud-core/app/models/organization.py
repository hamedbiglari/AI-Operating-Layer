"""
Organization: the tenant root.

Every tenant-owned table elsewhere in the system carries organization_id
as a foreign key back to this table (master spec section 8: "Tenant
isolation is mandatory"). Organizations are never hard-deleted — status
transitions to CANCELLED instead (soft-delete/archive semantics).
"""

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OrganizationStatus


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    status: Mapped[OrganizationStatus] = mapped_column(
        SAEnum(OrganizationStatus, name="organization_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=OrganizationStatus.ACTIVE,
        server_default=OrganizationStatus.ACTIVE.value,
    )

    users: Mapped[list["User"]] = relationship(  # noqa: F821
        back_populates="organization", cascade="all, delete-orphan"
    )
    sites: Mapped[list["Site"]] = relationship(  # noqa: F821
        back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Organization id={self.id} slug={self.slug!r} status={self.status.value}>"
