"""
Federated research records (pilot-ready research engine).

  ResearchQuestion     what is being asked (subject, optional compound, outcome, population)
  ResearchQuery        one concrete query string sent to providers (mode + keyword ids + route)
  ResearchProviderRun  one provider call for one query: ok / failed / not_configured (never hidden)
  ResearchHit          one record a provider returned, linked to the (deduplicated) Source

Traceability: keyword -> research project -> research task -> query -> provider run -> hit ->
source -> evidence -> claim -> knowledge object.
"""
from __future__ import annotations

import uuid

from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

QUERY_MODES = ("single", "multi", "exact", "boolean", "agent")
EVIDENCE_ROUTES = ("direct_subject",              # the study tested the subject itself
                   "compound_human",              # a constituent compound, studied in humans
                   "mechanistic",                 # mechanism / in vitro / animal
                   "co_occurrence",               # subject and compound mentioned together
                   "indirect_taxonomic",          # a taxonomic relative of the subject
                   "indirect_analogous_species",  # a different species used the same way
                   "indirect_formulation",        # a preparation containing the subject
                   "combination",                 # a combination of the subject's compounds
                   "background",                  # context, not evidence for the question
                   "general")
# Only these two may ever be DIRECT; every other route is indirect by database constraint.
DIRECT_CAPABLE_ROUTES = ("direct_subject", "general")
PROVIDER_RUN_STATES = ("ok", "failed", "not_configured")


def _in(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class ResearchQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_questions"
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="SET NULL"))
    research_project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="SET NULL"))
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)          # e.g. Taranjabin
    compound: Mapped[str | None] = mapped_column(String(300))                  # first compound (kept for existing rows)
    compounds: Mapped[list | None] = mapped_column(JSON)                       # every compound the question covers
    related_species: Mapped[list | None] = mapped_column(JSON)                 # taxonomic / analogous species
    outcome: Mapped[str | None] = mapped_column(String(300))                   # e.g. laxative
    population: Mapped[str | None] = mapped_column(String(100))                # e.g. human
    saturation_reason: Mapped[str | None] = mapped_column(String(40))          # why searching stopped (ADR-109)
    saturation_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=12)


class ResearchQuery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_queries"
    __table_args__ = (
        CheckConstraint(f"mode IN ({_in(QUERY_MODES)})", name="mode"),
        CheckConstraint(f"route IN ({_in(EVIDENCE_ROUTES)})", name="route"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    research_task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    research_question_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_questions.id", ondelete="SET NULL"), index=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    route: Mapped[str] = mapped_column(String(30), nullable=False, default="general")
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    keyword_ids: Mapped[list | None] = mapped_column(JSON)


class ResearchProviderRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_provider_runs"
    __table_args__ = (CheckConstraint(f"status IN ({_in(PROVIDER_RUN_STATES)})", name="status"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    research_query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_queries.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class ResearchHit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_hits"
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_provider_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200))
    doi: Mapped[str | None] = mapped_column(String(300))
    pmid: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str | None] = mapped_column(Text)
    merged_into_existing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # dedup outcome
    matched_on: Mapped[str | None] = mapped_column(String(20))  # doi | pmid | canonical_title | new
