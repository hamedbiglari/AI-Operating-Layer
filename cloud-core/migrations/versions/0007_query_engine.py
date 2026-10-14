"""queries, query_provenance, intents, query_groups, query_group_members, query_clusters, query_cluster_members (Phase 6: Query Engine, Intent, Query Clustering)

Revision ID: 0007
Revises: 0006
Create Date: 2026-01-07 00:00:00

Phase 6: the Query Engine foundation. `queries` + `query_provenance`
(section 23's Query, plus the additive occurrence-history table -
see app/models/query.py/query_provenance.py). `intents` (section 24).
`query_groups` + `query_group_members` (section 25, curated grouping).
`query_clusters` + `query_cluster_members` (additive - automatic
similarity grouping, kept deliberately separate from the curated
query_groups tables - see app/models/query_cluster.py).

Also additively extends the Phase 5 `research_reference_type` enum
with `query`/`query_group` (docs/DECISIONS.md ADR-015) so a
ResearchTaskReference can trace a research effort back to the demand
signal that motivated it, reusing Phase 5's existing provenance table
instead of Phase 6 inventing its own. This is the ONLY touch to a
prior migration's schema surface in this file, and it is additive only
(`ALTER TYPE ... ADD VALUE`) - migration 0006 itself is not modified.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    query_source = postgresql.ENUM(
        "search_console", "excel", "csv", "site_search", "keyword_tool",
        "customer", "research", "serp", "ai_test", "manual",
        name="query_source", create_type=False,
    )
    query_status = postgresql.ENUM(
        "discovered", "classified", "archived", name="query_status", create_type=False,
    )
    query_priority = postgresql.ENUM(
        "low", "medium", "high", "critical", name="query_priority", create_type=False,
    )
    intent_type = postgresql.ENUM(
        "information", "education", "problem", "comparison", "price", "quality",
        "authenticity", "trust", "origin", "supplier", "wholesale", "local",
        "availability", "commercial", "transactional", "recommendation",
        name="intent_type", create_type=False,
    )
    intent_classification_source = postgresql.ENUM(
        "rule_engine", "manual", "ml_model", name="intent_classification_source", create_type=False,
    )

    for enum_type in (query_source, query_status, query_priority, intent_type, intent_classification_source):
        enum_type.create(bind, checkfirst=True)

    # Additive extension of the Phase 5 enum - see module docstring.
    op.execute("ALTER TYPE research_reference_type ADD VALUE IF NOT EXISTS 'query'")
    op.execute("ALTER TYPE research_reference_type ADD VALUE IF NOT EXISTS 'query_group'")

    # --- queries ---------------------------------------------------
    op.create_table(
        "queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query", sa.String(length=1000), nullable=False),
        sa.Column("normalized_query", sa.String(length=1000), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("country", sa.String(length=10), nullable=True),
        sa.Column("source", query_source, nullable=False),
        sa.Column("search_volume", sa.Integer(), nullable=True),
        sa.Column("commercial_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("priority", query_priority, nullable=False, server_default="medium"),
        sa.Column("status", query_status, nullable=False, server_default="discovered"),
        sa.Column("discovered_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_queries_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_queries"),
        sa.UniqueConstraint("organization_id", "normalized_query", name="uq_queries_organization_normalized_query"),
        sa.CheckConstraint("search_volume IS NULL OR search_volume >= 0", name="ck_queries_search_volume_non_negative"),
        sa.CheckConstraint(
            "commercial_value IS NULL OR commercial_value >= 0", name="ck_queries_commercial_value_non_negative"
        ),
    )
    op.create_index("ix_queries_organization_id", "queries", ["organization_id"])
    op.create_index("ix_queries_normalized_query", "queries", ["normalized_query"])
    op.create_index("ix_queries_status", "queries", ["status"])

    # --- query_provenance ------------------------------------------
    op.create_table(
        "query_provenance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", query_source, nullable=False),
        sa.Column("raw_query", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_query_provenance_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["query_id"], ["queries.id"],
            name="fk_query_provenance_query_id_queries", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_query_provenance"),
    )
    op.create_index("ix_query_provenance_organization_id", "query_provenance", ["organization_id"])
    op.create_index("ix_query_provenance_query_id", "query_provenance", ["query_id"])

    # --- intents -----------------------------------------------------
    op.create_table(
        "intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intent_type", intent_type, nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("classification_source", intent_classification_source, nullable=False, server_default="rule_engine"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_intents_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["query_id"], ["queries.id"],
            name="fk_intents_query_id_queries", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["entities.id"],
            name="fk_intents_entity_id_entities", ondelete="SET NULL",
        ),
        # NOTE: no FK on product_id - products doesn't exist until
        # Phase 7. A future Phase 7 migration adds it via
        # op.create_foreign_key, this migration is never edited.
        sa.PrimaryKeyConstraint("id", name="pk_intents"),
    )
    op.create_index("ix_intents_organization_id", "intents", ["organization_id"])
    op.create_index("ix_intents_query_id", "intents", ["query_id"])
    op.create_index("ix_intents_intent_type", "intents", ["intent_type"])
    op.create_index("ix_intents_entity_id", "intents", ["entity_id"])
    op.create_index("ix_intents_product_id", "intents", ["product_id"])
    op.create_index(
        "uq_intents_query_id_primary", "intents", ["query_id"],
        unique=True, postgresql_where=sa.text("is_primary"),
    )

    # --- query_groups --------------------------------------------------
    op.create_table(
        "query_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("primary_intent", intent_type, nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", query_priority, nullable=False, server_default="medium"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_query_groups_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_entity_id"], ["entities.id"],
            name="fk_query_groups_target_entity_id_entities", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_query_groups"),
    )
    op.create_index("ix_query_groups_organization_id", "query_groups", ["organization_id"])
    op.create_index("ix_query_groups_target_entity_id", "query_groups", ["target_entity_id"])

    # --- query_group_members --------------------------------------------
    op.create_table(
        "query_group_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_query_group_members_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["query_group_id"], ["query_groups.id"],
            name="fk_query_group_members_query_group_id_query_groups", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["query_id"], ["queries.id"],
            name="fk_query_group_members_query_id_queries", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_query_group_members"),
        sa.UniqueConstraint("query_group_id", "query_id", name="uq_query_group_members_group_id_query_id"),
    )
    op.create_index("ix_query_group_members_organization_id", "query_group_members", ["organization_id"])
    op.create_index("ix_query_group_members_query_group_id", "query_group_members", ["query_group_id"])
    op.create_index("ix_query_group_members_query_id", "query_group_members", ["query_id"])

    # --- query_clusters --------------------------------------------------
    op.create_table(
        "query_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_query_clusters_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_query_clusters"),
    )
    op.create_index("ix_query_clusters_organization_id", "query_clusters", ["organization_id"])

    # --- query_cluster_members -------------------------------------------
    op.create_table(
        "query_cluster_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Numeric(4, 3), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_query_cluster_members_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["query_cluster_id"], ["query_clusters.id"],
            name="fk_query_cluster_members_query_cluster_id_query_clusters", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["query_id"], ["queries.id"],
            name="fk_query_cluster_members_query_id_queries", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_query_cluster_members"),
        sa.UniqueConstraint("query_cluster_id", "query_id", name="uq_query_cluster_members_cluster_id_query_id"),
    )
    op.create_index("ix_query_cluster_members_organization_id", "query_cluster_members", ["organization_id"])
    op.create_index("ix_query_cluster_members_query_cluster_id", "query_cluster_members", ["query_cluster_id"])
    op.create_index("ix_query_cluster_members_query_id", "query_cluster_members", ["query_id"])


def downgrade() -> None:
    op.drop_index("ix_query_cluster_members_query_id", table_name="query_cluster_members")
    op.drop_index("ix_query_cluster_members_query_cluster_id", table_name="query_cluster_members")
    op.drop_index("ix_query_cluster_members_organization_id", table_name="query_cluster_members")
    op.drop_table("query_cluster_members")

    op.drop_index("ix_query_clusters_organization_id", table_name="query_clusters")
    op.drop_table("query_clusters")

    op.drop_index("ix_query_group_members_query_id", table_name="query_group_members")
    op.drop_index("ix_query_group_members_query_group_id", table_name="query_group_members")
    op.drop_index("ix_query_group_members_organization_id", table_name="query_group_members")
    op.drop_table("query_group_members")

    op.drop_index("ix_query_groups_target_entity_id", table_name="query_groups")
    op.drop_index("ix_query_groups_organization_id", table_name="query_groups")
    op.drop_table("query_groups")

    op.drop_index("uq_intents_query_id_primary", table_name="intents")
    op.drop_index("ix_intents_product_id", table_name="intents")
    op.drop_index("ix_intents_entity_id", table_name="intents")
    op.drop_index("ix_intents_intent_type", table_name="intents")
    op.drop_index("ix_intents_query_id", table_name="intents")
    op.drop_index("ix_intents_organization_id", table_name="intents")
    op.drop_table("intents")

    op.drop_index("ix_query_provenance_query_id", table_name="query_provenance")
    op.drop_index("ix_query_provenance_organization_id", table_name="query_provenance")
    op.drop_table("query_provenance")

    op.drop_index("ix_queries_status", table_name="queries")
    op.drop_index("ix_queries_normalized_query", table_name="queries")
    op.drop_index("ix_queries_organization_id", table_name="queries")
    op.drop_table("queries")

    bind = op.get_bind()
    postgresql.ENUM(name="intent_classification_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="intent_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="query_priority").drop(bind, checkfirst=True)
    postgresql.ENUM(name="query_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="query_source").drop(bind, checkfirst=True)

    # Reverse the additive research_reference_type extension: Postgres
    # has no "DROP VALUE", so rebuild the type with the original
    # (Phase 5) value set, repoint the one column that uses it, and
    # drop the temporary type - the standard, correct way to reverse
    # an ADD VALUE.
    #
    # !! DESTRUCTIVE STEP, NAMED EXPLICITLY !! The DELETE below is a
    # genuine, irreversible data loss: any ResearchTaskReference row
    # created with reference_type='query'/'query_group' after this
    # migration's upgrade() ran is deleted, not preserved, because
    # those two values have no equivalent in the Phase 5 enum being
    # restored. This is fine for the dev/CI migration-cycle check
    # (scripts/verify_migration_cycle.sh) this downgrade path exists
    # to support, and fine for a genuinely unused/rolled-back
    # deployment. It is NOT fine to run against a production database
    # that has real query/query_group references in it without first
    # taking a backup (or exporting the affected rows) - downgrading
    # this migration in production should be treated as a data-loss
    # operation requiring explicit sign-off, not a routine rollback.
    op.execute(
        "DELETE FROM research_task_references WHERE reference_type IN ('query', 'query_group')"
    )
    op.execute("ALTER TYPE research_reference_type RENAME TO research_reference_type_old")
    research_reference_type_restored = postgresql.ENUM(
        "source", "document", "evidence", "claim", "knowledge_object", "knowledge_gap",
        name="research_reference_type",
    )
    research_reference_type_restored.create(bind, checkfirst=True)
    op.execute(
        "ALTER TABLE research_task_references "
        "ALTER COLUMN reference_type TYPE research_reference_type "
        "USING reference_type::text::research_reference_type"
    )
    op.execute("DROP TYPE research_reference_type_old")
