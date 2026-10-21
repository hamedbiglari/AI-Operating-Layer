"""Knowledge Transfer Packages and the AI-job output contract (prompt v5 §21, §51-53; ADR-134).
Additive and reversible: a new table, and `ai_jobs.output_contract` (NULL = free text, as before).

Revision ID: 0044
Revises: 0043
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "knowledge_transfer_packages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_object_id", UUID, nullable=False),
        sa.Column("submitted_by", sa.String(120), nullable=False),
        sa.Column("execution_id", UUID, nullable=True),
        sa.Column("job_key", sa.String(200), nullable=True),
        sa.Column("item_key", sa.String(200), nullable=True),
        sa.Column("package_hash", sa.String(64), nullable=False),
        sa.Column("raw", sa.Text(), nullable=False),
        sa.Column("ktp_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("invalid_reason", sa.String(500), nullable=True),
        sa.Column("validation", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("reconciliation", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "package_hash", name="uq_knowledge_transfer_packages_hash"),
        # Composite: the topic must belong to the same organization (ADR-037).
        sa.ForeignKeyConstraint(["knowledge_object_id", "organization_id"],
                                ["knowledge_objects.id", "knowledge_objects.organization_id"],
                                ondelete="CASCADE", name="fk_knowledge_transfer_packages_ko"),
        sa.CheckConstraint("status IN ('invalid', 'reconciled', 'partially_reconciled', 'nothing_accepted')",
                           name=op.f("ck_knowledge_transfer_packages_status")),
        sa.CheckConstraint("status <> 'invalid' OR invalid_reason IS NOT NULL",
                           name=op.f("ck_knowledge_transfer_packages_invalid_needs_reason")),
    )
    op.create_index("ix_knowledge_transfer_packages_organization_id", "knowledge_transfer_packages",
                    ["organization_id"])
    op.create_index("ix_knowledge_transfer_packages_ko", "knowledge_transfer_packages",
                    ["organization_id", "knowledge_object_id", "created_at"])
    op.add_column("ai_jobs", sa.Column("output_contract", sa.String(40), nullable=True))
    op.create_check_constraint(op.f("ck_ai_jobs_output_contract"), "ai_jobs",
                               "output_contract IS NULL OR output_contract IN ('ktp_v1')")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_ai_jobs_output_contract"), "ai_jobs", type_="check")
    op.drop_column("ai_jobs", "output_contract")
    op.drop_index("ix_knowledge_transfer_packages_ko", table_name="knowledge_transfer_packages")
    op.drop_index("ix_knowledge_transfer_packages_organization_id", table_name="knowledge_transfer_packages")
    op.drop_table("knowledge_transfer_packages")
