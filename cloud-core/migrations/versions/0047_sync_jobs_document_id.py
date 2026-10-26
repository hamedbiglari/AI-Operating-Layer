"""`sync_jobs.document_id` (Step 7C-2, decision D14a): an ingestion job's document as a real, indexed column, so
a document's jobs can be found without reading JSONB. Nullable: only document-ingestion jobs have one. ON DELETE
SET NULL keeps a job row for audit when its document goes. `payload.document_id` stays; readers of it are unchanged.

Style precedents:
  0028:25-26  op.add_column("sources", sa.Column("full_text_document_id", postgresql.UUID(as_uuid=True),
                                                 sa.ForeignKey("documents.id", ondelete="SET NULL")))
  0029:31-35  op.add_column("research_questions", sa.Column("compounds", postgresql.JSON()))
              op.execute("UPDATE research_questions SET compounds = json_build_array(compound) WHERE compound IS NOT NULL")

Revision ID: 0047
Revises: 0046
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Existing ingestion jobs get their column from the payload. Only rows still NULL are touched, so running it
# again changes nothing. A job whose document is gone (documents cascade with their source; jobs stay with the
# organization) keeps NULL rather than failing the foreign key. tests/test_sync_job_document_id.py runs this.
BACKFILL_SQL = (
    "UPDATE sync_jobs "
    "SET document_id = (payload->>'document_id')::uuid "
    "WHERE job_type = 'document_ingestion' "
    "  AND document_id IS NULL "
    "  AND payload ? 'document_id' "
    "  AND EXISTS (SELECT 1 FROM documents d "
    "              WHERE d.id = (sync_jobs.payload->>'document_id')::uuid "
    "                AND d.organization_id = sync_jobs.organization_id)"
)


def upgrade() -> None:
    op.add_column("sync_jobs", sa.Column("document_id", postgresql.UUID(as_uuid=True),
                                         sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True))
    op.execute(BACKFILL_SQL)
    op.create_index("ix_sync_jobs_document_id", "sync_jobs", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_sync_jobs_document_id", table_name="sync_jobs")
    op.drop_column("sync_jobs", "document_id")
