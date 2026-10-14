"""organizations, users, sites, audit_logs

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-02 00:00:00

Phase 1: tenant root (organizations), users, sites, and the audit log
table. All UUID PKs, TIMESTAMPTZ timestamps, organization_id foreign
keys on every tenant-owned table (per master spec section 8).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # create_type=False on every column definition below: the enum TYPEs
    # are created explicitly right here (once), so SQLAlchemy must not
    # also try to auto-create them a second time as a side effect of
    # create_table — that raised psycopg.errors.DuplicateObject when
    # this migration was actually run against Postgres.
    organization_status = postgresql.ENUM(
        "active", "suspended", "pending", "cancelled",
        name="organization_status", create_type=False,
    )
    user_role = postgresql.ENUM(
        "owner", "admin", "researcher", "editor", "analyst", "viewer",
        name="user_role", create_type=False,
    )
    user_status = postgresql.ENUM(
        "active", "invited", "suspended", "deactivated",
        name="user_status", create_type=False,
    )
    site_platform = postgresql.ENUM(
        "wordpress", "custom", "other",
        name="site_platform", create_type=False,
    )
    site_status = postgresql.ENUM(
        "active", "inactive", "archived",
        name="site_status", create_type=False,
    )

    bind = op.get_bind()
    organization_status.create(bind, checkfirst=True)
    user_role.create(bind, checkfirst=True)
    user_status.create(bind, checkfirst=True)
    site_platform.create(bind, checkfirst=True)
    site_status.create(bind, checkfirst=True)

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column(
            "status", organization_status, nullable=False, server_default="active"
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("status", user_status, nullable=False, server_default="active"),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_users_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.create_table(
        "sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("platform", site_platform, nullable=False),
        sa.Column("wordpress_url", sa.String(length=500), nullable=True),
        sa.Column("woo_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", site_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_sites_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sites"),
        sa.UniqueConstraint(
            "organization_id", "domain", name="uq_sites_organization_domain"
        ),
    )
    op.create_index("ix_sites_organization_id", "sites", ["organization_id"], unique=False)
    op.create_index("ix_sites_domain", "sites", ["domain"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_value", postgresql.JSONB(), nullable=True),
        sa.Column("new_value", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_audit_logs_organization_id_organizations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_audit_logs_user_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"], unique=False)
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_organization_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_sites_domain", table_name="sites")
    op.drop_index("ix_sites_organization_id", table_name="sites")
    op.drop_table("sites")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_table("organizations")

    bind = op.get_bind()
    postgresql.ENUM(name="site_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="site_platform").drop(bind, checkfirst=True)
    postgresql.ENUM(name="user_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="user_role").drop(bind, checkfirst=True)
    postgresql.ENUM(name="organization_status").drop(bind, checkfirst=True)
