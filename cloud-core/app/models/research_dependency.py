"""
Source dependency and research iterations (ADR-109).

`SourceDependency` records that one source rests on another — a review on the trials it summarises, a
reanalysis on its original data, two records of the same study. It exists so that twenty reviews of three
trials are never counted as twenty independent findings.

`ResearchIteration` records what each search round cost and yielded, which is what makes an honest
stopping decision possible: the system reports *why* it stopped, never "we searched the whole internet".
"""
from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

DEPENDENCY_RELATIONS = ("cites", "reviews", "reanalyses", "same_study", "preprint_of", "retracts", "corrects")
# A source that only *cites* another is still independent evidence; these relations are not.
NON_INDEPENDENT = ("reviews", "reanalyses", "same_study", "preprint_of")
SATURATION_REASONS = ("query_variants_exhausted", "low_marginal_yield", "duplicate_sources_only", "budget_reached",
                      "user_limit_reached", "no_new_relevant_evidence", "provider_unavailable", "not_saturated")


def _in(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class SourceDependency(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_dependencies"
    __table_args__ = (
        CheckConstraint(f"relation IN ({_in(DEPENDENCY_RELATIONS)})", name="relation"),
        CheckConstraint("detected_by IN ('user', 'doi_reference', 'provider')", name="detected_by"),
        CheckConstraint("source_id <> depends_on_source_id", name="no_self_dependency"),
        UniqueConstraint("organization_id", "source_id", "depends_on_source_id", "relation", name="uq_source_dependency"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    depends_on_source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    relation: Mapped[str] = mapped_column(String(20), nullable=False)
    detected_by: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    note: Mapped[str | None] = mapped_column(Text)


class ResearchIteration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_iterations"
    __table_args__ = (UniqueConstraint("organization_id", "research_question_id", "iteration", name="uq_research_iteration"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    research_question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    route: Mapped[str] = mapped_column(String(30), nullable=False)
    research_query_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_queries.id", ondelete="SET NULL"))
    sources_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_sources: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    providers_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    providers_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
