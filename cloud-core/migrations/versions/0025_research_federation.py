"""Pilot-ready research: source access model, evidence routes, federated research records,
extended keyword kinds. Additive; existing rows keep honest defaults (content_access='unknown',
full_text_accessed=false, review_status='not_reviewed').

Revision ID: 0025
Revises: 0024
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_KINDS = ("primary", "secondary", "long_tail", "question", "commercial", "transactional", "local", "scientific",
             "synonym", "alias", "alternative_spelling", "related_entity", "customer_question", "ai_query")
NEW_KINDS = OLD_KINDS + ("scientific_name", "common_name", "compound", "mechanism", "clinical_outcome", "safety_term",
                         "preparation_term", "dose_term", "language_variant")
_q = lambda v: ", ".join(f"'{x}'" for x in v)  # noqa: E731
UUID = postgresql.UUID(as_uuid=True)


def _ts():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False)]


def upgrade() -> None:
    # --- Source: existence / access / rights / acquisition / review kept apart ---
    op.add_column("sources", sa.Column("existence_status", sa.String(20), nullable=False, server_default="unconfirmed"))
    op.add_column("sources", sa.Column("content_access", sa.String(30), nullable=False, server_default="unknown"))
    op.add_column("sources", sa.Column("full_text_accessed", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("sources", sa.Column("accessed_parts", postgresql.JSON()))
    op.add_column("sources", sa.Column("acquisition_paths", postgresql.JSON()))
    op.add_column("sources", sa.Column("review_status", sa.String(20), nullable=False, server_default="not_reviewed"))
    op.add_column("sources", sa.Column("canonical_title", sa.String(1000)))
    op.add_column("sources", sa.Column("abstract", sa.Text()))
    op.create_check_constraint("existence_status", "sources", "existence_status IN ('confirmed', 'unconfirmed')")
    op.create_check_constraint("content_access", "sources",
        "content_access IN ('full_text_available', 'abstract_only', 'metadata_only', 'restricted', 'unavailable', 'unknown')")
    op.create_check_constraint("review_status", "sources", "review_status IN ('not_reviewed', 'in_review', 'reviewed')")
    # The rule of the whole pilot: full text is only ever claimed when the system actually holds it.
    op.create_check_constraint("full_text_claim_requires_access", "sources",
        "content_access <> 'full_text_available' OR full_text_accessed")
    op.create_index("ix_sources_org_doi", "sources", ["organization_id", "doi"])
    op.create_index("ix_sources_org_pmid", "sources", ["organization_id", "pmid"])
    op.create_index("ix_sources_org_canonical_title", "sources", ["organization_id", "canonical_title"])

    # --- Evidence: route + basis; routes other than direct_subject can never be direct ---
    op.add_column("evidence", sa.Column("evidence_route", sa.String(30)))
    op.add_column("evidence", sa.Column("subject_tested", sa.String(300)))
    op.add_column("evidence", sa.Column("basis", sa.String(20)))
    op.create_check_constraint("route", "evidence",
        "evidence_route IS NULL OR evidence_route IN ('direct_subject', 'compound_human', 'mechanistic', 'co_occurrence', 'general')")
    op.create_check_constraint("basis", "evidence", "basis IS NULL OR basis IN ('full_text', 'abstract', 'metadata')")
    op.create_check_constraint("compound_route_is_indirect", "evidence",
        "evidence_route IS NULL OR evidence_route IN ('direct_subject', 'general') OR directness = 'indirect'")

    # --- keyword kinds for research ---
    op.drop_constraint(op.f("ck_knowledge_keywords_kind"), "knowledge_keywords", type_="check")
    op.create_check_constraint("kind", "knowledge_keywords", f"kind IN ({_q(NEW_KINDS)})")

    # --- federated research records ---
    op.create_table("research_questions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="SET NULL")),
        sa.Column("research_project_id", UUID, sa.ForeignKey("research_projects.id", ondelete="SET NULL")),
        sa.Column("question_text", sa.Text(), nullable=False), sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("compound", sa.String(300)), sa.Column("outcome", sa.String(300)), sa.Column("population", sa.String(100)),
        *_ts())
    op.create_table("research_queries",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("research_task_id", UUID, sa.ForeignKey("research_tasks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("research_question_id", UUID, sa.ForeignKey("research_questions.id", ondelete="SET NULL"), index=True),
        sa.Column("mode", sa.String(20), nullable=False), sa.Column("route", sa.String(30), nullable=False, server_default="general"),
        sa.Column("query_text", sa.Text(), nullable=False), sa.Column("keyword_ids", postgresql.JSON()),
        sa.CheckConstraint("mode IN ('single', 'multi', 'exact', 'boolean', 'agent')", name="mode"),
        sa.CheckConstraint("route IN ('direct_subject', 'compound_human', 'mechanistic', 'co_occurrence', 'general')", name="route"),
        *_ts())
    op.create_table("research_provider_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("research_query_id", UUID, sa.ForeignKey("research_queries.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(40), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text()), sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer()),
        sa.CheckConstraint("status IN ('ok', 'failed', 'not_configured')", name="status"),
        *_ts())
    op.create_table("research_hits",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider_run_id", UUID, sa.ForeignKey("research_provider_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_id", UUID, sa.ForeignKey("sources.id", ondelete="SET NULL"), index=True),
        sa.Column("rank", sa.Integer(), nullable=False), sa.Column("external_id", sa.String(200)),
        sa.Column("doi", sa.String(300)), sa.Column("pmid", sa.String(40)), sa.Column("title", sa.Text()),
        sa.Column("merged_into_existing", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("matched_on", sa.String(20)),
        *_ts())


def downgrade() -> None:
    for t in ("research_hits", "research_provider_runs", "research_queries", "research_questions"):
        op.drop_table(t)
    op.drop_constraint(op.f("ck_knowledge_keywords_kind"), "knowledge_keywords", type_="check")
    op.execute(f"DELETE FROM knowledge_keywords WHERE kind NOT IN ({_q(OLD_KINDS)})")
    op.create_check_constraint("kind", "knowledge_keywords", f"kind IN ({_q(OLD_KINDS)})")
    for c in ("ck_evidence_compound_route_is_indirect", "ck_evidence_basis", "ck_evidence_route"):
        op.drop_constraint(op.f(c), "evidence", type_="check")
    for col in ("basis", "subject_tested", "evidence_route"):
        op.drop_column("evidence", col)
    for i in ("ix_sources_org_canonical_title", "ix_sources_org_pmid", "ix_sources_org_doi"):
        op.drop_index(i, table_name="sources")
    for c in ("ck_sources_full_text_claim_requires_access", "ck_sources_review_status", "ck_sources_content_access", "ck_sources_existence_status"):
        op.drop_constraint(op.f(c), "sources", type_="check")
    for col in ("abstract", "canonical_title", "review_status", "acquisition_paths", "accessed_parts", "full_text_accessed",
                "content_access", "existence_status"):
        op.drop_column("sources", col)
