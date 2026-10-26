"""
SyncJob (master spec section 41) — durable record of asynchronous work.

Section 41's instruction is explicit: *"Use async workers. Do not perform
heavy ingestion/extraction/embedding tasks directly inside normal HTTP
requests."* This table is what makes that honest rather than aspirational:
a job that exists as a row survives a worker crash, a deploy, and a
restart, which an in-memory queue entry does not.

Three design points worth stating:

**`attempts` is on the row, not inferred.** A retry counter held only in
the broker is lost the moment the broker is. Storing it here is what makes
DEAD_LETTER reachable deterministically rather than by guesswork.

**`payload` is JSONB and deliberately small.** It carries identifiers and
intent, never the data itself. A job that embeds a whole product body
becomes a second copy of the truth that can drift from the first.

**`error_message` is truncated, not unbounded.** An unbounded error column
is how a retry storm fills a disk.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SyncJobStatus, SyncJobType


class SyncJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_sync_jobs_attempts_non_negative"),
        ForeignKeyConstraint(
            ["site_id", "organization_id"], ["sites.id", "sites.organization_id"],
            name="fk_sync_jobs_site_organization", ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Nullable: an organization-wide job need not belong to one site.
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # Document-ingestion jobs only (migration 0047); payload["document_id"] still carries it too.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    job_type: Mapped[SyncJobType] = mapped_column(
        SAEnum(SyncJobType, name="sync_job_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False, index=True,
    )
    status: Mapped[SyncJobStatus] = mapped_column(
        SAEnum(SyncJobStatus, name="sync_job_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SyncJobStatus.QUEUED,
        server_default=SyncJobStatus.QUEUED.value,
        index=True,
    )

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Idempotency handle supplied by the caller. Two deliveries of the same
    # webhook carry the same key and must not create two jobs. Unique per
    # organization rather than globally, so two tenants cannot collide.
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SyncJob {self.job_type.value} {self.status.value} attempts={self.attempts}>"
