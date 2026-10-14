"""
Installation & credential lifecycle (ADR-036).

Managed by HUMAN users (KNOWLEDGE_EDITOR_ROLES) through the normal
tenant-scoped API — an installation cannot create or escalate itself.
Machine credentials authenticate; they do not administer.

The plaintext secret is returned exactly once, from `issue_credential`
and `rotate_credential`, and is never stored, logged, or recoverable.
Audit entries record key_id (public) and never the secret.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import AdapterScope, CredentialStatus, InstallationStatus
from app.models.installation import Installation, InstallationCredential
from app.security.machine_identity import generate_credential, hash_secret
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.site_service import get_site_or_404


def list_installations(
    db: Session, *, organization_id: UUID, adapter_type=None, limit: int, offset: int, sort: SortParams | None = None
) -> tuple[list[Installation], int]:
    base = select(Installation).where(Installation.organization_id == organization_id)
    if adapter_type:
        base = base.where(Installation.adapter_type == adapter_type)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(apply_sort(base, Installation, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_installation_or_404(db: Session, *, installation_id: UUID, organization_id: UUID) -> Installation:
    return get_tenant_scoped_or_404(
        db, Installation, installation_id, organization_id=organization_id,
        not_found_message="Installation not found",
    )


def create_installation(
    db: Session, *, organization_id: UUID, name: str, adapter_type, site_id: UUID | None,
    external_url: str | None, actor_user_id: UUID,
) -> Installation:
    if site_id is not None:
        get_site_or_404(db, site_id=site_id, organization_id=organization_id)

    installation = Installation(
        organization_id=organization_id, name=name, adapter_type=adapter_type,
        site_id=site_id, external_url=external_url, status=InstallationStatus.ACTIVE,
    )
    db.add(installation)
    db.flush()
    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="installation.created", resource_type="installation", resource_id=installation.id,
        new_value={"name": name, "adapter_type": adapter_type.value},
    )
    db.commit()
    db.refresh(installation)
    return installation


def set_installation_status(
    db: Session, *, installation: Installation, status: InstallationStatus, actor_user_id: UUID
) -> Installation:
    """REVOKED is terminal — an installation cannot be brought back,
    because 'revoked' must mean something permanent to be worth
    saying. Suspension is the reversible option."""
    if installation.status == InstallationStatus.REVOKED:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A revoked installation cannot be reactivated. Create a new installation.",
        )
    old = installation.status
    installation.status = status
    db.flush()
    record_audit_log(
        db, organization_id=installation.organization_id, user_id=actor_user_id,
        action="installation.status_changed", resource_type="installation", resource_id=installation.id,
        old_value={"status": old.value}, new_value={"status": status.value},
    )
    db.commit()
    db.refresh(installation)
    return installation


def issue_credential(
    db: Session, *, installation: Installation, scopes: list[AdapterScope],
    expires_at: datetime | None, actor_user_id: UUID, rotated_from: InstallationCredential | None = None,
) -> tuple[InstallationCredential, str]:
    """Returns (credential, plaintext_token). The token is the ONLY
    time the secret exists outside the caller's hands."""
    key_id, secret, token = generate_credential()
    credential = InstallationCredential(
        organization_id=installation.organization_id,
        installation_id=installation.id,
        key_id=key_id,
        secret_hash=hash_secret(secret),
        scopes=[s.value for s in scopes],
        status=CredentialStatus.ACTIVE,
        expires_at=expires_at,
        rotated_from_id=rotated_from.id if rotated_from else None,
    )
    db.add(credential)
    db.flush()
    record_audit_log(
        db, organization_id=installation.organization_id, user_id=actor_user_id,
        action="installation_credential.issued", resource_type="installation_credential",
        resource_id=credential.id,
        # key_id is public; the secret is never logged.
        new_value={"key_id": key_id, "scopes": [s.value for s in scopes]},
    )
    db.commit()
    db.refresh(credential)
    return credential, token


def rotate_credential(
    db: Session, *, credential: InstallationCredential, actor_user_id: UUID
) -> tuple[InstallationCredential, str]:
    """Issues a replacement and retires the old one. The old credential
    is marked ROTATED rather than deleted so audit entries referencing
    it still resolve."""
    if credential.status != CredentialStatus.ACTIVE:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Only an active credential can be rotated (this one is '{credential.status.value}').",
        )
    installation = db.get(Installation, credential.installation_id)
    new_credential, token = issue_credential(
        db, installation=installation,
        scopes=list(credential.granted_scopes),
        expires_at=credential.expires_at,
        actor_user_id=actor_user_id,
        rotated_from=credential,
    )
    credential.status = CredentialStatus.ROTATED
    credential.revoked_at = datetime.now(timezone.utc)
    db.flush()
    record_audit_log(
        db, organization_id=credential.organization_id, user_id=actor_user_id,
        action="installation_credential.rotated", resource_type="installation_credential",
        resource_id=credential.id, new_value={"replaced_by_key_id": new_credential.key_id},
    )
    db.commit()
    db.refresh(new_credential)
    return new_credential, token


def revoke_credential(
    db: Session, *, credential: InstallationCredential, actor_user_id: UUID
) -> InstallationCredential:
    credential.status = CredentialStatus.REVOKED
    credential.revoked_at = datetime.now(timezone.utc)
    db.flush()
    record_audit_log(
        db, organization_id=credential.organization_id, user_id=actor_user_id,
        action="installation_credential.revoked", resource_type="installation_credential",
        resource_id=credential.id, new_value={"key_id": credential.key_id},
    )
    db.commit()
    db.refresh(credential)
    return credential


def get_credential_or_404(db: Session, *, credential_id: UUID, organization_id: UUID) -> InstallationCredential:
    return get_tenant_scoped_or_404(
        db, InstallationCredential, credential_id, organization_id=organization_id,
        not_found_message="Credential not found",
    )


def list_credentials(
    db: Session, *, installation_id: UUID, organization_id: UUID, limit: int, offset: int, sort: SortParams | None = None
) -> tuple[list[InstallationCredential], int]:
    get_installation_or_404(db, installation_id=installation_id, organization_id=organization_id)
    base = select(InstallationCredential).where(
        InstallationCredential.installation_id == installation_id,
        InstallationCredential.organization_id == organization_id,
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        apply_sort(base, InstallationCredential, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)
    ).scalars().all()
    return list(rows), total
