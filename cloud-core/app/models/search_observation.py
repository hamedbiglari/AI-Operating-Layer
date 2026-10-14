"""
Search Intelligence observations (P12-19, ADR-075).

WHY THIS IS A SEPARATE TABLE FROM `visibility_tests`

Search and AI visibility are different observation domains and the contract
forbids collapsing them (§12). The evidence is in the columns: a search
observation has a POSITION, a URL and a result type; an AI observation has
mention/citation/recommendation tri-states. Neither set is meaningful for
the other, and a single table would be half-null in every row with no way
to tell which half was legitimately empty.

They share `query_id` — the canonical Phase 6 `Query` — plus market and
language. That is the correct amount of sharing: same question, different
kind of answer.

WHAT IS REUSED

    Query           canonical Phase 6 model. NOT duplicated. There is no
                    SearchQuery/SERPQuery table; a search query IS a query.
    Job lifecycle   SyncJob (ADR-068)
    Budget          VisibilityBudget (ADR-069)

APPEND-ONLY

Historical observations are never updated. A re-import for the same day
produces a new row with a new `collected_at`; overwriting would destroy the
history the whole feature exists to provide (§23).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    TIMESTAMP,
    Date,
    Enum as SAEnum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SearchDataSource, SearchResultType, SearchSurface


def _enum(cls, name):
    return SAEnum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class SearchObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One observed search datum for one query, market and day.

    EVERY METRIC IS NULLABLE, and that is the point. Search Console
    supplies impressions/clicks/CTR but no URL ranking for some rows; a
    SERP provider supplies position and URL but never impressions. A zero
    would claim "measured, and it was none"; NULL says "this source does
    not report it" (§24).
    """

    __tablename__ = "search_observations"
    __table_args__ = (
        # Append-only history: one row per (query, source, surface, market,
        # language, date, position). A re-import of the same day with the
        # same shape is idempotent; genuinely new data gets a new row.
        UniqueConstraint(
            "organization_id", "query_id", "data_source", "surface",
            "market", "language", "observed_date", "position",
            name="uq_search_observations_identity",
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(
            ["query_id", "organization_id"], ["queries.id", "queries.organization_id"],
            name="fk_search_observations_query_organization", ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # The canonical Query. NOT a copy of the query text - the text lives on
    # Query and is read through this reference.
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    data_source: Mapped[SearchDataSource] = mapped_column(
        _enum(SearchDataSource, "search_data_source"), nullable=False, index=True
    )
    surface: Mapped[SearchSurface] = mapped_column(
        _enum(SearchSurface, "search_surface"), nullable=False,
        default=SearchSurface.GOOGLE_WEB, server_default=SearchSurface.GOOGLE_WEB.value,
    )
    market: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String(12), nullable=True)
    device: Mapped[str | None] = mapped_column(String(16), nullable=True)

    observed_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # --- SERP-shaped fields (NULL for Search Console rows) ---
    position: Mapped[float | None] = mapped_column(Float, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    result_type: Mapped[SearchResultType | None] = mapped_column(
        _enum(SearchResultType, "search_result_type"), nullable=True
    )

    # --- Search Console-shaped fields (NULL for SERP rows) ---
    impressions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- provenance ---
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    # True when the row came from a fixture rather than a live provider.
    # §44 forbids fixture data masquerading as live observation, and this
    # is how a consumer tells them apart.
    is_fixture: Mapped[bool] = mapped_column(
        default=False, server_default="false", nullable=False
    )
    collected_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SearchObservation {self.data_source.value} pos={self.position} "
            f"impr={self.impressions} {self.observed_date}>"
        )
