"""
Relationship: a generic graph edge (master spec section 19). "Initial
graph implementation should use PostgreSQL relational tables" (no Neo4j
in MVP) - this table IS that implementation.

Design decision beyond the literal field list: the spec gives
subject_id/object_id as bare UUIDs with no type information. A
relational graph edge that can point at more than one kind of node
(Entity, KnowledgeObject, and eventually Product/Source/etc.) cannot be
a real foreign key - Postgres has no "FK into one of several tables"
mechanism. subject_type/object_type were added so the service layer can
resolve and tenant-check the referenced row against the correct table
(see app/services/relationship_service.py). This is the standard,
practical way to model a polymorphic graph edge in a relational
database, and it is exactly what enables a clean migration to a real
graph database later without changing the conceptual model.

source_id intentionally has no FK constraint in the Phase 2 migration:
the `sources` table did not exist yet. Phase 3's migration
(0004_sources_documents_chunks) adds the deferred foreign key via
`ALTER TABLE relationships ADD CONSTRAINT ...` without touching this
column's nullability or any existing data.
"""

import uuid

from sqlalchemy import Enum as SAEnum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import GraphNodeType, RelationshipStatus


class Relationship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "relationships"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    subject_type: Mapped[GraphNodeType] = mapped_column(
        SAEnum(GraphNodeType, name="graph_node_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Extensible vocabulary (e.g. "contains", "related_to", "part_of") -
    # plain string, same rationale as elsewhere.
    predicate: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    object_type: Mapped[GraphNodeType] = mapped_column(
        SAEnum(GraphNodeType, name="graph_node_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[RelationshipStatus] = mapped_column(
        SAEnum(RelationshipStatus, name="relationship_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RelationshipStatus.ACTIVE,
        server_default=RelationshipStatus.ACTIVE.value,
    )

    # created_at only, per the literal field list in section 19 (no
    # updated_at) - but TimestampMixin gives us both, and having
    # updated_at costs nothing while paying off the moment someone edits
    # confidence/status on an existing edge and wants to know when.

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Relationship {self.subject_type.value}:{self.subject_id} -{self.predicate}-> {self.object_type.value}:{self.object_id}>"
