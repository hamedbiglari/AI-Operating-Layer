"""
QueryClusterMembership: a pure join table for *automatic* similarity
assignment — deliberately the same shape as QueryGroupMembership but a
separate table, because it answers a different question (machine
similarity vs. curated business grouping). See QueryCluster's and
QueryGroupMembership's docstrings for the full reasoning against
merging these into one table with a "type" flag: they have different
write paths (this one is replaced wholesale every time
`query_cluster_service.cluster_queries` runs; QueryGroupMembership
rows are added/removed one at a time by a human), and conflating them
would make an automatic re-clustering run silently affect curated
membership.

`score` is nullable: the n-gram clustering algorithm (see
app/services/query_cluster_service.py) records each member's Jaccard
similarity to its cluster's representative query; a future embedding-
based algorithm would populate the same column with a different
similarity metric, no schema change required.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow


class QueryClusterMembership(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "query_cluster_members"
    __table_args__ = (
        UniqueConstraint("query_cluster_id", "query_id", name="uq_query_cluster_members_cluster_id_query_id"),
    )

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utcnow, nullable=False)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("query_clusters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    query_cluster: Mapped["QueryCluster"] = relationship(back_populates="members")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QueryClusterMembership cluster_id={self.query_cluster_id} query_id={self.query_id}>"
