"""
AI Center — AI Resource Registry, routing, shared working memory, discovery,
and the per-Knowledge-Object keyword workspace (REQ-AIC-*, REQ-KW-*; ADR-087…092).

Separation (ADR-087):
    Provider  ≠  Account  ≠  Model
    AIExecution (Phase 16/17, LOCKED) stays the one record per real model call;
    it gains only `provider_account_id` and `stop_reason`.
    Shared working memory ≠ Project Memory (docs) ≠ Knowledge Core ≠ AIExecution.

Every table is tenant-scoped (project invariant, tests/test_forensic_integrity.py):
providers, accounts and models are registered per tenant (BYOK).

Honesty rules enforced by the schema:
    * credentials are stored only encrypted (Fernet) + last 4 characters;
    * quota / balance / reset fields are NULL until a provider reports them;
    * discovery entries start DISCOVERED with an explicit classification basis
      — nothing is ACTIVE unless verified.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP, Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ROUTING_MODES = ("manual_single", "manual_chain", "stage_manual", "auto_pool", "priority_pool", "hybrid")
HEALTH_STATES = ("healthy", "degraded", "rate_limited", "quota_exhausted", "auth_failed",
                 "unavailable", "timeout", "unknown", "disconnected")
MEMORY_KINDS = ("job_state", "ai_handoff", "intermediate_finding", "open_question", "current_synthesis",
                "next_action", "conflict_context", "processing_checkpoint", "ai_summary")
DISCOVERY_STATUSES = ("discovered", "identified", "official_source_verified", "api_capability_checked",
                      "credential_method_verified", "capability_verified", "health_checked", "approved",
                      "active", "application_only", "model_only", "specialized_research_tool",
                      "no_verified_api", "not_verified", "deprecated", "blocked_external_dependency", "disabled")
KEYWORD_KINDS = ("primary", "secondary", "long_tail", "question", "commercial", "transactional", "local",
                 "scientific", "synonym", "alias", "alternative_spelling", "related_entity",
                 "customer_question", "ai_query",
                 # research keyword kinds (migration 0025)
                 "scientific_name", "common_name", "compound", "mechanism", "clinical_outcome", "safety_term",
                 "preparation_term", "dose_term", "language_variant")


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _tenant_fk(cols: list[str], table: str, name: str, ondelete: str = "CASCADE") -> ForeignKeyConstraint:
    return ForeignKeyConstraint(cols + ["organization_id"], [f"{table}.id", f"{table}.organization_id"],
                                ondelete=ondelete, name=name)


class AIProvider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_providers"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_ai_providers_id_organization_id"),
        UniqueConstraint("organization_id", "canonical_name", name="uq_ai_providers_org_canonical"),
        CheckConstraint(f"verification_status IN ({_in(DISCOVERY_STATUSES)})", name="verification_status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(120), nullable=False)
    official_url: Mapped[str | None] = mapped_column(String(500))
    api_base_url: Mapped[str | None] = mapped_column(String(500))
    documentation_url: Mapped[str | None] = mapped_column(String(500))
    # Which implemented adapter (app/integrations/llm/) can call it; NULL = none yet.
    adapter_key: Mapped[str | None] = mapped_column(String(60))
    credential_method: Mapped[str | None] = mapped_column(String(60))
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False, default="discovered")
    notes: Mapped[str | None] = mapped_column(Text)


class AIProviderAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_provider_accounts"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_ai_provider_accounts_id_organization_id"),
        UniqueConstraint("organization_id", "provider_id", "label", name="uq_ai_provider_accounts_label"),
        _tenant_fk(["provider_id"], "ai_providers", "fk_ai_provider_accounts_provider"),
        CheckConstraint(f"health_status IN ({_in(HEALTH_STATES)})", name="health_status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    plan_name: Mapped[str | None] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Never returned by any API. Fernet ciphertext + last four characters for display.
    credential_ciphertext: Mapped[str | None] = mapped_column(Text)
    credential_last4: Mapped[str | None] = mapped_column(String(4))
    credential_set_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    credential_last_tested_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    health_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    health_checked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    unavailable_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # Only provider-reported values; NULL = unknown (never 0).
    remaining_requests: Mapped[int | None] = mapped_column(Integer)
    remaining_tokens: Mapped[int | None] = mapped_column(Integer)
    quota_reset_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    spend_limit: Mapped[float | None] = mapped_column(Numeric(12, 4))
    spend_limit_currency: Mapped[str | None] = mapped_column(String(3))


class AIModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_models"
    __table_args__ = (
        UniqueConstraint("organization_id", "provider_id", "name", name="uq_ai_models_provider_name"),
        _tenant_fk(["provider_id"], "ai_providers", "fk_ai_models_provider"),
        CheckConstraint(f"status IN ({_in(DISCOVERY_STATUSES)})", name="status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str | None] = mapped_column(String(80))
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)
    modalities: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False, default=list)
    context_window: Mapped[int | None] = mapped_column(Integer)
    license: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="discovered")
    last_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class AIHealthEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_health_events"
    __table_args__ = (
        _tenant_fk(["account_id"], "ai_provider_accounts", "fk_ai_health_events_account"),
        CheckConstraint(f"status IN ({_in(HEALTH_STATES)})", name="status"),
        Index("ix_ai_health_events_account_time", "account_id", "observed_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # connection_test | execution
    http_status: Mapped[int | None] = mapped_column(Integer)
    provider_code: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str | None] = mapped_column(String(500))
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    observed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class AIRoutingPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_routing_policies"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_ai_routing_policies_id_organization_id"),
        UniqueConstraint("organization_id", "name", name="uq_ai_routing_policies_name"),
        CheckConstraint(f"mode IN ({_in(ROUTING_MODES)})", name="mode"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    max_cost_per_job: Mapped[float | None] = mapped_column(Numeric(12, 4))
    currency: Mapped[str | None] = mapped_column(String(3))


class AIRoutingStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_routing_steps"
    __table_args__ = (
        _tenant_fk(["policy_id"], "ai_routing_policies", "fk_ai_routing_steps_policy"),
        _tenant_fk(["account_id"], "ai_provider_accounts", "fk_ai_routing_steps_account"),
        UniqueConstraint("policy_id", "position", name="uq_ai_routing_steps_position"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(60))          # NULL = any stage
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    required_capability: Mapped[str | None] = mapped_column(String(40))


class AIRoutingDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Audit of every routing decision: what was chosen, what was skipped, why."""
    __tablename__ = "ai_routing_decisions"
    __table_args__ = (Index("ix_ai_routing_decisions_job", "organization_id", "job_key"),)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_key: Mapped[str | None] = mapped_column(String(200))
    stage: Mapped[str | None] = mapped_column(String(60))
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    chosen_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    chosen_model: Mapped[str | None] = mapped_column(String(160))
    trigger: Mapped[str] = mapped_column(String(60), nullable=False)   # initial | switch:<stop_reason> | manual_switch
    explanation: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class AIWorkingMemory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provider-agnostic shared working memory (checkpoints, handoffs, findings).
    Canonical in PostgreSQL; an optional semantic backend may mirror it."""
    __tablename__ = "ai_working_memory"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_in(MEMORY_KINDS)})", name="kind"),
        UniqueConstraint("organization_id", "job_key", "kind", "content_hash", name="uq_ai_working_memory_dedupe"),
        Index("ix_ai_working_memory_job", "organization_id", "job_key", "kind", "version"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    job_key: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    stage: Mapped[str | None] = mapped_column(String(60))
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    item_key: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)   # user:<id> | execution:<id> | system
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class AIDiscoveryEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_discovery_entries"
    __table_args__ = (
        UniqueConstraint("organization_id", "canonical_name", name="uq_ai_discovery_org_canonical"),
        CheckConstraint(f"status IN ({_in(DISCOVERY_STATUSES)})", name="status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(160), nullable=False)
    proposed_types: Mapped[list[str]] = mapped_column(ARRAY(String(30)), nullable=False, default=list)
    classification_basis: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="discovered")
    official_url: Mapped[str | None] = mapped_column(String(500))
    api_url: Mapped[str | None] = mapped_column(String(500))
    documentation_url: Mapped[str | None] = mapped_column(String(500))
    discovery_source: Mapped[str] = mapped_column(String(200), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    verification_notes: Mapped[str | None] = mapped_column(Text)


class KnowledgeKeyword(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_keywords"
    __table_args__ = (
        _tenant_fk(["knowledge_object_id"], "knowledge_objects", "fk_knowledge_keywords_ko"),
        UniqueConstraint("organization_id", "knowledge_object_id", "normalized", "kind", name="uq_knowledge_keywords_dedupe"),
        CheckConstraint(f"kind IN ({_in(KEYWORD_KINDS)})", name="kind"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False, default="primary")
    intent: Mapped[str | None] = mapped_column(String(60))
    source: Mapped[str | None] = mapped_column(String(120))
    volume: Mapped[int | None] = mapped_column(Integer)
    country: Mapped[str | None] = mapped_column(String(60))
    language: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(String(20))
    import_batch: Mapped[str | None] = mapped_column(String(80))
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)   # original imported row, never discarded
    research_task_ids: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)


class AIJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A multi-item AI processing job (REQ-AIC-004): the business parent of the
    AIExecutions it causes (exclusive-arc column ai_executions.ai_job_id)."""
    __tablename__ = "ai_jobs"
    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_ai_jobs_id_organization_id"),
        UniqueConstraint("organization_id", "job_key", name="uq_ai_jobs_job_key"),
        _tenant_fk(["policy_id"], "ai_routing_policies", "fk_ai_jobs_policy", ondelete="RESTRICT"),
        CheckConstraint("status IN ('queued', 'running', 'paused', 'pause_requested', 'blocked', 'completed', "
                        "'cancelled', 'cancel_requested')", name="status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    job_key: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[str] = mapped_column(String(1000), nullable=False)
    # §32 observability: how often this job had to retry or switch resource
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    switch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    stage: Mapped[str | None] = mapped_column(String(60))
    # ADR-095: set => this is BACKGROUND work and the tenant's BackgroundTaskPolicy for
    # this task type is enforced by the worker. NULL => interactive job the user started
    # with an explicitly chosen routing policy.
    task_type: Mapped[str | None] = mapped_column(String(80))
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    stop_reason: Mapped[str | None] = mapped_column(String(40))
    forced_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))   # manual switch request
    knowledge_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=400)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class AIJobItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One unit of work (e.g. one document). Canonical progress state: a
    switch or crash can never lose which items are done."""
    __tablename__ = "ai_job_items"
    __table_args__ = (
        _tenant_fk(["job_id"], "ai_jobs", "fk_ai_job_items_job"),
        UniqueConstraint("job_id", "item_key", name="uq_ai_job_items_key"),
        CheckConstraint("status IN ('pending', 'completed', 'failed')", name="status"),
        Index("ix_ai_job_items_job_status", "job_id", "status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    item_key: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)          # domain-owned input (not on AIExecution)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    last_execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    failure_reason: Mapped[str | None] = mapped_column(String(300))
    completed_by_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
