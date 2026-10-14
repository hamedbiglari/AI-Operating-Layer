"""
QueryGroup: a curated bucket of semantically related queries the
business has decided to treat as one unit (master spec section 25) —
"how to know if taranjabin is authentic" might group five differently-
worded queries that all deserve ONE page/section, not five.

QueryGroup is deliberately NOT "Knowledge Need" (see
app/services/query_group_service.py's module docstring for the full
reasoning) — a group is a curated bucket of queries (this table); a
Knowledge Need is a judgment computed at read time about whether that
bucket is adequately served by existing Knowledge/Evidence. Conflating
them would mean every QueryGroup automatically implies a content gap,
which is false.

`updated_at` is the one addition beyond section 25's literal field
list, justified the same way as everywhere else in this codebase:
every mutable tenant-owned table uses TimestampMixin, and a group's
`name`/`priority` are mutable.
"""

import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import IntentType, QueryPriority


class QueryGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "query_groups"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    primary_intent: Mapped[IntentType] = mapped_column(
        SAEnum(IntentType, name="intent_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    target_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    priority: Mapped[QueryPriority] = mapped_column(
        SAEnum(QueryPriority, name="query_priority", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=QueryPriority.MEDIUM,
        server_default=QueryPriority.MEDIUM.value,
    )

    members: Mapped[list["QueryGroupMembership"]] = relationship(  # noqa: F821
        back_populates="query_group", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QueryGroup id={self.id} name={self.name!r} primary_intent={self.primary_intent.value}>"
