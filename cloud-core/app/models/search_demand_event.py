"""
Search demand events (Phase 13, ADR-081).

WHAT THE OWNER ASKED FOR

"I need to know what a user — or a bot — was looking for, and record it,
so I can improve the service." That is demand intelligence: not what our
pages rank for (Phase 12 owns that), but what someone came here *wanting*.

THE THING THIS TABLE DELIBERATELY DOES NOT HAVE

**A query text column.** A search query IS a `Query` (Phase 6). Phase 12
established this when it built `SearchObservation` on `query_id` rather
than minting a `SERPQuery`, and the same rule holds here: this table
stores `query_id` and nothing else about the text. That is what makes the
two systems answer one question together — "this term is searched on our
site 40 times a week, we rank 19th for it, and it has no knowledge object"
— instead of three tables holding three spellings of the same string.

Recording a search therefore goes through `query_service`: find-or-create
the canonical `Query` by `normalized_query`, append a `QueryProvenance`
occurrence, then write the row here. The Phase 6 lifecycle
(DISCOVERED → CLASSIFIED) is untouched and still driven by Intent, not by
this table.

WHY BOT SEARCHES AND HUMAN SEARCHES SHARE A TABLE

Because the merchant's question — "what is being asked for that we do not
answer?" — has the same shape either way, and because the answer changes
if you cannot compare them. `actor_type` and `ai_agent_id` keep them
separable; a `bot_searches` table would have made the comparison a join
nobody writes.

RESULT COUNT IS NULLABLE

`result_count = 0` means "we searched and found nothing" — the most
valuable row in the table, because it is a content gap with a timestamp.
NULL means the adapter did not report it. Collapsing those two would
destroy exactly the signal this table exists to capture.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ActorType, SearchDemandSource


def _enum(cls, name):
    return SAEnum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class SearchDemandEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "search_demand_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "event_key",
            name="uq_search_demand_events_organization_event_key",
        ),
        # The canonical Phase 6 Query, tenant-composite as everywhere else.
        ForeignKeyConstraint(
            ["query_id", "organization_id"],
            ["queries.id", "queries.organization_id"],
            name="fk_search_demand_events_query_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["ai_agent_id", "organization_id"],
            ["ai_agents.id", "ai_agents.organization_id"],
            name="fk_search_demand_events_ai_agent_organization",
            ondelete="SET NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    event_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # The canonical Query. No text column here on purpose - see docstring.
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    demand_source: Mapped[SearchDemandSource] = mapped_column(
        _enum(SearchDemandSource, "search_demand_source"), nullable=False, index=True
    )
    actor_type: Mapped[ActorType] = mapped_column(
        _enum(ActorType, "actor_type"), nullable=False, index=True
    )
    ai_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    # 0 = searched, found nothing. NULL = not reported. Not the same.
    result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The page the search was performed from, if any.
    path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    geo_country: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)

    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SearchDemandEvent query={self.query_id} {self.actor_type.value} "
            f"results={self.result_count}>"
        )
