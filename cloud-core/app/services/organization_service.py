"""Organization service — Phase 1 only supports reading/updating "my own"
organization; there is no cross-tenant listing endpoint (no superadmin
scope in MVP)."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.services.audit import record_audit_log


def update_organization(
    db: Session, *, organization: Organization, name: str | None, actor_user_id: UUID
) -> Organization:
    old_value = {"name": organization.name}

    if name is not None:
        organization.name = name

    db.flush()
    record_audit_log(
        db,
        organization_id=organization.id,
        user_id=actor_user_id,
        action="organization.updated",
        resource_type="organization",
        resource_id=organization.id,
        old_value=old_value,
        new_value={"name": organization.name},
    )
    db.commit()
    db.refresh(organization)
    return organization
