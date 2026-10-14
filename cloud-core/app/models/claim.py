"""
Claim: a reviewable, evidence-trackable semantic assertion (master spec
section 16) - e.g. "Taranjabin -> contains -> Mannitol". Distinct from
Relationship (app/models/relationship.py): a Claim carries a review
lifecycle, an extraction-confidence/evidence-strength distinction, and
belongs to exactly one Knowledge Object; a Relationship is a lighter
generic graph edge that can connect any two graph nodes. The
claim_evidence linking table (Phase 4, see app/models/claim_evidence.py)
connects a Claim to its Evidence rows; evidence_strength here is the
Claim's AGGREGATE assessment, recomputed from every linked, VERIFIED
Evidence row by
app/services/claim_evidence_service.py::recompute_claim_aggregate
whenever a link is created, updated, or removed (see ClaimEvidenceStrength).
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ClaimEvidenceStrength, ClaimStatus


class Claim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            "(object_entity_id IS NOT NULL AND object_value IS NULL) "
            "OR (object_entity_id IS NULL AND object_value IS NOT NULL)",
            name="ck_claims_object_entity_xor_value",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_objects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Extensible vocabulary (e.g. "contains", "has_property", "treats") -
    # plain string, same rationale as object_type/entity_type.
    predicate: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    # A claim's object is EITHER another Entity OR a literal value (e.g.
    # "Taranjabin -> has_taste -> sweet") - mutually exclusive, enforced
    # by the XOR CHECK constraint above (exactly one must be non-null;
    # previously the constraint only required at least one, which wrongly
    # allowed both to be set at once — fixed after Phase 2 review).
    object_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    object_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ADR-114: which knowledge section this claim belongs to. Nullable: claims that predate the
    # category schema, or belong to an uncategorised topic, simply have no section.
    section_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    claim_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    evidence_strength: Mapped[ClaimEvidenceStrength] = mapped_column(
        SAEnum(ClaimEvidenceStrength, name="claim_evidence_strength", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ClaimEvidenceStrength.UNVERIFIED,
        server_default=ClaimEvidenceStrength.UNVERIFIED.value,
    )
    # Extraction/authoring confidence - explicitly NOT evidence strength
    # (section 16: "AI extraction can be highly confident while
    # scientific evidence remains weak").
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    status: Mapped[ClaimStatus] = mapped_column(
        SAEnum(ClaimStatus, name="claim_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ClaimStatus.DRAFT,
        server_default=ClaimStatus.DRAFT.value,
    )
    source_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    human_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    knowledge_object: Mapped["KnowledgeObject"] = relationship(back_populates="claims")  # noqa: F821
    subject_entity: Mapped["Entity"] = relationship(foreign_keys=[subject_entity_id])  # noqa: F821
    object_entity: Mapped["Entity | None"] = relationship(foreign_keys=[object_entity_id])  # noqa: F821
    # Phase 4: the links to this Claim's supporting/contradicting
    # Evidence rows (see app/models/claim_evidence.py). Deleting a Claim
    # deletes its links (the Evidence rows themselves survive — they may
    # be linked to other Claims too).
    evidence_links: Mapped[list["ClaimEvidence"]] = relationship(  # noqa: F821
        back_populates="claim", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Claim id={self.id} predicate={self.predicate!r} status={self.status.value}>"
