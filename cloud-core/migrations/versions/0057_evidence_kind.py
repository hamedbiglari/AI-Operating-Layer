"""Evidence kind (V5-knowledge-detail-evidence-kind): what sort of evidence a row is - traditional use, compositional,
mechanistic, animal, human clinical or other - so a knowledge object can show its evidence per kind and never let one
kind stand in for another.

Additive and reversible. A new enum type and one nullable column; no existing row is touched (NULL = not classified
yet; automatic classification during extraction is V5-evidence-kind-autoclassify).

Revision ID: 0057
Revises: 0056
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KINDS = ("traditional_use", "compositional", "mechanistic", "animal", "human_clinical", "other")


def upgrade() -> None:
    kind = postgresql.ENUM(*KINDS, name="evidence_kind")
    kind.create(op.get_bind(), checkfirst=True)
    op.add_column("evidence", sa.Column("kind", postgresql.ENUM(*KINDS, name="evidence_kind", create_type=False), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence", "kind")
    postgresql.ENUM(name="evidence_kind").drop(op.get_bind(), checkfirst=True)
