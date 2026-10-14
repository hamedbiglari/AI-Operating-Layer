"""Phase 13 — analytics, demand intelligence and AI access control.

Creates: ai_agents, access_policies, page_views, content_view_daily,
search_demand_events.

CORRECTION (Phase 14 forensic pass): this migration originally assumed
`adapter_scope` was a native Postgres ENUM type, "following the ADR-018
precedent for additive enum extension", and tried to `ALTER TYPE
adapter_scope ADD VALUE` for the two new Phase 13 scopes. That premise was
wrong — `installation_credentials.scopes` has always been a plain
`ARRAY(String(64))` (see migration 0010 and `app/models/installation.py`);
the closed set of permitted values is enforced at the application layer
by `AdapterScope(str, enum.Enum)` in `app/models/enums.py`, not by any
database type. No such Postgres type as `adapter_scope` has ever existed,
so the ALTER TYPE calls failed outright — this was never run successfully
before now. TELEMETRY_WRITE/TELEMETRY_READ were already added to the
Python enum for this phase, so no DDL is needed at all to make the new
scope values valid; this migration now does only what the table itself
actually needs: create the five new tables. The downgrade still clears
the two new-phase scope values from any credential that holds them,
exactly as before, but as a plain array UPDATE with no type involved.

REVERSIBILITY

base -> head -> base -> head is verified by
`scripts/verify_migration_cycle.sh`. The five new tables drop cleanly; the
six new enum types are dropped explicitly because SQLAlchemy's
`Enum(..., name=...)` creates a real PG type that `drop_table` does not
remove, and an orphan type is exactly the schema drift §29 forbids.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# No explicit pre-creation loop for these eight types (there was one
# here originally: `for enum_type in _NEW_ENUMS: enum_type.create(bind,
# checkfirst=True)`, run before any table that uses them). Removed
# because it actively caused the bug it was trying to avoid: each of
# these types is reused across several tables below (ACTOR_TYPE alone in
# four), and create_table()'s own built-in checkfirst-based
# auto-creation already handles "create this shared type once, reuse it
# on every later table" correctly on its own — confirmed against a real,
# freshly created Postgres database (Phase 14 forensic pass). Explicitly
# pre-creating the types AND letting create_table() auto-create them
# again produced "type already exists" on the very first reused type,
# every time, including right after a DROP DATABASE + CREATE DATABASE
# cycle — so it was never leftover state from an earlier attempt, it was
# this migration creating each type twice within a single run. Adding
# create_type=False to suppress the second creation did not resolve it
# either (that flag is meant for a type that is ALREADY guaranteed
# present, not for coordinating two creation paths inside one
# migration), so the correct fix is not adding a flag but removing the
# redundant explicit loop and trusting the one creation path that
# already works.
ACTOR_TYPE = sa.Enum(
    "human", "search_crawler", "ai_crawler", "ai_user_agent", "agent_tool", "unknown",
    name="actor_type",
)
ACTOR_CONFIDENCE = sa.Enum(
    "detected", "probable", "verified", "unknown", name="actor_confidence"
)
ACCESS_PURPOSE = sa.Enum(
    "training", "search_indexing", "answering", "agent_action", "preview", "unknown",
    name="access_purpose",
)
ACCESS_TIER = sa.Enum("free", "paid", "forbidden", "unset", name="access_tier")
ACCESS_DECISION = sa.Enum(
    "allowed", "payment_required", "blocked", "not_configured", name="access_decision"
)
AGENT_ORIGIN = sa.Enum(
    "seeded", "discovered", "manual", name="agent_registration_origin"
)
SEARCH_DEMAND_SOURCE = sa.Enum(
    "onsite_search", "agent_query", "referrer_query", "adapter_reported",
    name="search_demand_source",
)
GEO_METHOD = sa.Enum(
    "edge_header", "adapter_reported", "none", name="geo_resolution_method"
)

_NEW_ENUMS = (
    ACTOR_TYPE, ACTOR_CONFIDENCE, ACCESS_PURPOSE, ACCESS_TIER, ACCESS_DECISION,
    AGENT_ORIGIN, SEARCH_DEMAND_SOURCE, GEO_METHOD,
)

# The two new Phase 13 scope values, for the downgrade-time cleanup below.
# No corresponding "add" step exists on the upgrade side: `scopes` is a
# plain string array with no database-level enum to extend (see the
# module docstring's CORRECTION note) — TELEMETRY_WRITE/TELEMETRY_READ
# are valid the moment `app/models/enums.py` defines them, which it
# already does.
_NEW_SCOPES = ("telemetry:write", "telemetry:read")


def upgrade() -> None:
    # --- ai_agents ------------------------------------------------------
    op.create_table(
        "ai_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signature", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("vendor", sa.String(length=120), nullable=True),
        sa.Column("actor_type", ACTOR_TYPE, nullable=False),
        sa.Column("declared_purpose", ACCESS_PURPOSE, nullable=False, server_default="unknown"),
        sa.Column("confidence", ACTOR_CONFIDENCE, nullable=False, server_default="unknown"),
        sa.Column("origin", AGENT_ORIGIN, nullable=False, server_default="discovered"),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.Column("sample_user_agent", sa.String(length=400), nullable=True),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("observation_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_ai_agents_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_agents"),
        sa.UniqueConstraint(
            "organization_id", "signature", name="uq_ai_agents_organization_signature"
        ),
    )
    # Composite unique so child tables can carry a tenant-composite FK -
    # the ADR-037 pattern that makes a cross-tenant parent impossible at
    # SQL level, not merely unlikely at service level.
    op.create_unique_constraint(
        "uq_ai_agents_id_organization_id", "ai_agents", ["id", "organization_id"]
    )
    op.create_index("ix_ai_agents_organization_id", "ai_agents", ["organization_id"])
    op.create_index("ix_ai_agents_actor_type", "ai_agents", ["actor_type"])
    op.create_index("ix_ai_agents_origin", "ai_agents", ["origin"])
    op.create_index("ix_ai_agents_last_seen_at", "ai_agents", ["last_seen_at"])

    # --- access_policies ------------------------------------------------
    op.create_table(
        "access_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", ACTOR_TYPE, nullable=True),
        sa.Column("purpose", ACCESS_PURPOSE, nullable=True),
        sa.Column("tier", ACCESS_TIER, nullable=False, server_default="unset"),
        sa.Column("specificity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("terms_url", sa.String(length=2048), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_access_policies_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id", "organization_id"], ["ai_agents.id", "ai_agents.organization_id"],
            name="fk_access_policies_agent_organization", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"],
            name="fk_access_policies_updated_by_user_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_access_policies"),
    )
    # NULLS NOT DISTINCT is the whole reason precedence level 2 and 4 stay
    # unambiguous: without it Postgres allows two "GPTBot, any purpose"
    # rows because NULL != NULL.
    op.execute(
        sa.text(
            "ALTER TABLE access_policies ADD CONSTRAINT uq_access_policies_rule_identity "
            "UNIQUE NULLS NOT DISTINCT (organization_id, agent_id, actor_type, purpose)"
        )
    )
    op.create_index("ix_access_policies_organization_id", "access_policies", ["organization_id"])

    # --- page_views -----------------------------------------------------
    op.create_table(
        "page_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_key", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=True),
        sa.Column("content_title", sa.String(length=500), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("actor_type", ACTOR_TYPE, nullable=False),
        sa.Column("confidence", ACTOR_CONFIDENCE, nullable=False, server_default="unknown"),
        sa.Column("ai_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purpose", ACCESS_PURPOSE, nullable=False, server_default="unknown"),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column("referrer_host", sa.String(length=255), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("ip_truncated", sa.String(length=64), nullable=True),
        sa.Column("ip_retained_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("geo_method", GEO_METHOD, nullable=False, server_default="none"),
        sa.Column("geo_country", sa.String(length=2), nullable=True),
        sa.Column("geo_region", sa.String(length=80), nullable=True),
        sa.Column("geo_city", sa.String(length=120), nullable=True),
        sa.Column("geo_latitude", sa.Float(), nullable=True),
        sa.Column("geo_longitude", sa.Float(), nullable=True),
        sa.Column("geo_timezone", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("dwell_ms", sa.Integer(), nullable=True),
        sa.Column("dwell_is_complete", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("access_decision", ACCESS_DECISION, nullable=False, server_default="not_configured"),
        sa.Column("matched_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_page_views_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["site_id", "organization_id"], ["sites.id", "sites.organization_id"],
            name="fk_page_views_site_organization", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ai_agent_id", "organization_id"], ["ai_agents.id", "ai_agents.organization_id"],
            name="fk_page_views_ai_agent_organization", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_page_views"),
        sa.UniqueConstraint(
            "organization_id", "event_key", name="uq_page_views_organization_event_key"
        ),
    )
    op.create_index("ix_page_views_organization_id", "page_views", ["organization_id"])
    op.create_index("ix_page_views_site_id", "page_views", ["site_id"])
    op.create_index("ix_page_views_path", "page_views", ["path"])
    op.create_index("ix_page_views_actor_type", "page_views", ["actor_type"])
    op.create_index("ix_page_views_ai_agent_id", "page_views", ["ai_agent_id"])
    op.create_index("ix_page_views_geo_country", "page_views", ["geo_country"])
    op.create_index("ix_page_views_occurred_at", "page_views", ["occurred_at"])
    op.create_index("ix_page_views_access_decision", "page_views", ["access_decision"])
    op.create_index("ix_page_views_ip_truncated", "page_views", ["ip_truncated"])
    op.create_index("ix_page_views_referrer_host", "page_views", ["referrer_host"])
    op.create_index("ix_page_views_content_type", "page_views", ["content_type"])
    # Partial index: the retention job scans only rows that still hold an
    # address, which is a small and shrinking subset of the table.
    op.create_index(
        "ix_page_views_ip_retention_due",
        "page_views",
        ["ip_retained_until"],
        postgresql_where=sa.text("ip_address IS NOT NULL"),
    )
    # The rollup's own GROUP BY, indexed.
    op.create_index(
        "ix_page_views_rollup", "page_views", ["organization_id", "occurred_at", "site_id", "path"]
    )

    # --- content_view_daily ---------------------------------------------
    op.create_table(
        "content_view_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("content_title", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=80), nullable=True),
        sa.Column("view_date", sa.Date(), nullable=False),
        sa.Column("human_views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ai_crawler_views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ai_answer_views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("agent_views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("search_views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("unknown_views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("blocked_views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("payment_required_views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("dwell_ms_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("dwell_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("distinct_countries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recomputed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_content_view_daily_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["site_id", "organization_id"], ["sites.id", "sites.organization_id"],
            name="fk_content_view_daily_site_organization", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_content_view_daily"),
    )
    op.execute(
        sa.text(
            "ALTER TABLE content_view_daily ADD CONSTRAINT uq_content_view_daily_identity "
            "UNIQUE NULLS NOT DISTINCT (organization_id, site_id, path, view_date)"
        )
    )
    op.create_index("ix_content_view_daily_organization_id", "content_view_daily", ["organization_id"])
    op.create_index("ix_content_view_daily_view_date", "content_view_daily", ["view_date"])
    op.create_index("ix_content_view_daily_path", "content_view_daily", ["path"])
    op.create_index("ix_content_view_daily_total_views", "content_view_daily", ["total_views"])
    op.create_index("ix_content_view_daily_content_type", "content_view_daily", ["content_type"])
    op.create_index("ix_content_view_daily_site_id", "content_view_daily", ["site_id"])

    # --- search_demand_events -------------------------------------------
    op.create_table(
        "search_demand_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_key", sa.String(length=64), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("demand_source", SEARCH_DEMAND_SOURCE, nullable=False),
        sa.Column("actor_type", ACTOR_TYPE, nullable=False),
        sa.Column("ai_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("geo_country", sa.String(length=2), nullable=True),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_search_demand_events_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["query_id", "organization_id"], ["queries.id", "queries.organization_id"],
            name="fk_search_demand_events_query_organization", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ai_agent_id", "organization_id"], ["ai_agents.id", "ai_agents.organization_id"],
            name="fk_search_demand_events_ai_agent_organization", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_search_demand_events"),
        sa.UniqueConstraint(
            "organization_id", "event_key",
            name="uq_search_demand_events_organization_event_key",
        ),
    )
    op.create_index("ix_search_demand_events_organization_id", "search_demand_events", ["organization_id"])
    op.create_index("ix_search_demand_events_query_id", "search_demand_events", ["query_id"])
    op.create_index("ix_search_demand_events_actor_type", "search_demand_events", ["actor_type"])
    op.create_index("ix_search_demand_events_demand_source", "search_demand_events", ["demand_source"])
    op.create_index("ix_search_demand_events_occurred_at", "search_demand_events", ["occurred_at"])
    op.create_index("ix_search_demand_events_ai_agent_id", "search_demand_events", ["ai_agent_id"])
    op.create_index("ix_search_demand_events_geo_country", "search_demand_events", ["geo_country"])
    op.create_index("ix_search_demand_events_site_id", "search_demand_events", ["site_id"])


def downgrade() -> None:
    """DESTRUCTIVE, stated plainly.

    Dropping these tables destroys every recorded page view, every
    discovered agent and every access decision the merchant made. That is
    inherent to reversing the phase, not an accident — but it is written
    here so nobody runs it against production believing it is "just a
    reversible migration". The same warning pattern as migration 0007's
    enum downgrade.
    """
    op.drop_table("search_demand_events")
    op.drop_table("content_view_daily")
    op.drop_table("page_views")
    op.drop_table("access_policies")
    op.drop_table("ai_agents")

    # Clear the two Phase 13 scope values from any credential still
    # holding one — `scopes` is a plain string array (no database enum
    # involved; see the module docstring's CORRECTION note), so this is
    # an ordinary array UPDATE, not a type rebuild. Reversing the phase
    # should not leave a credential holding a scope whose meaning
    # (TELEMETRY_WRITE/TELEMETRY_READ) no longer exists once the Phase 13
    # code that checks for it is gone.
    op.execute(
        sa.text(
            "UPDATE installation_credentials SET scopes = "
            "ARRAY(SELECT unnest(scopes) EXCEPT SELECT unnest("
            "ARRAY['telemetry:write','telemetry:read']))"
        )
    )

    bind = op.get_bind()
    for enum_type in reversed(_NEW_ENUMS):
        enum_type.drop(bind, checkfirst=True)
