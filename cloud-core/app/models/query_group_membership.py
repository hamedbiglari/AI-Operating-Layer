"""
QueryGroupMembership: `query_group_members` (master spec section 25) —
exactly the two-column link the spec describes (`query_group_id`,
`query_id`), plus the same UUID-primary-key/organization_id/created_at
scaffolding every other link table in this codebase carries (ClaimEvidence
being the closest precedent: section 18's literal `claim_evidence`
field list was just `claim_id, evidence_id, relation_type`, yet it also
got a full `id`/`organization_id`/timestamps per section 8's blanket
"use UUID primary keys" rule and this project's own established
convention).

No `updated_at`: membership either exists or it doesn't - there is
nothing on this row to edit in place, only to add or remove.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow


class QueryGroupMembership(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "query_group_members"
    __table_args__ = (
        UniqueConstraint("query_group_id", "query_id", name="uq_query_group_members_group_id_query_id"),
    )

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utcnow, nullable=False)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("query_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("queries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    query_group: Mapped["QueryGroup"] = relationship(back_populates="members")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QueryGroupMembership group_id={self.query_group_id} query_id={self.query_id}>"
