"""
QueryCluster: the output of automatic, similarity-based grouping
(master spec section 25: "The system should cluster semantically
related queries"). Not a section-25-literal table — section 25 only
names `query_groups`/`query_group_members`, which are CURATED buckets
a human or the business defines. QueryCluster is the other half of
that sentence: an automatically computed grouping, kept in its own
table rather than writing directly into `query_groups`, because a
cluster is a machine-computed *candidate* for grouping, not itself a
curated decision — collapsing the two would mean every automatic
similarity match silently became an authoritative QueryGroup with no
human step in between.

`QueryGroup`'s relationship to one or more `QueryCluster`s is
deliberately NOT stored directly (no `cluster_id` on
`QueryGroupMembership`) — see QueryGroupMembership's docstring and
`app/services/query_cluster_service.py` for why: it's derived at read
time instead, so there is exactly one source of truth for "which
cluster is this query in" (this table), not two that could diverge.
"""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class QueryCluster(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "query_clusters"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # A short, human-scannable label — the cluster's own most
    # representative query text (longest/most central member) at
    # clustering time, editable later by a human. Nullable only for
    # the brief window between insert and the clustering algorithm
    # assigning an initial label in the same transaction.
    label: Mapped[str | None] = mapped_column(String(300), nullable=True)

    members: Mapped[list["QueryClusterMembership"]] = relationship(  # noqa: F821
        back_populates="query_cluster", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QueryCluster id={self.id} label={self.label!r}>"
