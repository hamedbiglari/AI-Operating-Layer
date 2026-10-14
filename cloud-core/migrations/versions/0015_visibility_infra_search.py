"""visibility projects/runs/snapshots/competitors/events + search_observations

Revision ID: 0015
Revises: 0014
Create Date: 2026-01-15 00:00:00

P12-18 and P12-19 (ADR-074, ADR-075).

What is NOT created here, deliberately:
  - no second Query table: search and visibility both reference the
    canonical `queries` row
  - no VisibilityObservation table: `visibility_tests` is extended
  - no VisibilitySource table: platform + collection_method already model it

`visibility_tests` gains project_id/run_id so an existing observation can
belong to a run. Both nullable: ad-hoc observations predate runs and remain
valid.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    enums = {
        "visibility_project_status": ("active", "paused", "archived"),
        "visibility_run_status": ("pending", "queued", "running", "succeeded",
                                  "partial", "failed", "cancelled"),
        "competitor_origin": ("merchant_defined", "system_discovered", "user_approved"),
        "visibility_event_type": (
            "first_observed", "disappeared", "mention_changed", "citation_changed",
            "recommendation_changed", "product_appeared", "product_disappeared",
            "url_appeared", "url_disappeared", "rank_changed",
            "competitor_appeared", "competitor_disappeared"),
        "search_surface": ("google_web", "google_images", "google_news", "bing_web", "other"),
        "search_data_source": ("search_console", "serp_provider", "manual_import", "fixture"),
        "search_result_type": ("organic", "featured_snippet", "knowledge_panel",
                               "local_pack", "shopping", "video", "ai_overview", "other"),
    }
    for name, values in enums.items():
        postgresql.ENUM(*values, name=name, create_type=False).create(bind, checkfirst=True)

    op.create_table(
        "visibility_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", postgresql.ENUM(name="visibility_project_status", create_type=False),
                  nullable=False, server_default="active"),
        sa.Column("markets", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("languages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("platforms", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("target_brand", sa.String(length=200), nullable=True),
        sa.Column("target_domain", sa.String(length=255), nullable=True),
        sa.Column("methodology_version", sa.String(length=40), nullable=False, server_default="v1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_visibility_projects_org", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id", "organization_id"],
            ["sites.id", "sites.organization_id"],
            name="fk_visibility_projects_site_organization", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_visibility_projects"),
        sa.UniqueConstraint("organization_id", "name", name="uq_visibility_projects_org_name"),
    )
    op.create_index("ix_visibility_projects_organization_id", "visibility_projects", ["organization_id"])
    op.create_index("ix_visibility_projects_status", "visibility_projects", ["status"])
    op.create_unique_constraint(
        "uq_visibility_projects_id_organization_id", "visibility_projects", ["id", "organization_id"])

    op.create_table(
        "visibility_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sync_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", postgresql.ENUM(name="visibility_run_status", create_type=False),
                  nullable=False, server_default="pending"),
        sa.Column("platform", postgresql.ENUM(name="visibility_platform", create_type=False),
                  nullable=False),
        sa.Column("market", sa.String(length=8), nullable=True),
        sa.Column("language", sa.String(length=12), nullable=True),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("provider_version", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("methodology_version", sa.String(length=40), nullable=False, server_default="v1"),
        sa.Column("queries_planned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queries_observed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queries_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("estimated_cost", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_visibility_runs_org", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id", "organization_id"],
            ["visibility_projects.id", "visibility_projects.organization_id"],
            name="fk_visibility_runs_project_organization", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_visibility_runs"),
    )
    for col in ("organization_id", "project_id", "sync_job_id", "status"):
        op.create_index(f"ix_visibility_runs_{col}", "visibility_runs", [col])

    op.create_table(
        "visibility_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("platform", postgresql.ENUM(name="visibility_platform", create_type=False),
                  nullable=False),
        sa.Column("market", sa.String(length=8), nullable=True),
        sa.Column("language", sa.String(length=12), nullable=True),
        sa.Column("observations_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observations_tested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observations_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observations_unavailable", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mention_present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("citation_present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommendation_present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("product_present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("url_present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("methodology_version", sa.String(length=40), nullable=False, server_default="v1"),
        sa.Column("provider_name", sa.String(length=80), nullable=True),
        sa.Column("provider_version", sa.String(length=40), nullable=True),
        sa.Column("parser_version", sa.String(length=40), nullable=True),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_visibility_snapshots_org", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id", "organization_id"],
            ["visibility_projects.id", "visibility_projects.organization_id"],
            name="fk_visibility_snapshots_project_organization", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_visibility_snapshots"),
    )
    for col in ("organization_id", "project_id", "run_id", "captured_at"):
        op.create_index(f"ix_visibility_snapshots_{col}", "visibility_snapshots", [col])

    op.create_table(
        "visibility_competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("origin", postgresql.ENUM(name="competitor_origin", create_type=False),
                  nullable=False, server_default="merchant_defined"),
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_visibility_competitors_org", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id", "organization_id"],
            ["visibility_projects.id", "visibility_projects.organization_id"],
            name="fk_visibility_competitors_project_organization", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_visibility_competitors"),
        sa.UniqueConstraint("project_id", "domain", name="uq_visibility_competitors_project_domain"),
    )
    for col in ("organization_id", "project_id", "domain"):
        op.create_index(f"ix_visibility_competitors_{col}", "visibility_competitors", [col])

    op.create_table(
        "visibility_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", postgresql.ENUM(name="visibility_event_type", create_type=False),
                  nullable=False),
        sa.Column("platform", postgresql.ENUM(name="visibility_platform", create_type=False),
                  nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("previous_value", sa.String(length=120), nullable=True),
        sa.Column("current_value", sa.String(length=120), nullable=True),
        sa.Column("determination", sa.String(length=16), nullable=False, server_default="observed"),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_visibility_events_org", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id", "organization_id"],
            ["visibility_projects.id", "visibility_projects.organization_id"],
            name="fk_visibility_events_project_organization", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_visibility_events"),
    )
    for col in ("organization_id", "project_id", "event_type", "observed_at"):
        op.create_index(f"ix_visibility_events_{col}", "visibility_events", [col])

    # Link existing observations to runs/projects. Nullable: ad-hoc
    # observations predate runs and remain valid.
    op.add_column("visibility_tests",
                  sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("visibility_tests",
                  sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("visibility_tests",
                  sa.Column("provider_outcome", sa.String(length=32), nullable=True))
    op.add_column("visibility_tests",
                  sa.Column("parser_version", sa.String(length=40), nullable=True))
    op.add_column("visibility_tests",
                  sa.Column("is_fixture", sa.Boolean(), nullable=False, server_default="false"))
    op.create_index("ix_visibility_tests_run_id", "visibility_tests", ["run_id"])

    op.create_table(
        "search_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_source", postgresql.ENUM(name="search_data_source", create_type=False),
                  nullable=False),
        sa.Column("surface", postgresql.ENUM(name="search_surface", create_type=False),
                  nullable=False, server_default="google_web"),
        sa.Column("market", sa.String(length=8), nullable=True),
        sa.Column("language", sa.String(length=12), nullable=True),
        sa.Column("device", sa.String(length=16), nullable=True),
        sa.Column("observed_date", sa.Date(), nullable=False),
        sa.Column("position", sa.Float(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("result_type", postgresql.ENUM(name="search_result_type", create_type=False),
                  nullable=True),
        sa.Column("impressions", sa.Integer(), nullable=True),
        sa.Column("clicks", sa.Integer(), nullable=True),
        sa.Column("ctr", sa.Float(), nullable=True),
        sa.Column("provider_name", sa.String(length=80), nullable=False),
        sa.Column("provider_version", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("parser_version", sa.String(length=40), nullable=False, server_default="v1"),
        sa.Column("is_fixture", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("collected_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
            name="fk_search_observations_org", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_id", "organization_id"],
            ["queries.id", "queries.organization_id"],
            name="fk_search_observations_query_organization", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_search_observations"),
    )
    op.execute(
        "ALTER TABLE search_observations ADD CONSTRAINT uq_search_observations_identity "
        "UNIQUE NULLS NOT DISTINCT (organization_id, query_id, data_source, surface, "
        "market, language, observed_date, position)"
    )
    for col in ("organization_id", "query_id", "data_source", "market",
                "observed_date", "domain"):
        op.create_index(f"ix_search_observations_{col}", "search_observations", [col])


def downgrade() -> None:
    for col in ("domain", "observed_date", "market", "data_source", "query_id", "organization_id"):
        op.drop_index(f"ix_search_observations_{col}", table_name="search_observations")
    op.drop_table("search_observations")

    op.drop_index("ix_visibility_tests_run_id", table_name="visibility_tests")
    for col in ("is_fixture", "parser_version", "provider_outcome", "run_id", "project_id"):
        op.drop_column("visibility_tests", col)

    for table, cols in (
        ("visibility_events", ("observed_at", "event_type", "project_id", "organization_id")),
        ("visibility_competitors", ("domain", "project_id", "organization_id")),
        ("visibility_snapshots", ("captured_at", "run_id", "project_id", "organization_id")),
        ("visibility_runs", ("status", "sync_job_id", "project_id", "organization_id")),
    ):
        for col in cols:
            op.drop_index(f"ix_{table}_{col}", table_name=table)
        op.drop_table(table)

    op.drop_constraint("uq_visibility_projects_id_organization_id", "visibility_projects", type_="unique")
    op.drop_index("ix_visibility_projects_status", table_name="visibility_projects")
    op.drop_index("ix_visibility_projects_organization_id", table_name="visibility_projects")
    op.drop_table("visibility_projects")

    bind = op.get_bind()
    for name in ("search_result_type", "search_data_source", "search_surface",
                 "visibility_event_type", "competitor_origin",
                 "visibility_run_status", "visibility_project_status"):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
