"""Full indirect-evidence route vocabulary + multi-compound research questions (ADR-108). Additive.

Revision ID: 0029
Revises: 0028
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = ("direct_subject", "compound_human", "mechanistic", "co_occurrence", "general")
NEW = OLD + ("indirect_taxonomic", "indirect_analogous_species", "indirect_formulation", "combination", "background")
_q = lambda v: ", ".join(f"'{x}'" for x in v)  # noqa: E731
DIRECT_OK = ("direct_subject", "general")       # every other route is indirect by construction


def upgrade() -> None:
    op.drop_constraint(op.f("ck_evidence_route"), "evidence", type_="check")
    op.create_check_constraint("route", "evidence", f"evidence_route IS NULL OR evidence_route IN ({_q(NEW)})")
    op.drop_constraint(op.f("ck_evidence_compound_route_is_indirect"), "evidence", type_="check")
    op.create_check_constraint("compound_route_is_indirect", "evidence",
        f"evidence_route IS NULL OR evidence_route IN ({_q(DIRECT_OK)}) OR directness = 'indirect'")
    op.drop_constraint(op.f("ck_research_queries_route"), "research_queries", type_="check")
    op.create_check_constraint("route", "research_queries", f"route IN ({_q(NEW)})")
    # a question may name several compounds; `compound` stays as the first one for existing rows
    op.add_column("research_questions", sa.Column("compounds", postgresql.JSON()))
    op.add_column("research_questions", sa.Column("related_species", postgresql.JSON()))
    # which compound (or combination) a piece of evidence actually concerns
    op.add_column("evidence", sa.Column("evidence_about", sa.String(300)))
    op.execute("UPDATE research_questions SET compounds = json_build_array(compound) WHERE compound IS NOT NULL")


def downgrade() -> None:
    op.drop_column("evidence", "evidence_about")
    op.drop_column("research_questions", "related_species")
    op.drop_column("research_questions", "compounds")
    op.drop_constraint(op.f("ck_research_queries_route"), "research_queries", type_="check")
    op.execute(f"DELETE FROM research_queries WHERE route NOT IN ({_q(OLD)})")
    op.create_check_constraint("route", "research_queries", f"route IN ({_q(OLD)})")
    op.drop_constraint(op.f("ck_evidence_compound_route_is_indirect"), "evidence", type_="check")
    op.drop_constraint(op.f("ck_evidence_route"), "evidence", type_="check")
    op.execute(f"UPDATE evidence SET evidence_route = NULL WHERE evidence_route NOT IN ({_q(OLD)})")
    op.create_check_constraint("route", "evidence", f"evidence_route IS NULL OR evidence_route IN ({_q(OLD)})")
    op.create_check_constraint("compound_route_is_indirect", "evidence",
        f"evidence_route IS NULL OR evidence_route IN ({_q(DIRECT_OK)}) OR directness = 'indirect'")
