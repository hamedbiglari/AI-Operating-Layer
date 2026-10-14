"""
Evidence: a specific, citable finding drawn from a Source and
(optionally) pinned to one Document / DocumentChunk, that can be linked
to one or more Claims via claim_evidence (master spec section 9 — the
evidence_strength/directness/study_type model referenced from
Source.reliability_score's and Claim.evidence_strength's docstrings).

Evidence is deliberately its own row, not a field on claim_evidence:
a single study result ("RCT of N=200 found X reduces Y") is often cited
for or against SEVERAL claims. The study's own strength/directness/
study_type doesn't change per claim — only its RELATION to a given
claim does (see app/models/claim_evidence.py::ClaimEvidence.relation).

Distinct from Source.reliability_score (Phase 3): reliability_score
rates the SOURCE in general, independent of any specific finding;
Evidence.evidence_strength rates ONE finding drawn from it. A highly
reliable journal can still contain one weak, underpowered study.
"""

import uuid

from sqlalchemy import (
    Numeric,
    Boolean,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EvidenceDirectness, EvidenceStatus, EvidenceStrength


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(
            "sample_size IS NULL OR sample_size >= 0", name="ck_evidence_sample_size_non_negative"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional narrowing to the specific Document / DocumentChunk this
    # was read from. Both are SET NULL (not CASCADE) on delete —
    # re-extracting a Document deletes and recreates its chunks
    # (app/services/document_chunk_service.py), and that housekeeping
    # must never silently destroy a curated, possibly human-reviewed
    # Evidence row. Losing the pinpoint just degrades gracefully back
    # to source-level provenance.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    document_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Extensible vocabulary (randomized_controlled_trial, meta_analysis,
    # systematic_review, cohort_study, case_control_study, case_report,
    # in_vitro, animal_study, observational_study, expert_opinion,
    # traditional_use, narrative_review, mechanistic_study, ...) - plain
    # indexed string, same rationale as source_type/entity_type.
    study_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    directness: Mapped[EvidenceDirectness] = mapped_column(
        SAEnum(EvidenceDirectness, name="evidence_directness", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=EvidenceDirectness.DIRECT,
        server_default=EvidenceDirectness.DIRECT.value,
    )
    # This Evidence row's own strength rating — see the module docstring
    # for how this differs from Claim.evidence_strength (the aggregate).
    evidence_strength: Mapped[EvidenceStrength] = mapped_column(
        SAEnum(EvidenceStrength, name="evidence_strength", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=EvidenceStrength.VERY_LOW,
        server_default=EvidenceStrength.VERY_LOW.value,
    )
    status: Mapped[EvidenceStatus] = mapped_column(
        SAEnum(EvidenceStatus, name="evidence_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=EvidenceStatus.DRAFT,
        server_default=EvidenceStatus.DRAFT.value,
    )

    # The actual citable finding, in plain text — what this piece of
    # evidence says, independent of any claim it might end up linked to.
    # route of the evidence relative to the research subject (migration 0025). Compound, mechanistic and
    # co-occurrence evidence is INDIRECT by database constraint unless the study tested the subject itself.
    evidence_route: Mapped[str | None] = mapped_column(String(30), nullable=True)
    subject_tested: Mapped[str | None] = mapped_column(String(300), nullable=True)
    basis: Mapped[str | None] = mapped_column(String(20), nullable=True)  # full_text | abstract | metadata
    # what the evidence is actually about: the subject, one compound, or a combination ("Mannitol + Fructose")
    evidence_about: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # §19: how sure we are that the SOURCE SAYS this (0–1). Different from evidence_strength, which rates
    # how strong the underlying science is. A machine extraction may never claim 1.0 before human review.
    extraction_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    extraction_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    population: Mapped[str | None] = mapped_column(String(500), nullable=True)

    source_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    human_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    source: Mapped["Source"] = relationship()  # noqa: F821
    document: Mapped["Document | None"] = relationship()  # noqa: F821
    document_chunk: Mapped["DocumentChunk | None"] = relationship()  # noqa: F821
    claim_links: Mapped[list["ClaimEvidence"]] = relationship(  # noqa: F821
        back_populates="evidence", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Evidence id={self.id} study_type={self.study_type!r} strength={self.evidence_strength.value}>"
