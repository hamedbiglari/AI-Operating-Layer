"""Wallet, append-only ledger, reservations, payments, webhook events (ADR-104). Additive.

Revision ID: 0026
Revises: 0025
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)
LEDGER = "'payment_captured', 'refund', 'credit_granted', 'credit_reversed', 'ai_usage_charge', 'manual_adjustment', 'reservation', 'release'"


def _ts():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False)]


def _org():
    return sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


def upgrade() -> None:
    op.create_table("wallets", sa.Column("id", UUID, primary_key=True), _org(),
                    sa.Column("currency", sa.String(3), nullable=False, server_default="USD"), *_ts(),
                    sa.UniqueConstraint("organization_id", name="uq_wallets_organization"))
    op.create_table("wallet_ledger_entries", sa.Column("id", UUID, primary_key=True), _org(),
                    sa.Column("wallet_id", UUID, sa.ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("entry_type", sa.String(30), nullable=False), sa.Column("amount_cents", sa.BigInteger(), nullable=False),
                    sa.Column("reservation_id", UUID), sa.Column("payment_id", UUID),
                    sa.Column("idempotency_key", sa.String(200), nullable=False), sa.Column("reference", sa.String(300)),
                    sa.Column("note", sa.Text()), *_ts(),
                    sa.CheckConstraint(f"entry_type IN ({LEDGER})", name="entry_type"),
                    sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_ledger_idempotency"))
    op.create_table("wallet_reservations", sa.Column("id", UUID, primary_key=True), _org(),
                    sa.Column("wallet_id", UUID, sa.ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("amount_cents", sa.BigInteger(), nullable=False), sa.Column("settled_cents", sa.BigInteger()),
                    sa.Column("status", sa.String(20), nullable=False, server_default="held"), sa.Column("reference", sa.String(300)),
                    sa.Column("idempotency_key", sa.String(200), nullable=False), sa.Column("closed_at", sa.TIMESTAMP(timezone=True)), *_ts(),
                    sa.CheckConstraint("status IN ('held', 'settled', 'released', 'expired')", name="status"),
                    sa.CheckConstraint("amount_cents > 0", name="positive_amount"),
                    sa.CheckConstraint("settled_cents IS NULL OR (settled_cents >= 0 AND settled_cents <= amount_cents)", name="settled_within_hold"),
                    sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_reservation_idempotency"))
    op.create_table("payments", sa.Column("id", UUID, primary_key=True), _org(),
                    sa.Column("wallet_id", UUID, sa.ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("provider", sa.String(30), nullable=False), sa.Column("provider_payment_id", sa.String(200), nullable=False),
                    sa.Column("amount_cents", sa.BigInteger(), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
                    sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
                    sa.Column("idempotency_key", sa.String(200), nullable=False), sa.Column("failure_reason", sa.Text()), *_ts(),
                    sa.CheckConstraint("status IN ('pending', 'succeeded', 'failed', 'cancelled')", name="status"),
                    sa.CheckConstraint("amount_cents > 0", name="positive_amount"),
                    sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_payment_idempotency"),
                    sa.UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_id"))
    op.create_table("payment_webhook_events", sa.Column("id", UUID, primary_key=True),
                    sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), index=True),
                    sa.Column("provider", sa.String(30), nullable=False), sa.Column("event_id", sa.String(200), nullable=False),
                    sa.Column("event_type", sa.String(80), nullable=False), sa.Column("payment_id", UUID),
                    sa.Column("payload", postgresql.JSON()), *_ts(),
                    sa.UniqueConstraint("provider", "event_id", name="uq_webhook_event"))
    # the ledger is append-only: no UPDATE, no DELETE (tenant offboarding cascades are allowed)
    op.execute("""
        CREATE OR REPLACE FUNCTION wallet_ledger_append_only() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' AND NOT EXISTS (SELECT 1 FROM organizations WHERE id = OLD.organization_id) THEN
            RETURN OLD;   -- organization already deleted: offboarding cascade
          END IF;
          RAISE EXCEPTION 'wallet ledger is append-only (% refused)', TG_OP;
        END; $$ LANGUAGE plpgsql;""")
    op.execute("CREATE TRIGGER trg_wallet_ledger_append_only BEFORE UPDATE OR DELETE ON wallet_ledger_entries "
               "FOR EACH ROW EXECUTE FUNCTION wallet_ledger_append_only();")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_wallet_ledger_append_only ON wallet_ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS wallet_ledger_append_only()")
    for t in ("payment_webhook_events", "payments", "wallet_reservations", "wallet_ledger_entries", "wallets"):
        op.drop_table(t)
