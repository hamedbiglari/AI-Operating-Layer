"""RETRYING + document_ingestion job type; drop dead visibility_job_status

Revision ID: 0014
Revises: 0013
Create Date: 2026-01-14 00:00:00

Three changes, all consequences of the Phase 12 remediation audit:

1. `sync_job_status` gains `retrying` (P12-02 requires it in the job-state
   contract). Distinct from `failed`: a retry is scheduled, so an operator
   can tell work that is still moving from work that has stopped.

2. `sync_job_type` gains `document_ingestion` (P12-02). Document conversion
   reuses the canonical SyncJob model rather than introducing a second job
   system - ADR-068.

3. `visibility_job_status` is DROPPED. It was created in migration 0012 and
   never used by any model or service - dead architecture (P12-17). Keeping
   a second job-state vocabulary alongside SyncJobStatus would be the
   duplicate-domain fault the contract forbids.

Dropping an unused enum type is non-destructive: no column references it,
verified before writing this migration.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in
    # older PostgreSQL; 12+ allows it, and this project targets 16.
    op.execute("ALTER TYPE sync_job_status ADD VALUE IF NOT EXISTS 'retrying'")
    op.execute("ALTER TYPE sync_job_type ADD VALUE IF NOT EXISTS 'document_ingestion'")

    # Safe because nothing references it - confirmed by inspecting
    # pg_depend before authoring this migration.
    op.execute("DROP TYPE IF EXISTS visibility_job_status")


def downgrade() -> None:
    # Recreate the dead type so the schema round-trips exactly.
    op.execute(
        "CREATE TYPE visibility_job_status AS ENUM "
        "('queued','running','succeeded','failed','dead_letter','cancelled','budget_exceeded')"
    )
    # PostgreSQL cannot remove a value from an enum type. Removing
    # 'retrying'/'document_ingestion' would require recreating both types
    # and rewriting every dependent column - destructive, and the contract
    # forbids destructive migrations without explicit reason. The added
    # values are left in place; they are inert when unused.
