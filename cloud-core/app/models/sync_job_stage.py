"""
SyncJobStage (Step 7C-3, decision D14b): the current state of one stage of a
document-ingestion job.

One row per (job, stage) holding its current state, not an append-only event
log: queries stay simple and the table small; it can grow into a log later if
one is needed. Rows go with their job (ON DELETE CASCADE). services/stage_events
writes them when AIOL_EMIT_STAGE_EVENTS is on (7C-4); the Processing endpoint
still derives each stage (processing_service) until 7C-5 reads them.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Enum as SAEnum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SyncJobStageKey, SyncJobStageState


class SyncJobStage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_job_stages"
    __table_args__ = (UniqueConstraint("sync_job_id", "stage_key", name="uq_sync_job_stages_job_stage"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sync_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    stage_key: Mapped[SyncJobStageKey] = mapped_column(
        SAEnum(SyncJobStageKey, name="sync_job_stage_key", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    state: Mapped[SyncJobStageState] = mapped_column(
        SAEnum(SyncJobStageState, name="sync_job_stage_state", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
