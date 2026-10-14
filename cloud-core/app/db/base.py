"""
SQLAlchemy 2.x declarative base.

Every ORM model in the system inherits from `Base`. A fixed naming
convention is applied so Alembic autogenerate produces stable,
predictable constraint/index names across the whole schema.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import MetaData, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UUIDPrimaryKeyMixin:
    """Standard UUID primary key used by every entity in the system (see
    section 8 of the master spec: 'Use UUID primary keys')."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Standard TIMESTAMPTZ created_at/updated_at columns (see section 8:
    'Use TIMESTAMPTZ for timestamps')."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
