"""customer_contexts, recommendations (Phase 8: Recommendation Engine)

Revision ID: 0009
Revises: 0008
Create Date: 2026-01-09 00:00:00

Phase 8: `customer_contexts` (section 32 - privacy-safe, no raw
conversation storage) and `recommendations` (section 33 - every score
accompanied by a SignalState so UNKNOWN stays distinguishable from
NEGATIVE, plus a structured JSONB `reason` and a `policy_version` for
reproducibility).

No prior migration is modified. Phase 7's tables are referenced by FK
only; nothing in `products`, `offers`, `product_evidence`,
`product_relations` or `trust_records` is altered - Phase 8 consumes
the Commerce domain through `app/contracts/commerce.py`, never by
reshaping it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCORE_COLUMNS = (
    "relevance_score", "evidence_score", "trust_score", "availability_score", "final_score",
)


def upgrade() -> None:
    bind = op.get_bind()

    context_type = postgresql.ENUM(
        "anonymous", "session", "customer", name="context_type", create_type=False)
    context_source = postgresql.ENUM(
        "web", "site_search", "ai_assistant", "merchant", "api",
        name="context_source", create_type=False)
    purchase_intent = postgresql.ENUM(
        "none", "researching", "comparing", "ready", name="purchase_intent", create_type=False)
    need_level = postgresql.ENUM("low", "normal", "high", name="need_level", create_type=False)
    price_sensitivity = postgresql.ENUM(
        "unknown", "low", "medium", "high", name="price_sensitivity", create_type=False)
    consent_status = postgresql.ENUM(
        "not_required", "granted", "withdrawn", name="consent_status", create_type=False)
    response_mode = postgresql.ENUM(
        "educate", "compare", "reassure", "recommend", "transact",
        name="response_mode", create_type=False)
    recommendation_status = postgresql.ENUM(
        "not_eligible", "no_recommendation", "recommended_with_caveat", "recommended",
        name="recommendation_status", create_type=False)
    signal_state = postgresql.ENUM(
        "unknown", "partial", "established", "conflicting", "negative",
        name="signal_state", create_type=False)

    for enum_type in (
        context_type, context_source, purchase_intent, need_level, price_sensitivity,
        consent_status, response_mode, recommendation_status, signal_state,
    ):
        enum_type.create(bind, checkfirst=True)

    # `intent_type` already exists from migration 0007 (Phase 6) and is
    # reused here deliberately rather than duplicated - a context's
    # intent and a query's intent are the same kind of fact.
    intent_type = postgresql.ENUM(name="intent_type", create_type=False)

    op.create_table(
        "customer_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("context_type", context_type, nullable=False, server_default="anonymous"),
        sa.Column("intent", intent_type, nullable=True),
        sa.Column("topic", sa.String(length=500), nullable=True),
        sa.Column("purchase_intent", purchase_intent, nullable=False, server_default="none"),
        sa.Column("evidence_need", need_level, nullable=False, server_default="normal"),
        sa.Column("trust_need", need_level, nullable=False, server_default="normal"),
        sa.Column("price_sensitivity", price_sensitivity, nullable=False, server_default="unknown"),
        sa.Column("product_interest", sa.String(length=500), nullable=True),
        sa.Column("preferences", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("consent_status", consent_status, nullable=False, server_default="not_required"),
        sa.Column("source", context_source, nullable=False, server_default="api"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_customer_contexts_organization_id_organizations", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_customer_contexts"),
    )
    op.create_index("ix_customer_contexts_organization_id", "customer_contexts", ["organization_id"])
    op.create_index("ix_customer_contexts_customer_id", "customer_contexts", ["customer_id"])
    op.create_index("ix_customer_contexts_session_id", "customer_contexts", ["session_id"])
    op.create_index("ix_customer_contexts_consent_status", "customer_contexts", ["consent_status"])

    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_context_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("knowledge_object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("response_mode", response_mode, nullable=False),
        sa.Column("relevance_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("evidence_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("trust_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("availability_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("final_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("evidence_state", signal_state, nullable=False, server_default="unknown"),
        sa.Column("trust_state", signal_state, nullable=False, server_default="unknown"),
        sa.Column("reason", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", recommendation_status, nullable=False),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_recommendations_organization_id_organizations", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["customer_context_id"], ["customer_contexts.id"],
            name="fk_recommendations_customer_context_id_customer_contexts", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"],
            name="fk_recommendations_product_id_products", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["offer_id"], ["offers.id"],
            name="fk_recommendations_offer_id_offers", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["query_id"], ["queries.id"],
            name="fk_recommendations_query_id_queries", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["knowledge_object_id"], ["knowledge_objects.id"],
            name="fk_recommendations_knowledge_object_id_knowledge_objects", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_recommendations"),
        *[
            sa.CheckConstraint(f"{c} >= 0 AND {c} <= 1", name=f"ck_recommendations_{c}_range")
            for c in _SCORE_COLUMNS
        ],
    )
    op.create_index("ix_recommendations_organization_id", "recommendations", ["organization_id"])
    op.create_index("ix_recommendations_customer_context_id", "recommendations", ["customer_context_id"])
    op.create_index("ix_recommendations_product_id", "recommendations", ["product_id"])
    op.create_index("ix_recommendations_offer_id", "recommendations", ["offer_id"])
    op.create_index("ix_recommendations_query_id", "recommendations", ["query_id"])
    op.create_index("ix_recommendations_knowledge_object_id", "recommendations", ["knowledge_object_id"])
    op.create_index("ix_recommendations_final_score", "recommendations", ["final_score"])
    op.create_index("ix_recommendations_status", "recommendations", ["status"])


def downgrade() -> None:
    for idx in (
        "ix_recommendations_status", "ix_recommendations_final_score",
        "ix_recommendations_knowledge_object_id", "ix_recommendations_query_id",
        "ix_recommendations_offer_id", "ix_recommendations_product_id",
        "ix_recommendations_customer_context_id", "ix_recommendations_organization_id",
    ):
        op.drop_index(idx, table_name="recommendations")
    op.drop_table("recommendations")

    for idx in (
        "ix_customer_contexts_consent_status", "ix_customer_contexts_session_id",
        "ix_customer_contexts_customer_id", "ix_customer_contexts_organization_id",
    ):
        op.drop_index(idx, table_name="customer_contexts")
    op.drop_table("customer_contexts")

    bind = op.get_bind()
    # intent_type is NOT dropped - it is owned by migration 0007
    # (Phase 6) and other tables still use it.
    for name in (
        "signal_state", "recommendation_status", "response_mode", "consent_status",
        "price_sensitivity", "need_level", "purchase_intent", "context_source", "context_type",
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
