"""Device Intelligence platform signals (ADR-138 amendment, master prompt §16–17).

device_observations gains:
* os_install_pseudonym — keyed, versioned HMAC of an operating-system installation identifier the client
  reported (today: Windows MachineGuid). The raw identifier is never stored.
* signal_states — per-signal availability for this observation, e.g.
  {"machine_guid": "observed" | "unavailable" | "unsupported" | "invalid", "gdid": "unsupported"},
  so an absent signal is recorded as absent, never as a value and never as evidence of abuse.

Additive and reversible.

Revision ID: 0050
Revises: 0049
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0050"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("device_observations", sa.Column("os_install_pseudonym", sa.String(64), nullable=True))
    op.add_column("device_observations", sa.Column("signal_states", sa.JSON(), nullable=True))
    op.create_index("ix_device_observations_os_install", "device_observations",
                    ["organization_id", "os_install_pseudonym"])


def downgrade() -> None:
    op.drop_index("ix_device_observations_os_install", table_name="device_observations")
    op.drop_column("device_observations", "signal_states")
    op.drop_column("device_observations", "os_install_pseudonym")
