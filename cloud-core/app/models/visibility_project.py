"""
Visibility infrastructure (P12-18, ADR-074).

WHAT IS REUSED RATHER THAN REBUILT — the forensic decision that shaped
this file:

    VisibilityQuery     -> canonical `Query` (Phase 6). A visibility query
                           IS a query; a second query table would fork the
                           vocabulary the whole system reasons about.
    VisibilityObservation -> existing `VisibilityTest` (Phase 12), extended
                           with project/run links rather than replaced.
    VisibilitySource    -> `VisibilityPlatform` + `VisibilityCollectionMethod`
                           already model surface and method. A table would
                           add a row per enum value and nothing else.
    Job lifecycle       -> `SyncJob` (ADR-068), the canonical job model.
    Budget              -> `VisibilityBudget` (ADR-069).
    Gaps                -> `KnowledgeGap` (Phase 2) is referenced, never
                           duplicated.

Four models are genuinely new because nothing existing performs their role:
Project (measurement configuration), Run (one execution), Snapshot
(immutable historical summary), Competitor and Event.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    CompetitorOrigin,
    VisibilityEventType,
    VisibilityPlatform,
    VisibilityProjectStatus,
    VisibilityRunStatus,
)


def _enum(cls, name):
    return SAEnum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class VisibilityProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A coherent measurement configuration.

    `methodology_version` is the field that makes historical comparison
    honest: when the way we measure changes, snapshots taken under the old
    methodology must remain identifiable, or a trend line silently compares
    two different things.

    No provider credentials live here. Secrets belong in the credential
    architecture, not in an ordinary configuration row.
    """

    __tablename__ = "visibility_projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_visibility_projects_org_name"),
        ForeignKeyConstraint(
            ["site_id", "organization_id"], ["sites.id", "sites.organization_id"],
            name="fk_visibility_projects_site_organization", ondelete="SET NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[VisibilityProjectStatus] = mapped_column(
        _enum(VisibilityProjectStatus, "visibility_project_status"),
        nullable=False, default=VisibilityProjectStatus.ACTIVE,
        server_default=VisibilityProjectStatus.ACTIVE.value, index=True,
    )

    # Scope. Markets and languages are lists because visibility is
    # market-dependent: a US-English result and an IR-Persian result for
    # the same query are different observations, not one (P12 §38).
    markets: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    languages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    platforms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # Brand/domain the project is measuring FOR. Without it, "mentioned"
    # has no subject.
    target_brand: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)

    methodology_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="v1", server_default="v1"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VisibilityProject {self.name!r} {self.status.value}>"


class VisibilityRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of a project's query scope.

    PARTIAL exists because a run over twenty queries where three providers
    failed is neither SUCCEEDED nor FAILED. Forcing it into either loses
    the distinction between "everything worked" and "most things worked",
    and an operator needs that distinction to decide whether to re-run.

    `sync_job_id` links to the canonical job (ADR-068) rather than
    duplicating its lifecycle fields here.
    """

    __tablename__ = "visibility_runs"
    __table_args__ = (
        # Phase 17: composite tenant-FK target for ai_executions (ADR-037).
        UniqueConstraint("id", "organization_id", name="uq_visibility_runs_id_organization_id"),
        ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["visibility_projects.id", "visibility_projects.organization_id"],
            name="fk_visibility_runs_project_organization", ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sync_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    status: Mapped[VisibilityRunStatus] = mapped_column(
        _enum(VisibilityRunStatus, "visibility_run_status"),
        nullable=False, default=VisibilityRunStatus.PENDING,
        server_default=VisibilityRunStatus.PENDING.value, index=True,
    )
    platform: Mapped[VisibilityPlatform] = mapped_column(
        _enum(VisibilityPlatform, "visibility_platform"), nullable=False
    )
    market: Mapped[str | None] = mapped_column(String(8), nullable=True)
    language: Mapped[str | None] = mapped_column(String(12), nullable=True)

    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    methodology_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")

    queries_planned: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    queries_observed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    queries_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(String(32), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VisibilityRun {self.status.value} {self.queries_observed}/{self.queries_planned}>"


class VisibilitySnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An IMMUTABLE historical summary.

    Snapshots are never updated in place. A metric recomputed later under a
    changed methodology is a different measurement, and overwriting would
    make a trend line compare two incompatible things without saying so.

    Every count that could form a rate is stored alongside its denominator,
    so a consumer cannot construct a rate without also having the sample it
    came from (P12 §13).
    """

    __tablename__ = "visibility_snapshots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["visibility_projects.id", "visibility_projects.organization_id"],
            name="fk_visibility_snapshots_project_organization", ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    platform: Mapped[VisibilityPlatform] = mapped_column(
        _enum(VisibilityPlatform, "visibility_platform"), nullable=False
    )
    market: Mapped[str | None] = mapped_column(String(8), nullable=True)
    language: Mapped[str | None] = mapped_column(String(12), nullable=True)

    # THE DENOMINATOR. `observations_total` is everything in scope;
    # `observations_tested` is what was actually examined. A rate computed
    # against the wrong one is the single easiest way to publish a false
    # visibility number.
    observations_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observations_tested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observations_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observations_unavailable: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    mention_present: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    citation_present: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recommendation_present: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_present: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    url_present: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    methodology_version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    provider_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, index=True)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class VisibilityCompetitor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A competitor under measurement.

    `origin` distinguishes a brand the merchant named from one the system
    merely saw. A brand that appeared in an answer is a CANDIDATE; calling
    it a competitor without approval puts words in the merchant's mouth,
    and `is_approved` is what separates the two.
    """

    __tablename__ = "visibility_competitors"
    __table_args__ = (
        UniqueConstraint("project_id", "domain", name="uq_visibility_competitors_project_domain"),
        ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["visibility_projects.id", "visibility_projects.organization_id"],
            name="fk_visibility_competitors_project_organization", ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    origin: Mapped[CompetitorOrigin] = mapped_column(
        _enum(CompetitorOrigin, "competitor_origin"),
        nullable=False, default=CompetitorOrigin.MERCHANT_DEFINED,
        server_default=CompetitorOrigin.MERCHANT_DEFINED.value,
    )
    # A SYSTEM_DISCOVERED competitor is NOT approved until a human says so.
    is_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class VisibilityEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An OBSERVED CHANGE between two snapshots.

    Every event is descriptive. There is deliberately no `cause` column and
    no `impact` column: this system observes that a value changed, and
    cannot know why. A field for causality would be filled with guesses.
    """

    __tablename__ = "visibility_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["visibility_projects.id", "visibility_projects.organization_id"],
            name="fk_visibility_events_project_organization", ondelete="CASCADE",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    previous_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    current_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    event_type: Mapped[VisibilityEventType] = mapped_column(
        _enum(VisibilityEventType, "visibility_event_type"), nullable=False, index=True
    )
    platform: Mapped[VisibilityPlatform | None] = mapped_column(
        _enum(VisibilityPlatform, "visibility_platform"), nullable=True
    )
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    previous_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    current_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Always "observed" for events derived from snapshots. The column exists
    # so that if an inferred signal is ever added, the two can never be
    # confused (P12 §18).
    determination: Mapped[str] = mapped_column(
        String(16), nullable=False, default="observed", server_default="observed"
    )
    observed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, index=True)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
