"""
Demand Intelligence (REQ-DI-001/002/003, ADR-099).

Distinct sources stay distinct (source_type) and are normalised into one
queryable DemandSignal shape. Only data that actually entered the system is
stored: first-party internal search (telemetry), an owner-uploaded Search
Console export, and — once OAuth credentials exist — live GSC / GA4 syncs.
Nothing is estimated or invented; unknown metrics stay NULL.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

DEMAND_SOURCES = ("gsc", "gsc_export", "ga4", "internal_search", "ai_visibility", "customer_query", "product_behavior")
CONNECTABLE_SOURCES = ("gsc", "ga4")
CONNECTION_STATES = ("NOT_CONNECTED", "CONNECTED", "ERROR", "BLOCKED_EXTERNAL_DEPENDENCY")
SIGNAL_STATES = ("new", "promoted", "dismissed")


def _in(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class DemandConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "demand_connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_type", name="uq_demand_connection_source"),
        CheckConstraint(f"source_type IN ({_in(CONNECTABLE_SOURCES)})", name="ck_demand_connection_source"),
        CheckConstraint(f"status IN ({_in(CONNECTION_STATES)})", name="ck_demand_connection_status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="NOT_CONNECTED")
    property_ref: Mapped[str | None] = mapped_column(String(500))       # e.g. GSC site URL / GA4 property id
    last_sync_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DemandSignal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "demand_signals"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_type", "dedupe_key", name="uq_demand_signal_dedupe"),
        CheckConstraint(f"source_type IN ({_in(DEMAND_SOURCES)})", name="ck_demand_signal_source"),
        CheckConstraint(f"status IN ({_in(SIGNAL_STATES)})", name="ck_demand_signal_status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(600), nullable=False)
    query_text: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_query: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    # search-engine metrics (GSC); NULL when the source does not provide them
    impressions: Mapped[int | None] = mapped_column(Integer)
    clicks: Mapped[int | None] = mapped_column(Integer)
    ctr: Mapped[float | None] = mapped_column(Numeric(8, 5))
    position: Mapped[float | None] = mapped_column(Numeric(8, 2))
    page: Mapped[str | None] = mapped_column(String(1000))
    country: Mapped[str | None] = mapped_column(String(10))
    device: Mapped[str | None] = mapped_column(String(20))
    # first-party behaviour metrics; NULL when not applicable
    searches: Mapped[int | None] = mapped_column(Integer)
    zero_result_searches: Mapped[int | None] = mapped_column(Integer)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    observed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    raw: Mapped[dict | None] = mapped_column(JSON)                      # the untouched imported row
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    information_need: Mapped[str | None] = mapped_column(Text)
    research_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_tasks.id", ondelete="SET NULL"))
