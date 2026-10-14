"""
Page view telemetry (Phase 13, ADR-078 / ADR-079).

This table is the one the owner asked for by name: *who arrived, from
where, on which page, for how long.* It is also the table that reverses a
deliberate earlier narrowing, so the reversal is documented here rather
than being discoverable only from a diff.

WHAT CHANGED, AND WHY IT IS RECORDED

`AIOL_Actors` (Phase 9, ADR-046) deliberately stored no IP and no query
string: "an adapter log is not an analytics product". The pre-Phase-13 UX
checkpoint (§P.5) found that the original design conversation had asked
for geography and dwell time, and declined to close the gap by default,
flagging it as an **owner decision**. The owner has now made that decision
explicitly and asked for IP, geolocation and dwell time.

So this is not scope creep and it is not a silent reversal — it is a
recorded supersession (ADR-079 supersedes the privacy narrowing in
ADR-046, which remains preserved and readable). What the earlier decision
got right is kept: the data now collected is personal data, and the model
carries the consequences of that rather than pretending otherwise.

HOW THE PRIVACY COST IS BOUNDED

    ip_address        full address, INET, NULLABLE, retention-bounded
    ip_truncated      /24 (v4) or /48 (v6), never NULL when an IP was seen
    ip_retained_until the row's own expiry for the full address

`ip_truncated` is written on every row and never deleted. `ip_address` is
nulled by the retention job at `ip_retained_until` (default 30 days,
organization-configurable). So historical analytics keep working forever
at network granularity, and the identifying value has a life span that a
merchant can point to when asked. This is the difference between "we
collect IPs" and "we collect IPs forever", and only the second one is
hard to defend.

`is_authenticated_human` is deliberately absent. Nothing here links a view
to a logged-in identity, and no cross-session visitor id is minted.
Checkpoint §76/§77 prohibits profiling and manipulation framing; that
prohibition is unchanged by this ADR and is the reason the owner's
analytics requirement is met with *traffic* data rather than *person*
data.

GEOLOCATION IS NOT INVENTED

There is no bundled IP-geolocation database and no third-party lookup
call. `geo_method` says where the location came from, and when nothing
supplied one it is `NONE` with every geo column NULL — which the dashboard
renders as *Not available*, never as a zero or an empty map pin
(checkpoint §10: "Not available" is not "0"). Wiring a real geo provider
is a documented follow-up, not a thing this phase quietly faked.

DWELL TIME IS NULLABLE AND THAT IS LOAD-BEARING

`dwell_ms` is NULL unless the client actually reported it. A crawler that
fetches one URL and leaves reports nothing; writing 0 there would claim
"measured, and it was instant", which is a different and false statement.
Same rule as Phase 12's search metrics (ADR-075).

APPEND-ONLY

A page view is an observation of a moment. It is never updated - except
for the one retention write that nulls `ip_address`, which is a deletion,
not a revision.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Enum as SAEnum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AccessDecision,
    AccessPurpose,
    ActorConfidence,
    ActorType,
    GeoResolutionMethod,
)


def _enum(cls, name):
    return SAEnum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class PageView(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "page_views"
    __table_args__ = (
        # Idempotency. The adapter batches and retries; a redelivered batch
        # must not double-count a page. `event_key` is minted client-side
        # (uuid4 per observation) and is the whole reason a retry is safe.
        UniqueConstraint(
            "organization_id", "event_key", name="uq_page_views_organization_event_key"
        ),
        ForeignKeyConstraint(
            ["site_id", "organization_id"],
            ["sites.id", "sites.organization_id"],
            name="fk_page_views_site_organization",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["ai_agent_id", "organization_id"],
            ["ai_agents.id", "ai_agents.organization_id"],
            name="fk_page_views_ai_agent_organization",
            ondelete="SET NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    event_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # --- what was fetched ---------------------------------------------------
    # Path only. The query string is stripped before storage (inherited
    # from ADR-046) because it routinely carries personal data; a search
    # term that matters is recorded deliberately as a SearchDemandEvent,
    # not swept up incidentally from a URL.
    path: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    # Free-text label so a report can group "product page" vs "article"
    # without Core having to know a site's routing.
    content_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    content_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- who fetched it -----------------------------------------------------
    actor_type: Mapped[ActorType] = mapped_column(
        _enum(ActorType, "actor_type"), nullable=False, index=True
    )
    confidence: Mapped[ActorConfidence] = mapped_column(
        _enum(ActorConfidence, "actor_confidence"),
        nullable=False,
        default=ActorConfidence.UNKNOWN,
        server_default=ActorConfidence.UNKNOWN.value,
    )
    ai_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    purpose: Mapped[AccessPurpose] = mapped_column(
        _enum(AccessPurpose, "access_purpose"),
        nullable=False,
        default=AccessPurpose.UNKNOWN,
        server_default=AccessPurpose.UNKNOWN.value,
    )
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    referrer_host: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # --- network identity (retention-bounded, ADR-079) ----------------------
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    ip_truncated: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ip_retained_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, index=True
    )

    # --- geography (never inferred, ADR-079) --------------------------------
    geo_method: Mapped[GeoResolutionMethod] = mapped_column(
        _enum(GeoResolutionMethod, "geo_resolution_method"),
        nullable=False,
        default=GeoResolutionMethod.NONE,
        server_default=GeoResolutionMethod.NONE.value,
    )
    geo_country: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    geo_region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    geo_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Rounded to 2 decimal places by the service (~1 km). Full precision
    # would be a home address; 1 km is a city district, which is what a
    # traffic report actually needs.
    geo_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- engagement ---------------------------------------------------------
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, index=True
    )
    # NULL means not reported. See the module docstring.
    dwell_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # True when the client told us the visit ended (beacon fired) rather
    # than the dwell being a lower bound from the last heartbeat.
    dwell_is_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # --- what the access policy did ----------------------------------------
    access_decision: Mapped[AccessDecision] = mapped_column(
        _enum(AccessDecision, "access_decision"),
        nullable=False,
        default=AccessDecision.NOT_CONFIGURED,
        server_default=AccessDecision.NOT_CONFIGURED.value,
        index=True,
    )
    # The rule that produced it, for "why was this blocked?". Intentionally
    # NOT a FK: policies are edited and deleted, and the history of what we
    # did must survive the rule that did it.
    matched_policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PageView {self.actor_type.value} {self.path} dwell={self.dwell_ms}>"
