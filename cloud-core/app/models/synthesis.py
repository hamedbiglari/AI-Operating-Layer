"""
Synthesis runs and the per-unit coverage ledger (prompt v4.0 §15–§21, §58–§60; ADR-124).

A `SynthesisRun` is one budgeted, coverage-audited synthesis over a scope of the knowledge base. Its model
calls are ordinary `ai_jobs` (one per stage: map, then each reduce level) — there is no second job system.

`SynthesisUnit` is the ledger §19 asks for: one row per knowledge unit that entered the run, with the
pack it went into and what became of it. The database itself refuses the two silent failures:
  * an `omitted` unit without an `omission_reason`;
  * a `merged` unit without the unit it was merged into.
A run can therefore not finish with a knowledge unit that simply vanished.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, TIMESTAMP, CheckConstraint, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

RUN_STATUSES = ("planned", "blocked", "queued", "running", "completed", "completed_with_gaps", "failed",
                "cancelled")
UNIT_STATUSES = ("pending", "processed", "represented", "merged", "transformed", "unresolved",
                 "contradictory", "omitted")


def _q(v):  # noqa: ANN001, ANN202
    return ", ".join(f"'{x}'" for x in v)


class SynthesisRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "synthesis_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_q(RUN_STATUSES)})", name="status"),
        CheckConstraint("status NOT IN ('failed', 'blocked') OR failure_reason IS NOT NULL",
                        name="a_failure_needs_a_reason"),
        # §20: a run may only call itself complete when its own ledger says nothing was lost
        CheckConstraint("status <> 'completed' OR (omitted_units = 0 AND pending_units = 0)",
                        name="complete_means_nothing_lost"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_objects.id", ondelete="CASCADE"), index=True)
    section_key: Mapped[str | None] = mapped_column(String(100))
    task: Mapped[str] = mapped_column(Text, nullable=False)                 # the instruction, in words
    scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)   # filters exactly as applied
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="planned", index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    budgets: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    plan: Mapped[dict | None] = mapped_column(JSON)
    allow_partial: Mapped[bool] = mapped_column(nullable=False, default=False)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    current_stage: Mapped[str | None] = mapped_column(String(30))
    ai_job_keys: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # §62/§63 reproducibility
    knowledge_version: Mapped[int | None] = mapped_column(Integer)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    # outcome
    result_text: Mapped[str | None] = mapped_column(Text)                   # with [[U..]] markers, unedited
    audit: Mapped[dict | None] = mapped_column(JSON)
    input_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    represented_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    merged_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transformed_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolved_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradictory_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    omitted_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    information_loss_rate: Mapped[float | None] = mapped_column(Float)      # NULL until audited
    publication_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("publications.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class SynthesisUnit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "synthesis_units"
    __table_args__ = (
        CheckConstraint(f"status IN ({_q(UNIT_STATUSES)})", name="status"),
        CheckConstraint("status <> 'omitted' OR omission_reason IS NOT NULL", name="an_omission_needs_a_reason"),
        CheckConstraint("status <> 'merged' OR merged_into_key IS NOT NULL", name="a_merge_needs_a_target"),
        UniqueConstraint("run_id", "unit_key", name="uq_synthesis_unit_key"),
        Index("ix_synthesis_units_run_status", "run_id", "status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("synthesis_runs.id", ondelete="CASCADE"), nullable=False)
    unit_key: Mapped[int] = mapped_column(Integer, nullable=False)          # the [[U<n>]] marker
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL"), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)                 # what the unit said when sent
    pack_index: Mapped[int | None] = mapped_column(Integer)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    contested: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    merged_into_key: Mapped[int | None] = mapped_column(Integer)
    omission_reason: Mapped[str | None] = mapped_column(Text)
    status_reason: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
