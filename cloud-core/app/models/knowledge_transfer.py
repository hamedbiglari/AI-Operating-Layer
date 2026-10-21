"""A received Knowledge Transfer Package and what validation and reconciliation did with it (ADR-134).

The row is the audit trail of how worker output became (or did not become) knowledge: the raw package,
per-item validation verdicts, and per-claim reconciliation outcomes with the ids they touched. It is never
updated after reconciliation, and resubmitting the same package returns this row (idempotent by hash).
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

KTP_STATES = ("invalid", "reconciled", "partially_reconciled", "nothing_accepted")


class KnowledgeTransferRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_transfer_packages"
    __table_args__ = (
        UniqueConstraint("organization_id", "package_hash", name="uq_knowledge_transfer_packages_hash"),
        ForeignKeyConstraint(["knowledge_object_id", "organization_id"],
                             ["knowledge_objects.id", "knowledge_objects.organization_id"],
                             ondelete="CASCADE", name="fk_knowledge_transfer_packages_ko"),
        CheckConstraint("status IN ('invalid', 'reconciled', 'partially_reconciled', 'nothing_accepted')",
                        name="status"),
        CheckConstraint("status <> 'invalid' OR invalid_reason IS NOT NULL", name="invalid_needs_reason"),
        Index("ix_knowledge_transfer_packages_ko", "organization_id", "knowledge_object_id", "created_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    # Tenant isolation at SQL level (ADR-037): composite FK, the topic must belong to the same organization.
    knowledge_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Who produced it: user:<id> | execution:<id>. The execution, job and item locate it in the job system.
    submitted_by: Mapped[str] = mapped_column(String(120), nullable=False)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_key: Mapped[str | None] = mapped_column(String(200))
    item_key: Mapped[str | None] = mapped_column(String(200))
    package_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw: Mapped[str] = mapped_column(Text, nullable=False)                 # exactly as received
    ktp_version: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    invalid_reason: Mapped[str | None] = mapped_column(String(500))
    validation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reconciliation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
