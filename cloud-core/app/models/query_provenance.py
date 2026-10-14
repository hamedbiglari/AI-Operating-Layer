"""
QueryProvenance: one occurrence of a Query being observed from a
specific source event — a single CSV row, a single Search Console
data point, a single manual entry. Not a section-23-literal table;
additive, per docs/DECISIONS.md ADR-015.

Why this exists: `Query.source` (section 23) holds exactly one value —
the first-observed source — but the same demand signal legitimately
gets re-observed from multiple sources over time (e.g. first imported
from a CSV, later also seen in Search Console). A single column can't
hold that history without being overwritten and losing it; this table
is the append-only occurrence log, deliberately NOT collapsed into
`Query` itself.

`raw_query` is the exact string as it appeared in THIS occurrence,
which can differ slightly (typos, casing, extra whitespace) from the
canonical, deduplicated `Query.query` even when both resolve to the
same `normalized_query` — this is where that per-occurrence variation
is preserved rather than silently lost at import time.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Enum as SAEnum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import QuerySource


class QueryProvenance(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "query_provenance"

    # created_at only, no TimestampMixin - an immutable occurrence
    # record, never edited in place, same pattern already established
    # for ResearchTaskReference (Phase 5).
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utcnow, nullable=False)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[QuerySource] = mapped_column(
        SAEnum(QuerySource, name="query_source", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    raw_query: Mapped[str] = mapped_column(Text, nullable=False)
    # Open, per-occurrence extras (e.g. originating filename, source
    # row number, Search-Console-specific columns) - same rationale as
    # Source.metadata_: shape varies by source, must not require a
    # migration to extend.
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    query: Mapped["Query"] = relationship(back_populates="provenance")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QueryProvenance query_id={self.query_id} source={self.source.value}>"
