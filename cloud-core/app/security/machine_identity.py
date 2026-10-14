"""
Machine-client authentication (ADR-036).

The whole security property of this module in one sentence:
**the tenant is derived from the credential, never read from the
request.**

Flow:

    Authorization: Bearer aiol_<key_id>_<secret>
        -> look up credential by key_id (non-secret, indexed)
        -> constant-time verify secret against stored bcrypt hash
        -> credential ACTIVE and unexpired?
        -> installation ACTIVE?
        -> organization ACTIVE?
        -> MachineIdentity(organization_id=<from installation>, ...)

There is no parameter anywhere in this module that lets a caller
influence which organization it resolves to. An adapter that sends
`{"organization_id": "<someone else's>"}` in a body is simply ignored -
the field does not participate in authentication.

Reuses `app/security/passwords.py` (bcrypt) rather than introducing a
second hashing scheme, per the "do not create a parallel
authentication system" constraint. The secret is never stored and
never recoverable; it is returned exactly once at issue time.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import (
    AdapterScope,
    CredentialStatus,
    InstallationStatus,
    OrganizationStatus,
)
from app.models.installation import Installation, InstallationCredential
from app.models.organization import Organization
from app.security.passwords import hash_password, verify_password

_PREFIX = "aiol"
_KEY_ID_BYTES = 12
_SECRET_BYTES = 32

# One generic message for every authentication failure. Distinguishing
# "no such key" from "wrong secret" from "revoked" would let an
# attacker enumerate valid key_ids; operators get the real reason from
# the audit log instead.
_AUTH_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or inactive installation credential",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True)
class MachineIdentity:
    """The authenticated result. `organization_id` here is the ONLY
    tenant a request may act in."""

    installation_id: UUID
    organization_id: UUID
    site_id: UUID | None
    credential_id: UUID
    adapter_type: str
    scopes: frozenset[AdapterScope]

    def has_scope(self, scope: AdapterScope) -> bool:
        return scope in self.scopes


def generate_credential() -> tuple[str, str, str]:
    """Returns (key_id, plaintext_secret, full_token).

    `token_urlsafe` is used rather than `uuid4` because these are
    secrets, and uuid4 is not specified as cryptographically strong for
    that purpose."""
    key_id = secrets.token_urlsafe(_KEY_ID_BYTES).replace("-", "").replace("_", "")[:22]
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    return key_id, secret, f"{_PREFIX}_{key_id}_{secret}"


def hash_secret(secret: str) -> str:
    return hash_password(secret)


def _parse_token(raw: str) -> tuple[str, str] | None:
    if not raw.startswith(f"{_PREFIX}_"):
        return None
    parts = raw.split("_", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if not header or not header.lower().startswith("bearer "):
        return None
    return header[7:].strip() or None


def resolve_machine_identity(request: Request, db: Session) -> MachineIdentity:
    """Every rejection path raises the same generic 401 - see
    _AUTH_EXCEPTION."""
    raw = _extract_bearer(request)
    if raw is None:
        raise _AUTH_EXCEPTION

    parsed = _parse_token(raw)
    if parsed is None:
        # Not a machine token at all (probably a user JWT hitting an
        # adapter route). Still a 401, not a 400 - the route requires
        # machine identity and did not get one.
        raise _AUTH_EXCEPTION
    key_id, secret = parsed

    credential = db.execute(
        select(InstallationCredential).where(InstallationCredential.key_id == key_id)
    ).scalar_one_or_none()
    if credential is None:
        # Still run a hash comparison against a dummy value so that a
        # non-existent key_id costs the same time as a wrong secret -
        # otherwise response timing reveals which key_ids exist.
        verify_password(secret, hash_password("timing-equalisation"))
        raise _AUTH_EXCEPTION

    if not verify_password(secret, credential.secret_hash):
        raise _AUTH_EXCEPTION
    if credential.status != CredentialStatus.ACTIVE:
        raise _AUTH_EXCEPTION
    if credential.expires_at is not None and credential.expires_at <= datetime.now(timezone.utc):
        raise _AUTH_EXCEPTION

    installation = db.get(Installation, credential.installation_id)
    if installation is None or installation.status != InstallationStatus.ACTIVE:
        raise _AUTH_EXCEPTION

    organization = db.get(Organization, installation.organization_id)
    if organization is None or organization.status != OrganizationStatus.ACTIVE:
        raise _AUTH_EXCEPTION

    now = datetime.now(timezone.utc)
    credential.last_used_at = now
    installation.last_seen_at = now
    db.commit()

    return MachineIdentity(
        installation_id=installation.id,
        organization_id=installation.organization_id,  # derived, never client-supplied
        site_id=installation.site_id,
        credential_id=credential.id,
        adapter_type=installation.adapter_type.value,
        scopes=frozenset(credential.granted_scopes),
    )


def get_machine_identity(request: Request, db: Session = Depends(get_db)) -> MachineIdentity:
    return resolve_machine_identity(request, db)


def require_scope(*required: AdapterScope):
    """Authorization layered on top of authentication, mirroring how
    `require_roles` layers on `get_current_user` for human users."""

    def _dependency(identity: MachineIdentity = Depends(get_machine_identity)) -> MachineIdentity:
        if not any(identity.has_scope(s) for s in required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Credential lacks required scope: {', '.join(s.value for s in required)}",
            )
        return identity

    return _dependency
