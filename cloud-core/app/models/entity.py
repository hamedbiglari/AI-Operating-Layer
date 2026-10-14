"""
Entity: a named thing attached to a Knowledge Object (master spec
section 12) — e.g. "Taranjabin" or "Mannitol". `aliases`/`external_ids`
are JSONB because the shape of "what an alternate name or external
identifier looks like" varies by entity_type and must not require a
migration to extend (mirrors the extensibility principle applied to
object_type/entity_type themselves).
"""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Entity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "entities"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Phase 2 decision: required, not nullable. There is no ingestion
    # pipeline yet (that's Phase 3) that would create free-floating
    # entities before they're attached to a Knowledge Object — every
    # entity created via the Phase 2 API is explicitly scoped to one.
    # Revisit nullability if/when Phase 3 needs a staging area.
    knowledge_object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_objects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Extensible vocabulary, plain string per section 11's principle —
    # see app/models/enums.py header comment.
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    aliases: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    external_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en", server_default="en")

    knowledge_object: Mapped["KnowledgeObject"] = relationship(back_populates="entities")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Entity id={self.id} name={self.canonical_name!r} type={self.entity_type!r}>"
