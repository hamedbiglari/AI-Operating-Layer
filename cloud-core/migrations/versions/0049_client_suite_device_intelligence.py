"""Official client suite (ADR-137) and Device Intelligence (ADR-138).

* conversation_messages.client_request_id + a partial unique index: a native client that lost the reply to a
  question re-sends it with the same key and receives the stored turn instead of asking twice.
* device_credentials, device_credential_links, device_challenges, device_observations: installation-continuity
  evidence, tenant-scoped like every other table (tests/test_forensic_integrity.py).

Additive and reversible. No existing column changes meaning; existing rows get NULL client_request_id.

Revision ID: 0049
Revises: 0048
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049"
down_revision: Union[str, None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROVENANCES = ("WEB_BROWSER", "WINDOWS_CLIENT", "MACOS_CLIENT", "ANDROID_CLIENT", "IOS_CLIENT",
               "SERVER_OBSERVATION")
KEY_STORAGE = ("hardware", "os_keystore", "browser_non_extractable", "software", "unknown")
REVOKED_REASONS = ("user_revoked", "admin_revoked", "last_account_unlinked", "key_rotated")
OBSERVATION_KINDS = ("registered", "linked", "verified", "verification_failed", "revoked", "unlinked")


def _q(values):
    return ", ".join(f"'{v}'" for v in values)


def _uuid(name, *args, **kw):
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, **kw)


def _ts(name, nullable=True):
    return sa.Column(name, sa.TIMESTAMP(timezone=True), nullable=nullable)


def _stamps():
    return [sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())]


def _org():
    return _uuid("organization_id", sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)


def upgrade() -> None:
    op.add_column("conversation_messages", sa.Column("client_request_id", sa.String(64), nullable=True))
    op.create_index("uq_conversation_messages_client_request", "conversation_messages",
                    ["conversation_id", "client_request_id"], unique=True,
                    postgresql_where=sa.text("client_request_id IS NOT NULL"))

    op.create_table(
        "device_credentials",
        _uuid("id", primary_key=True), _org(),
        _uuid("registered_by_user_id", sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provenance", sa.String(30), nullable=False),
        sa.Column("algorithm", sa.String(10), nullable=False),
        sa.Column("public_key_spki", sa.Text(), nullable=False),
        sa.Column("key_thumbprint", sa.String(64), nullable=False),
        sa.Column("key_storage", sa.String(30), nullable=False),
        sa.Column("app_version", sa.String(40)), sa.Column("os_family", sa.String(40)),
        sa.Column("os_version", sa.String(40)),
        sa.Column("status", sa.String(20), nullable=False),
        _ts("first_seen_at", False), _ts("last_seen_at", False), _ts("last_verified_at"),
        _ts("revoked_at"), sa.Column("revoked_reason", sa.String(30)),
        *_stamps(),
        sa.UniqueConstraint("organization_id", "key_thumbprint", name="uq_device_credentials_org_thumbprint"),
        sa.CheckConstraint(f"provenance IN ({_q(PROVENANCES)})", name="ck_device_credentials_provenance"),
        sa.CheckConstraint(f"key_storage IN ({_q(KEY_STORAGE)})", name="ck_device_credentials_key_storage"),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_device_credentials_status"),
        sa.CheckConstraint("algorithm IN ('ES256')", name="ck_device_credentials_algorithm"),
        sa.CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL AND revoked_reason IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL AND revoked_reason IS NOT NULL "
            f"AND revoked_reason IN ({_q(REVOKED_REASONS)}))",
            name="ck_device_credentials_revoked_credentials_say_why"),
    )
    op.create_index("ix_device_credentials_organization_id", "device_credentials", ["organization_id"])

    op.create_table(
        "device_credential_links",
        _uuid("id", primary_key=True), _org(),
        _uuid("credential_id", sa.ForeignKey("device_credentials.id", ondelete="CASCADE"), nullable=False),
        _uuid("user_id", nullable=False),
        _ts("first_linked_at", False), _ts("last_verified_at"), _ts("unlinked_at"),
        *_stamps(),
        sa.UniqueConstraint("credential_id", "user_id", name="uq_device_credential_links_credential_user"),
        sa.ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                                ondelete="CASCADE", name="fk_device_credential_links_user_org"),
    )
    op.create_index("ix_device_credential_links_organization_id", "device_credential_links", ["organization_id"])
    op.create_index("ix_device_credential_links_credential_id", "device_credential_links", ["credential_id"])
    op.create_index("ix_device_credential_links_user", "device_credential_links", ["organization_id", "user_id"])

    op.create_table(
        "device_challenges",
        _uuid("id", primary_key=True), _org(),
        _uuid("user_id", sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        _uuid("credential_id", sa.ForeignKey("device_credentials.id", ondelete="CASCADE"), nullable=True),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        _ts("expires_at", False), _ts("consumed_at"),
        *_stamps(),
        sa.CheckConstraint("purpose IN ('register', 'verify')", name="ck_device_challenges_purpose"),
        sa.CheckConstraint("purpose = 'register' OR credential_id IS NOT NULL",
                           name="ck_device_challenges_verify_names_a_credential"),
    )
    op.create_index("ix_device_challenges_organization_id", "device_challenges", ["organization_id"])
    op.create_index("ix_device_challenges_expires_at", "device_challenges", ["expires_at"])

    op.create_table(
        "device_observations",
        _uuid("id", primary_key=True), _org(),
        _uuid("credential_id", sa.ForeignKey("device_credentials.id", ondelete="CASCADE"), nullable=True),
        _uuid("user_id", sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provenance", sa.String(30), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(40)),
        sa.Column("network_pseudonym", sa.String(64)),
        sa.Column("network_prefix_pseudonym", sa.String(64)),
        sa.Column("pseudonym_key_version", sa.Integer()),
        sa.Column("app_version", sa.String(40)),
        *_stamps(),
        sa.CheckConstraint(f"provenance IN ({_q(PROVENANCES)})", name="ck_device_observations_provenance"),
        sa.CheckConstraint(f"kind IN ({_q(OBSERVATION_KINDS)})", name="ck_device_observations_kind"),
    )
    op.create_index("ix_device_observations_organization_id", "device_observations", ["organization_id"])
    op.create_index("ix_device_observations_credential", "device_observations", ["credential_id", "created_at"])
    op.create_index("ix_device_observations_network", "device_observations",
                    ["organization_id", "network_prefix_pseudonym"])
    op.create_index("ix_device_observations_created_at", "device_observations", ["created_at"])


def downgrade() -> None:
    op.drop_table("device_observations")
    op.drop_table("device_challenges")
    op.drop_table("device_credential_links")
    op.drop_table("device_credentials")
    op.drop_index("uq_conversation_messages_client_request", table_name="conversation_messages")
    op.drop_column("conversation_messages", "client_request_id")
