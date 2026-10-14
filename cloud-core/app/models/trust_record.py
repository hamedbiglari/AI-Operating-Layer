"""
TrustRecord (master spec section 30) — one evidence-backed trust
assertion about a subject (the organization itself, a product, or a
claim).

**There is deliberately no `trust_score` column, and that is the single
most important thing about this model.** Section 30: "Trust must be
evidence-backed... Do not create a fake 'trust score' that has no
explainable evidence." A score would be a number that survives
independently of the evidence underneath it — it can drift, be cached,
be shown after its supporting evidence is rejected, and be quoted out
of context as if it meant something external. Instead, "how trusted is
this product" is answered by ENUMERATING this table's VERIFIED rows for
that subject, which is inherently explainable: every unit of trust is a
row you can open, with a claim, a piece of evidence, and a verification
date attached.

`evidence_id` is NOT NULL for the same reason. A trust record with no
evidence is precisely the "fake trust" section 30 forbids — so it
cannot be represented in this schema at all, rather than being
discouraged in a docstring.

`verification_status` starts UNVERIFIED, always; only a human review
action sets VERIFIED (and stamps `verified_at`). Same discipline as
Claim/Evidence/ProductEvidence.

`subject_type`/`subject_id` is the polymorphic pointer section 30
specifies. Postgres cannot hold a real FK to "one of several tables",
so — exactly as Relationship (Phase 2) and ResearchTaskReference
(Phase 5) already do — the type is tagged here and the service layer
resolves + tenant-checks it against the right table before insert
(`app/services/trust_service.py::_resolve_subject`). It is never
trusted as-is.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Enum as SAEnum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import TrustSubjectType, TrustType, VerificationStatus


class TrustRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "trust_records"

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utcnow, nullable=False)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject_type: Mapped[TrustSubjectType] = mapped_column(
        SAEnum(TrustSubjectType, name="trust_subject_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    # No DB-level FK - points at one of several tables depending on
    # subject_type. Resolved and tenant-checked in the service layer.
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    trust_type: Mapped[TrustType] = mapped_column(
        SAEnum(TrustType, name="trust_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    # What is actually being asserted, in plain language - the thing a
    # human reviewer confirms the evidence does or doesn't support.
    claim: Mapped[str] = mapped_column(Text, nullable=False)

    # NOT NULL - see module docstring. Trust without evidence is
    # exactly what section 30 forbids, so the schema makes it
    # unrepresentable rather than merely discouraged.
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
        server_default=VerificationStatus.UNVERIFIED.value,
        index=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    evidence: Mapped["Evidence"] = relationship()  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<TrustRecord {self.subject_type.value}:{self.subject_id} "
            f"type={self.trust_type.value} status={self.verification_status.value}>"
        )
