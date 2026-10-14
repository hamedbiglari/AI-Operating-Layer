"""
ProductEvidence (master spec section 28) — links a Product to a Phase 4
`Evidence` row **for one specific, stated claim about that product**.

The `claim` column is the whole point of this table, and the reason it
is NOT nullable. Section 28's own examples:

    Product A / Claim: Origin = X   / Evidence: origin document
    Product A / Claim: Grade  = A   / Evidence: lab report

This is what enforces evidence SCOPE, the rule the Phase 7 brief calls
critical:

    Taranjabin contains Mannitol
    + independent evidence about Mannitol
    ≠ Taranjabin has Mannitol's clinical effect

Because every link must name the claim it supports, an origin document
can only ever be attached as evidence *for the origin claim*. There is
no schema path by which composition evidence silently becomes clinical-
efficacy evidence: doing that would require a human to literally type a
clinical claim next to a composition document, and then have another
human VERIFY it — which is exactly the reviewable, auditable moment the
spec wants this to be, rather than an inference the system makes on its
own. This model makes the unsafe conversion *visible*, not impossible;
software cannot stop a human from writing a false claim, but it can
refuse to make that leap by itself and it can record who did.

`verification_status` starts at UNVERIFIED, always. Section 28: "Do not
allow unsupported marketing claims to be presented as verified
evidence." A newly created link is never born VERIFIED — same
discipline as Claim (Phase 2) and Evidence (Phase 4).

`organization_id` added beyond the literal field list, same reasoning
as Offer (see ADR-022). `evidence_id` reuses the Phase 4 Evidence
engine rather than duplicating it — the Phase 7 brief's "Do not
duplicate Evidence Engine logic" requirement.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Enum as SAEnum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import VerificationStatus


class ProductEvidence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "product_evidence"
    __table_args__ = (
        # The same Evidence row may legitimately support several
        # DIFFERENT claims about the same product (a lab report can
        # evidence both "Grade = A" and "no heavy metals"), so
        # uniqueness is on the triple, not the pair.
        UniqueConstraint(
            "product_id", "evidence_id", "claim", name="uq_product_evidence_product_evidence_claim"
        ),
    )

    # created_at only, no TimestampMixin: an evidence link is an
    # append/remove record, not an edit-in-place one - changing which
    # claim a piece of evidence supports is a different link, not a
    # mutation of this one. Same reasoning as ResearchTaskReference
    # (Phase 5) and QueryProvenance (Phase 6).
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utcnow, nullable=False)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # NOT NULL by design - see module docstring. This is the scope.
    claim: Mapped[str] = mapped_column(Text, nullable=False)

    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
        server_default=VerificationStatus.UNVERIFIED.value,
        index=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="evidence_links")  # noqa: F821
    evidence: Mapped["Evidence"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ProductEvidence product_id={self.product_id} claim={self.claim!r} "
            f"status={self.verification_status.value}>"
        )
