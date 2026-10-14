"""knowledge core: objects, entities, claims, relationships, versions, gaps

Revision ID: 0003
Revises: 0002
Create Date: 2026-01-03 00:00:00

Phase 2: the Knowledge Core. Table creation order follows the FK
dependency chain: knowledge_objects -> entities -> claims (needs both
knowledge_objects and entities) -> relationships (no cross-table FK,
see app/models/relationship.py) -> knowledge_versions -> knowledge_gaps.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    knowledge_object_status = postgresql.ENUM(
        "draft", "in_review", "published", "archived",
        name="knowledge_object_status", create_type=False,
    )
    claim_status = postgresql.ENUM(
        "draft", "pending_review", "approved", "rejected", "disputed", "deprecated",
        name="claim_status", create_type=False,
    )
    claim_evidence_strength = postgresql.ENUM(
        "unverified", "insufficient", "weak", "moderate", "strong", "conflicting",
        name="claim_evidence_strength", create_type=False,
    )
    relationship_status = postgresql.ENUM(
        "active", "disputed", "deprecated",
        name="relationship_status", create_type=False,
    )
    graph_node_type = postgresql.ENUM(
        "entity", "knowledge_object",
        name="graph_node_type", create_type=False,
    )
    gap_type = postgresql.ENUM(
        "content_gap", "entity_gap", "claim_gap", "evidence_gap", "source_gap",
        "access_gap", "relation_gap", "freshness_gap", "conflict_gap", "research_gap",
        name="gap_type", create_type=False,
    )
    gap_priority = postgresql.ENUM(
        "low", "medium", "high", "critical",
        name="gap_priority", create_type=False,
    )
    gap_status = postgresql.ENUM(
        "open", "in_progress", "resolved", "dismissed",
        name="gap_status", create_type=False,
    )
    gap_recommended_action = postgresql.ENUM(
        "search_more", "expand_search", "search_related_entity", "search_compound",
        "search_mechanism", "search_related_plant", "search_clinical_database",
        "search_primary_studies", "search_secondary_studies", "request_full_text",
        "request_user_source", "request_pdf", "request_dataset", "request_expert_review",
        "run_analysis", "compare_evidence", "resolve_conflict", "wait_for_new_evidence",
        "keep_gap_open",
        name="gap_recommended_action", create_type=False,
    )

    for enum_type in (
        knowledge_object_status, claim_status, claim_evidence_strength,
        relationship_status, graph_node_type, gap_type, gap_priority,
        gap_status, gap_recommended_action,
    ):
        enum_type.create(bind, checkfirst=True)

    # --- knowledge_objects ---------------------------------------------
    op.create_table(
        "knowledge_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_name", sa.String(length=500), nullable=False),
        sa.Column("slug", sa.String(length=500), nullable=False),
        sa.Column("object_type", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", knowledge_object_status, nullable=False, server_default="draft"),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("public_visibility", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ai_visibility", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_knowledge_objects_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_objects"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_knowledge_objects_organization_slug"),
    )
    op.create_index("ix_knowledge_objects_organization_id", "knowledge_objects", ["organization_id"])
    op.create_index("ix_knowledge_objects_object_type", "knowledge_objects", ["object_type"])

    # --- entities --------------------------------------------------------
    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("canonical_name", sa.String(length=500), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=True),
        sa.Column("external_ids", postgresql.JSONB(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_entities_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_object_id"], ["knowledge_objects.id"],
            name="fk_entities_knowledge_object_id_knowledge_objects", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_entities"),
    )
    op.create_index("ix_entities_organization_id", "entities", ["organization_id"])
    op.create_index("ix_entities_knowledge_object_id", "entities", ["knowledge_object_id"])
    op.create_index("ix_entities_entity_type", "entities", ["entity_type"])
    op.create_index("ix_entities_canonical_name", "entities", ["canonical_name"])

    # --- claims ------------------------------------------------------------
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("predicate", sa.String(length=200), nullable=False),
        sa.Column("object_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("object_value", sa.Text(), nullable=True),
        sa.Column("claim_type", sa.String(length=100), nullable=True),
        sa.Column("evidence_strength", claim_evidence_strength, nullable=False, server_default="unverified"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("status", claim_status, nullable=False, server_default="draft"),
        sa.Column("source_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("human_reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_claims_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_object_id"], ["knowledge_objects.id"],
            name="fk_claims_knowledge_object_id_knowledge_objects", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["subject_entity_id"], ["entities.id"],
            name="fk_claims_subject_entity_id_entities", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["object_entity_id"], ["entities.id"],
            name="fk_claims_object_entity_id_entities", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claims"),
        sa.CheckConstraint(
            "(object_entity_id IS NOT NULL AND object_value IS NULL) "
            "OR (object_entity_id IS NULL AND object_value IS NOT NULL)",
            name="ck_claims_object_entity_xor_value",
        ),
    )
    op.create_index("ix_claims_organization_id", "claims", ["organization_id"])
    op.create_index("ix_claims_knowledge_object_id", "claims", ["knowledge_object_id"])
    op.create_index("ix_claims_subject_entity_id", "claims", ["subject_entity_id"])
    op.create_index("ix_claims_object_entity_id", "claims", ["object_entity_id"])
    op.create_index("ix_claims_predicate", "claims", ["predicate"])
    op.create_index("ix_claims_claim_type", "claims", ["claim_type"])

    # --- relationships -------------------------------------------------------
    op.create_table(
        "relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_type", graph_node_type, nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("predicate", sa.String(length=200), nullable=False),
        sa.Column("object_type", graph_node_type, nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", relationship_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_relationships_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_relationships"),
    )
    op.create_index("ix_relationships_organization_id", "relationships", ["organization_id"])
    op.create_index("ix_relationships_subject_id", "relationships", ["subject_id"])
    op.create_index("ix_relationships_object_id", "relationships", ["object_id"])
    op.create_index("ix_relationships_predicate", "relationships", ["predicate"])

    # --- knowledge_versions ------------------------------------------------
    op.create_table(
        "knowledge_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_knowledge_versions_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_object_id"], ["knowledge_objects.id"],
            name="fk_knowledge_versions_knowledge_object_id_knowledge_objects", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            name="fk_knowledge_versions_created_by_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_versions"),
        sa.UniqueConstraint("knowledge_object_id", "version", name="uq_knowledge_versions_object_version"),
    )
    op.create_index("ix_knowledge_versions_organization_id", "knowledge_versions", ["organization_id"])
    op.create_index("ix_knowledge_versions_knowledge_object_id", "knowledge_versions", ["knowledge_object_id"])
    op.create_index("ix_knowledge_versions_created_by", "knowledge_versions", ["created_by"])

    # --- knowledge_gaps ------------------------------------------------------
    op.create_table(
        "knowledge_gaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gap_type", gap_type, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", gap_priority, nullable=False, server_default="medium"),
        sa.Column("status", gap_status, nullable=False, server_default="open"),
        sa.Column("recommended_action", gap_recommended_action, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_knowledge_gaps_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_object_id"], ["knowledge_objects.id"],
            name="fk_knowledge_gaps_knowledge_object_id_knowledge_objects", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_gaps"),
    )
    op.create_index("ix_knowledge_gaps_organization_id", "knowledge_gaps", ["organization_id"])
    op.create_index("ix_knowledge_gaps_knowledge_object_id", "knowledge_gaps", ["knowledge_object_id"])
    op.create_index("ix_knowledge_gaps_gap_type", "knowledge_gaps", ["gap_type"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_gaps_knowledge_object_id", table_name="knowledge_gaps")
    op.drop_index("ix_knowledge_gaps_organization_id", table_name="knowledge_gaps")
    op.drop_index("ix_knowledge_gaps_gap_type", table_name="knowledge_gaps")
    op.drop_table("knowledge_gaps")

    op.drop_index("ix_knowledge_versions_created_by", table_name="knowledge_versions")
    op.drop_index("ix_knowledge_versions_knowledge_object_id", table_name="knowledge_versions")
    op.drop_index("ix_knowledge_versions_organization_id", table_name="knowledge_versions")
    op.drop_table("knowledge_versions")

    op.drop_index("ix_relationships_predicate", table_name="relationships")
    op.drop_index("ix_relationships_object_id", table_name="relationships")
    op.drop_index("ix_relationships_subject_id", table_name="relationships")
    op.drop_index("ix_relationships_organization_id", table_name="relationships")
    op.drop_table("relationships")

    op.drop_index("ix_claims_claim_type", table_name="claims")
    op.drop_index("ix_claims_predicate", table_name="claims")
    op.drop_index("ix_claims_object_entity_id", table_name="claims")
    op.drop_index("ix_claims_subject_entity_id", table_name="claims")
    op.drop_index("ix_claims_knowledge_object_id", table_name="claims")
    op.drop_index("ix_claims_organization_id", table_name="claims")
    op.drop_table("claims")

    op.drop_index("ix_entities_canonical_name", table_name="entities")
    op.drop_index("ix_entities_entity_type", table_name="entities")
    op.drop_index("ix_entities_knowledge_object_id", table_name="entities")
    op.drop_index("ix_entities_organization_id", table_name="entities")
    op.drop_table("entities")

    op.drop_index("ix_knowledge_objects_object_type", table_name="knowledge_objects")
    op.drop_index("ix_knowledge_objects_organization_id", table_name="knowledge_objects")
    op.drop_table("knowledge_objects")

    bind = op.get_bind()
    for enum_name in (
        "gap_recommended_action", "gap_status", "gap_priority", "gap_type",
        "graph_node_type", "relationship_status", "claim_evidence_strength",
        "claim_status", "knowledge_object_status",
    ):
        postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
