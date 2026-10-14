"""
KnowledgeObject: the canonical semantic abstraction (master spec section
11). NOT an article — a Knowledge Object is the source from which many
outputs (article, FAQ, comparison, buying guide, structured data, AI
response, product explanation) can later be generated. Phase 2 only
implements the object itself plus its authoring lifecycle; generating
those outputs is a later phase.
"""

import uuid

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import KnowledgeObjectStatus


class KnowledgeObject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_objects"
    __table_args__ = (
        # Phase 17: composite tenant-FK target for ai_executions (ADR-037).
        UniqueConstraint("id", "organization_id", name="uq_knowledge_objects_id_organization_id"),
        UniqueConstraint("organization_id", "slug", name="uq_knowledge_objects_organization_slug"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), nullable=False)

    # Deliberately a plain string, not a DB enum — master spec section 11:
    # "This list must be extensible" (plant, food, compound, disease,
    # condition, concept, person, organization, product, brand, place,
    # study, method, topic, ...). Indexed per section 53.
    object_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # ADR-114: a topic may belong to a Category, which carries its section schema. Nullable on purpose —
    # every Knowledge Object that existed before categories keeps working untouched, and `object_type`
    # stays exactly as it was.
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[KnowledgeObjectStatus] = mapped_column(
        SAEnum(KnowledgeObjectStatus, name="knowledge_object_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=KnowledgeObjectStatus.DRAFT,
        server_default=KnowledgeObjectStatus.DRAFT.value,
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en", server_default="en")

    # Extraction/authoring confidence — NOT evidence strength (section 16
    # makes this distinction explicit for Claims; the same principle
    # applies here: how sure the pipeline/author is this object is
    # correctly identified/scoped, independent of how well-evidenced its
    # claims are).
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    # Default to NOT visible: an object must be deliberately published
    # (see KnowledgeObjectStatus + the /publish action) before it is
    # exposed publicly or to AI systems. Fail-safe default, not
    # fail-open — matches the review posture already established for
    # claims (draft-by-default) and production config (secure-by-default).
    public_visibility: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    ai_visibility: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    entities: Mapped[list["Entity"]] = relationship(  # noqa: F821
        back_populates="knowledge_object", cascade="all, delete-orphan"
    )
    claims: Mapped[list["Claim"]] = relationship(  # noqa: F821
        back_populates="knowledge_object", cascade="all, delete-orphan"
    )
    versions: Mapped[list["KnowledgeVersion"]] = relationship(  # noqa: F821
        back_populates="knowledge_object", cascade="all, delete-orphan", order_by="KnowledgeVersion.version"
    )
    gaps: Mapped[list["KnowledgeGap"]] = relationship(  # noqa: F821
        back_populates="knowledge_object", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<KnowledgeObject id={self.id} slug={self.slug!r} type={self.object_type!r}>"
