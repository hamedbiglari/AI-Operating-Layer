"""Authenticated knowledge chat: per-organisation chat settings, conversations, messages with an explicit
answer state, resolved citations, feedback and the research-request approval trail (master prompt §13-§14;
ADR-128). Additive and reversible — no existing table or column is changed.

Revision ID: 0040
Revises: 0039
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSON()

ANSWER_STATES = ("ANSWERED_FROM_KNOWLEDGE", "PARTIAL_ANSWER", "CONFLICTED", "NEEDS_WEB_RESEARCH",
                 "NEEDS_USER_SOURCE", "UNKNOWN", "PROVIDER_UNAVAILABLE", "PROCESSING")
MESSAGE_ROLES = ("user", "assistant")
RESEARCH_MODES = ("disabled", "ask_every_time", "preauthorized")
REQUEST_STATES = ("pending_approval", "approved", "running", "completed", "cancelled", "rejected", "failed")
FEEDBACK_RATINGS = ("helpful", "not_helpful", "wrong", "incomplete")
CONVERSATION_STATES = ("active", "archived")


def _q(v):
    return ", ".join(f"'{x}'" for x in v)


def _ts():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False)]


def _org():
    return sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False, index=True)


def upgrade() -> None:
    # --- §14: the dashboard's control surface. No row = the chat is off for that tenant.
    op.create_table(
        "chat_settings",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allowed_knowledge_object_ids", JSON, nullable=False, server_default="[]"),
        sa.Column("online_research", sa.String(20), nullable=False, server_default="ask_every_time"),
        sa.Column("routing_policy_id", UUID, sa.ForeignKey("ai_routing_policies.id", ondelete="SET NULL")),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default="1200"),
        sa.Column("context_token_budget", sa.Integer(), nullable=False, server_default="24000"),
        sa.Column("show_citations", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("collect_feedback", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("retention_days", sa.Integer()),
        sa.Column("messages_per_user_per_day", sa.Integer(), server_default="100"),
        sa.Column("max_cost_per_message", sa.Numeric(12, 4)),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_ts(),
        sa.UniqueConstraint("organization_id", name="uq_chat_settings_organization"),
        sa.CheckConstraint(f"online_research IN ({_q(RESEARCH_MODES)})", name="ck_chat_settings_online_research"),
        sa.CheckConstraint("max_output_tokens BETWEEN 128 AND 32000", name="ck_chat_settings_max_output_tokens_range"),
        sa.CheckConstraint("context_token_budget BETWEEN 2000 AND 400000",
                           name="ck_chat_settings_context_token_budget_range"),
        sa.CheckConstraint("retention_days IS NULL OR retention_days >= 1",
                           name="ck_chat_settings_retention_days_positive"),
        sa.CheckConstraint("messages_per_user_per_day IS NULL OR messages_per_user_per_day >= 1",
                           name="ck_chat_settings_daily_limit_positive"),
        sa.CheckConstraint("max_cost_per_message IS NULL OR max_cost_per_message > 0",
                           name="ck_chat_settings_cost_cap_positive"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(300)),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="SET NULL"), index=True),
        sa.Column("language", sa.String(10)),
        sa.Column("state", sa.String(20), nullable=False, server_default="active"),
        sa.Column("archived_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_message_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        *_ts(),
        sa.CheckConstraint(f"state IN ({_q(CONVERSATION_STATES)})", name="ck_conversations_state"),
        sa.CheckConstraint("message_count >= 0", name="ck_conversations_message_count_not_negative"),
    )
    op.create_index("ix_conversations_owner", "conversations",
                    ["organization_id", "user_id", "state", "last_message_at"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("conversation_id", UUID, sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("answer_state", sa.String(30)),
        sa.Column("limitation", sa.Text()),
        sa.Column("attachments", JSON, nullable=False, server_default="[]"),
        sa.Column("retrieval", JSON),
        sa.Column("grounding", JSON),
        sa.Column("ai_execution_id", UUID, sa.ForeignKey("ai_executions.id", ondelete="SET NULL")),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cost", sa.Numeric(12, 6)),
        sa.Column("cost_currency", sa.String(3)),
        sa.Column("stop_reason", sa.String(40)),
        sa.Column("error", sa.Text()),
        sa.Column("answers_message_id", UUID, sa.ForeignKey("conversation_messages.id", ondelete="SET NULL")),
        *_ts(),
        sa.UniqueConstraint("conversation_id", "position", name="uq_conversation_message_position"),
        sa.CheckConstraint("position >= 1", name="ck_conversation_messages_position_positive"),
        sa.CheckConstraint(f"role IN ({_q(MESSAGE_ROLES)})", name="ck_conversation_messages_role"),
        sa.CheckConstraint(f"answer_state IS NULL OR answer_state IN ({_q(ANSWER_STATES)})",
                           name="ck_conversation_messages_answer_state"),
        sa.CheckConstraint("(role = 'user' AND answer_state IS NULL) "
                           "OR (role = 'assistant' AND answer_state IS NOT NULL)",
                           name="ck_conversation_messages_only_assistant_turns_have_an_answer_state"),
    )
    op.create_index("ix_conversation_messages_thread", "conversation_messages", ["conversation_id", "position"])

    op.create_table(
        "conversation_citations",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("message_id", UUID, sa.ForeignKey("conversation_messages.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("claim_id", UUID, sa.ForeignKey("claims.id", ondelete="SET NULL")),
        sa.Column("evidence_id", UUID, sa.ForeignKey("evidence.id", ondelete="SET NULL")),
        sa.Column("source_id", UUID, sa.ForeignKey("sources.id", ondelete="SET NULL")),
        sa.Column("directness", sa.String(20)),
        sa.Column("page_number", sa.Integer()),
        sa.Column("location", JSON),
        sa.Column("contested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("claim_text", sa.Text()),
        *_ts(),
        sa.UniqueConstraint("message_id", "ordinal", name="uq_conversation_citation_ordinal"),
        sa.CheckConstraint("ordinal >= 1", name="ck_conversation_citations_ordinal_positive"),
    )
    op.create_index("ix_conversation_citations_message", "conversation_citations", ["message_id", "ordinal"])

    op.create_table(
        "conversation_feedback",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("message_id", UUID, sa.ForeignKey("conversation_messages.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("rating", sa.String(20), nullable=False),
        sa.Column("note", sa.Text()),
        *_ts(),
        sa.UniqueConstraint("message_id", "user_id", name="uq_conversation_feedback_once"),
        sa.CheckConstraint(f"rating IN ({_q(FEEDBACK_RATINGS)})", name="ck_conversation_feedback_rating"),
    )

    op.create_table(
        "conversation_research_requests",
        sa.Column("id", UUID, primary_key=True),
        _org(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("conversation_id", UUID, sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("message_id", UUID, sa.ForeignKey("conversation_messages.id", ondelete="SET NULL")),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("knowledge_object_id", UUID, sa.ForeignKey("knowledge_objects.id", ondelete="SET NULL")),
        sa.Column("proposed_scope", JSON, nullable=False, server_default="{}"),
        sa.Column("state", sa.String(30), nullable=False, server_default="pending_approval"),
        sa.Column("authorization_basis", sa.String(40)),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("decided_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("research_project_id", UUID, sa.ForeignKey("research_projects.id", ondelete="SET NULL")),
        sa.Column("knowledge_gap_id", UUID, sa.ForeignKey("knowledge_gaps.id", ondelete="SET NULL")),
        sa.Column("reanswer_message_id", UUID, sa.ForeignKey("conversation_messages.id", ondelete="SET NULL")),
        sa.Column("sources_added", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        *_ts(),
        sa.CheckConstraint(f"state IN ({_q(REQUEST_STATES)})", name="ck_conversation_research_requests_state"),
        sa.CheckConstraint("state NOT IN ('approved', 'running', 'completed') OR decided_at IS NOT NULL",
                           name="ck_conversation_research_requests_a_started_request_has_a_decision"),
        sa.CheckConstraint("state <> 'failed' OR error IS NOT NULL",
                           name="ck_conversation_research_requests_a_failure_needs_a_reason"),
    )
    op.create_index("ix_conversation_research_requests_owner", "conversation_research_requests",
                    ["organization_id", "user_id", "state", "created_at"])


def downgrade() -> None:
    op.drop_table("conversation_research_requests")
    op.drop_table("conversation_feedback")
    op.drop_table("conversation_citations")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
    op.drop_table("chat_settings")
