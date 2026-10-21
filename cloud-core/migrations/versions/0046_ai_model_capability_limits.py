"""Provider capability metadata on `ai_models` (prompt v5 §7, §16; ADR-136): max input/output tokens, RPM/TPM,
structured-output and tool flags, and where the figures came from. Every column is nullable: NULL means unknown,
which is what every existing row is. Additive and reversible.

Revision ID: 0046
Revises: 0045
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INT_COLUMNS = ("max_input_tokens", "max_output_tokens", "rpm_limit", "tpm_limit")
_SOURCES = "('official_docs', 'provider_api', 'operator', 'conservative_estimate')"


def upgrade() -> None:
    for name in _INT_COLUMNS:
        op.add_column("ai_models", sa.Column(name, sa.Integer(), nullable=True))
    op.add_column("ai_models", sa.Column("supports_structured_output", sa.Boolean(), nullable=True))
    op.add_column("ai_models", sa.Column("supports_tools", sa.Boolean(), nullable=True))
    op.add_column("ai_models", sa.Column("capability_source", sa.String(40), nullable=True))
    op.create_check_constraint(op.f("ck_ai_models_capability_source"), "ai_models",
                               f"capability_source IS NULL OR capability_source IN {_SOURCES}")
    op.create_check_constraint(op.f("ck_ai_models_limits_positive"), "ai_models",
                               " AND ".join(f"({c} IS NULL OR {c} > 0)" for c in _INT_COLUMNS))


def downgrade() -> None:
    op.drop_constraint(op.f("ck_ai_models_limits_positive"), "ai_models", type_="check")
    op.drop_constraint(op.f("ck_ai_models_capability_source"), "ai_models", type_="check")
    for name in ("capability_source", "supports_tools", "supports_structured_output", *reversed(_INT_COLUMNS)):
        op.drop_column("ai_models", name)
