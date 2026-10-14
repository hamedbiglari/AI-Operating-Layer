"""
VisibilityTest (master spec section 31) — one observation of how a
platform answered one prompt, at one moment.

THE NAMING, stated up front because it misleads otherwise: section 31 calls
this table `visibility_tests`, and that name is kept for spec fidelity. But
a row here is an **observation**, not a test result in the pass/fail sense.
It records what a platform said on one occasion. It does not establish that
the merchant "is visible on ChatGPT" — a sample of one prompt on one day is
not a statement about a population, and the API layer is responsible for
never presenting it as one.

FIVE SIGNALS, TRI-STATE, NOT BOOLEAN (ADR-061)

Section 31 lists `mentioned`, `cited`, `recommended`, `product_present`,
`url_present`, which read as booleans. They are `SignalPresence` instead,
because a boolean `false` cannot distinguish:

    "we looked, and the brand was not cited"   -> a real negative finding
    "we did not check for citation"            -> no finding at all

Averaging those together produces a wrong number, quietly. The default is
NOT_CHECKED: an observation that did not examine a signal has said nothing
about it.

TWO SIGNALS FROM SECTION 31 ARE DELIBERATELY ABSENT

Section 31's prose lists seven things that must stay distinct: Mention,
Citation, Recommendation, Product Display, URL, **Click**, **Purchase**.
Its column list gives five. Click and Purchase have no columns here, and
that is the correct reading rather than an omission:

  - a click happens in the user's browser, on a platform this system
    cannot observe
  - a purchase happens on the merchant's own site, and belongs to
    commerce/analytics, not to visibility observation

Giving them columns would invite writing values that could only be guesses.
Their absence is enforced by test. See ADR-062.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    SignalPresence,
    VisibilityCollectionMethod,
    VisibilityPlatform,
    VisibilityTestType,
)


class VisibilityTest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "visibility_tests"
    __table_args__ = (
        # Composite tenant FK (ADR-037), adopted at creation rather than
        # retrofitted - the Phase 9 lesson.
        ForeignKeyConstraint(
            ["query_id", "organization_id"], ["queries.id", "queries.organization_id"],
            name="fk_visibility_tests_query_organization", ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["product_id", "organization_id"], ["products.id", "products.organization_id"],
            name="fk_visibility_tests_product_organization", ondelete="SET NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Nullable: a probe may be ad-hoc rather than tied to a tracked Query.
    # Phase 6 owns Query; this references it and never duplicates it.
    query_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # Beyond section 31's list: which product the probe was about, when it
    # was product-specific. Without it, `product_present` is unattributable.
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # P12-18: an observation may belong to a run. Both nullable because
    # ad-hoc observations predate runs and remain valid.
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # How the provider call ended. NULL for manually entered observations,
    # which had no provider.
    provider_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Fixture data must never be mistaken for a live observation.
    is_fixture: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    platform: Mapped[VisibilityPlatform] = mapped_column(
        SAEnum(VisibilityPlatform, name="visibility_platform", values_callable=lambda e: [m.value for m in e]),
        nullable=False, index=True,
    )
    test_type: Mapped[VisibilityTestType] = mapped_column(
        SAEnum(VisibilityTestType, name="visibility_test_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )

    # The exact prompt issued. Stored verbatim so an observation can be
    # re-run and compared; paraphrasing it would destroy reproducibility.
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # The platform's answer. Nullable because a failed probe still produces
    # a row - recording the attempt and its failure is the point.
    response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- the five section-31 signals, tri-state (see class docstring) ---
    mentioned: Mapped[SignalPresence] = mapped_column(
        SAEnum(SignalPresence, name="signal_presence", values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=SignalPresence.NOT_CHECKED,
        server_default=SignalPresence.NOT_CHECKED.value, index=True,
    )
    cited: Mapped[SignalPresence] = mapped_column(
        SAEnum(SignalPresence, name="signal_presence", values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=SignalPresence.NOT_CHECKED,
        server_default=SignalPresence.NOT_CHECKED.value,
    )
    recommended: Mapped[SignalPresence] = mapped_column(
        SAEnum(SignalPresence, name="signal_presence", values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=SignalPresence.NOT_CHECKED,
        server_default=SignalPresence.NOT_CHECKED.value,
    )
    product_present: Mapped[SignalPresence] = mapped_column(
        SAEnum(SignalPresence, name="signal_presence", values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=SignalPresence.NOT_CHECKED,
        server_default=SignalPresence.NOT_CHECKED.value,
    )
    url_present: Mapped[SignalPresence] = mapped_column(
        SAEnum(SignalPresence, name="signal_presence", values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=SignalPresence.NOT_CHECKED,
        server_default=SignalPresence.NOT_CHECKED.value,
    )

    # --- provenance: how this observation was obtained ---
    collection_method: Mapped[VisibilityCollectionMethod] = mapped_column(
        SAEnum(VisibilityCollectionMethod, name="visibility_collection_method",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=VisibilityCollectionMethod.MANUAL_PASTE,
        server_default=VisibilityCollectionMethod.MANUAL_PASTE.value,
    )
    # The model/version the platform reported, where it reports one. NULL
    # when unknown - never guessed. Platform answers change with model
    # versions, so comparing observations across versions is not
    # like-for-like and a reader needs to be able to tell.
    platform_model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    result_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    tested_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, index=True)

    # Estimated cost of this probe, where the platform charges. Recorded so
    # spend is attributable per observation rather than only in aggregate.
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    # Phase 17: the terminal AIExecution of this probe's chain (the one
    # whose output was parsed, or the final failure). NULL for fixture and
    # not-configured probes — nothing was invoked. The composite tenant FK
    # (ai_execution_id, organization_id) -> ai_executions is issued as raw
    # DDL (column-list ON DELETE SET NULL); see app/models/ai_execution.py.
    ai_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VisibilityTest {self.platform.value} mentioned={self.mentioned.value} "
            f"cited={self.cited.value} at={self.tested_at}>"
        )
