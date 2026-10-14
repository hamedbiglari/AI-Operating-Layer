"""
Query: one deduplicated unit of search/demand signal (master spec
section 23) — "قیمت ترنجبین", "taranjabin benefits", etc. `query` is
the exact, spec-literal field: the canonical, human-readable form of
this demand signal, immutable once set.

Two additive fields beyond section 23's literal list, both justified
in docs/DECISIONS.md ADR-015:

- `normalized_query`: a deterministic, derived dedup/match key (lower-
  cased, whitespace-collapsed). Section 23 requires `query` to exist
  but is silent on how dedup works — this is the same kind of addition
  as `Document.content_hash` (Phase 3): a derived column the service
  layer needs for a deterministic comparison, not a replacement of the
  spec field it's derived from.
- `discovered_at` is spec-literal and is NOT the same as `created_at`
  (TimestampMixin): `discovered_at` is a domain fact — when this demand
  was first observed in the real world — and can legitimately be
  backdated when importing historical Search Console/CSV data;
  `created_at` is simply when this row was inserted into this database.

The exact string as it appeared in one specific import/source event
(which can differ slightly from the canonical `query` — typos,
casing — even across occurrences that all resolve to the same
`normalized_query`) lives on QueryProvenance, never here.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import QueryPriority, QuerySource, QueryStatus


class Query(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "queries"
    __table_args__ = (
        UniqueConstraint("organization_id", "normalized_query", name="uq_queries_organization_normalized_query"),
        CheckConstraint(
            "search_volume IS NULL OR search_volume >= 0", name="ck_queries_search_volume_non_negative"
        ),
        CheckConstraint(
            "commercial_value IS NULL OR commercial_value >= 0", name="ck_queries_commercial_value_non_negative"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query: Mapped[str] = mapped_column(String(1000), nullable=False)
    normalized_query: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en", server_default="en")
    country: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # First-observed source (see QueryProvenance for the full
    # occurrence history — this column keeps its section-23-literal
    # meaning: ONE source per query, unchanged after creation).
    source: Mapped[QuerySource] = mapped_column(
        SAEnum(QuerySource, name="query_source", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )

    search_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commercial_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    priority: Mapped[QueryPriority] = mapped_column(
        SAEnum(QueryPriority, name="query_priority", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=QueryPriority.MEDIUM,
        server_default=QueryPriority.MEDIUM.value,
    )
    status: Mapped[QueryStatus] = mapped_column(
        SAEnum(QueryStatus, name="query_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=QueryStatus.DISCOVERED,
        server_default=QueryStatus.DISCOVERED.value,
        index=True,
    )
    discovered_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utcnow, nullable=False)

    provenance: Mapped[list["QueryProvenance"]] = relationship(  # noqa: F821
        back_populates="query", cascade="all, delete-orphan"
    )
    intents: Mapped[list["Intent"]] = relationship(  # noqa: F821
        back_populates="query", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Query id={self.id} query={self.query!r} status={self.status.value}>"
