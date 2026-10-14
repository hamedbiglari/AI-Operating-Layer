"""
ClaimEvidence: the many-to-many link between Claim and Evidence (master
spec section 9/16), carrying the one piece of information that is a
property of the LINK rather than of either side alone: how this
specific Evidence relates to this specific Claim (`relation`) — the raw
signal app/services/claim_evidence_service.py::recompute_claim_aggregate
reads to detect SUPPORTS-vs-CONTRADICTS disagreement on the same Claim
(this phase's "Conflict foundations").

A Claim can be linked to many Evidence rows, and one Evidence row (one
study) can support or contradict many different Claims — hence a
dedicated link table rather than a foreign key on either side.
"""

import uuid

from sqlalchemy import CheckConstraint, Enum as SAEnum, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EvidenceRelation


class ClaimEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_claim_id_evidence_id"),
        CheckConstraint(
            "weight IS NULL OR (weight >= 0 AND weight <= 1)", name="ck_claim_evidence_weight_range"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation: Mapped[EvidenceRelation] = mapped_column(
        SAEnum(EvidenceRelation, name="evidence_relation", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=EvidenceRelation.SUPPORTS,
        server_default=EvidenceRelation.SUPPORTS.value,
    )
    # 0-1: how much THIS LINK should count in the claim's aggregate —
    # independent of Evidence.evidence_strength (rates the study itself)
    # and Source.reliability_score (rates the source in general). NULL
    # means "derive the weight from evidence_strength alone" (see
    # claim_evidence_service.py::_effective_weight) — an explicit weight
    # is for the rare case a reviewer wants to override that default
    # (e.g. a HIGH-strength study that is only weakly relevant here).
    weight: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    claim: Mapped["Claim"] = relationship(back_populates="evidence_links")  # noqa: F821
    evidence: Mapped["Evidence"] = relationship(back_populates="claim_links")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ClaimEvidence claim_id={self.claim_id} evidence_id={self.evidence_id} "
            f"relation={self.relation.value}>"
        )
