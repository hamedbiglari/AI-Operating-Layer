"""
Background Processing Policy — explicit opt-in per task type (ADR-095).

A connected AI account is NOT automatically eligible for background processing.
The merchant must configure it here. Worker enforces these policies before dispatch.
"""
from __future__ import annotations
import uuid
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BackgroundTaskPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Policy for one background task type (document_processing, research, …)."""
    __tablename__ = "background_task_policies"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # JSON list of provider account UUIDs (ordered preferred → fallback)
    allowed_account_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    routing_policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    routing_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)  # mirrors RoutingMode enum
    max_cost_per_run: Mapped[float | None] = mapped_column(nullable=True)
    max_cost_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    required_capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    auto_switch_on_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pause_on_cost_limit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    __table_args__ = (UniqueConstraint("organization_id", "task_type", name="uq_bg_policy_task_type"),)


class MemoryProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Named memory profile (namespace, scope, backend selection)."""
    __tablename__ = "memory_profiles"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    namespace: Mapped[str] = mapped_column(String(200), nullable=False)
    scope: Mapped[str] = mapped_column(String(30), nullable=False, default="project")  # project/tenant/global
    semantic_backend: Mapped[str] = mapped_column(String(30), nullable=False, default="native")  # native/walrus
    retention_days: Mapped[int | None] = mapped_column(nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_memory_profile_name"),
                      UniqueConstraint("organization_id", "namespace", name="uq_memory_profile_ns"),)
