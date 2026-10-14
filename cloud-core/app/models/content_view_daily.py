"""
Daily content rollup (Phase 13, ADR-080).

WHY A ROLLUP TABLE EXISTS AT ALL

The owner's requirement is "sort my content by how often it was seen,
least to most and the other way round, with the numbers". That is an
ORDER BY over a COUNT over every page view ever recorded. Doing it live
means a full aggregate scan on every dashboard load, which is exactly the
anti-pattern the performance gate (§18) names: it would work fine on the
demo data and fall over on the real thing.

So the counts are rolled up once per (site, path, day) and the report
sorts the rollup. The rollup is derived data with a stated derivation,
not a second source of truth: `page_views` remains authoritative and the
rollup can be dropped and rebuilt from it at any time. `recomputed_at`
records when that last happened, and the dashboard shows it — a stale
rollup must be visible as stale, not silently served as current
(checkpoint §68).

WHY THE COUNTS ARE SPLIT

    human_views      probable human browsers
    ai_crawler_views indexing for later
    ai_answer_views  an AI fetching to answer a live question
    agent_views      an agent acting for a person
    search_views     conventional search crawlers
    unknown_views    unclassified

A single `views` column with a `bot_views` companion was the obvious
smaller design and is wrong for this product: "an AI quoted this page to
a customer 400 times this week" and "a training crawler took a copy" are
the two facts the merchant is trying to tell apart, and a bot/human split
collapses them into one number. The total is derived by summing, so no
column can disagree with the total.

DWELL IS SUMMED AND COUNTED SEPARATELY

`dwell_ms_total` pairs with `dwell_samples` rather than storing an
average, because averaging at write time loses the ability to re-average
over a different window, and because a mean over 3 samples and a mean over
3,000 are not the same claim. The dashboard divides and says how many
samples it divided by.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ContentViewDaily(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_view_daily"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "site_id",
            "path",
            "view_date",
            name="uq_content_view_daily_identity",
            postgresql_nulls_not_distinct=True,
        ),
        ForeignKeyConstraint(
            ["site_id", "organization_id"],
            ["sites.id", "sites.organization_id"],
            name="fk_content_view_daily_site_organization",
            ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    path: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    content_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    view_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    human_views: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    ai_crawler_views: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    ai_answer_views: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    agent_views: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    search_views: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    unknown_views: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    # Denormalised sum of the six above. Written by the same function that
    # writes them, asserted equal by a test and by a mutation case, so it
    # cannot drift into being a seventh independent number.
    total_views: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0", index=True)

    blocked_views: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    payment_required_views: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )

    dwell_ms_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    dwell_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    distinct_countries: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    recomputed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    @property
    def mean_dwell_ms(self) -> float | None:
        """None, not 0, when nothing reported a dwell. The caller renders
        *Not available*."""
        if self.dwell_samples == 0:
            return None
        return self.dwell_ms_total / self.dwell_samples

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ContentViewDaily {self.path} {self.view_date} total={self.total_views}>"
