"""
Authentication service.

Owns the two bootstrap/auth flows:
- register_organization: creates a brand-new tenant (Organization + its
  first OWNER user) atomically.
- authenticate: verifies email/password and returns the User, or None.

Kept out of the API layer so it's independently testable and reusable
(e.g. by a future CLI/admin tool) without going through HTTP.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import OrganizationStatus, UserRole, UserStatus
from app.models.organization import Organization
from app.models.user import User
from app.security.passwords import hash_password, verify_password
from app.services.audit import record_audit_log
from app.services.slugs import slugify


class EmailAlreadyRegisteredError(Exception):
    pass


class OrganizationSlugConflictError(Exception):
    pass


def register_organization(
    db: Session,
    *,
    organization_name: str,
    owner_email: str,
    owner_name: str,
    owner_password: str | None,
) -> tuple[Organization, User]:
    """owner_password=None creates a passwordless owner who signs in with an emailed code (ADR-106)."""
    base_slug = slugify(organization_name)
    slug = base_slug
    suffix = 1
    while db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none():
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    organization = Organization(
        name=organization_name,
        slug=slug,
        status=OrganizationStatus.ACTIVE,
    )
    db.add(organization)
    db.flush()  # assigns organization.id without committing yet

    owner = User(
        organization_id=organization.id,
        email=owner_email.lower(),
        name=owner_name,
        role=UserRole.OWNER,
        status=UserStatus.ACTIVE,
        password_hash=hash_password(owner_password) if owner_password else None,
    )
    db.add(owner)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyRegisteredError(owner_email) from exc

    record_audit_log(
        db,
        organization_id=organization.id,
        user_id=owner.id,
        action="organization.registered",
        resource_type="organization",
        resource_id=organization.id,
        new_value={"name": organization.name, "slug": organization.slug},
    )
    record_audit_log(
        db,
        organization_id=organization.id,
        user_id=owner.id,
        action="user.created",
        resource_type="user",
        resource_id=owner.id,
        new_value={"email": owner.email, "role": owner.role.value},
    )

    db.commit()
    db.refresh(organization)
    db.refresh(owner)
    return organization, owner


_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("timing-equaliser-not-a-password")
    return _DUMMY_HASH


def authenticate(db: Session, *, email: str, password: str) -> User | None:
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user is None or not user.password_hash:
        # Unknown address, or a passwordless owner (ADR-106) whom only the emailed code can sign in. Spend the
        # same bcrypt work as a real check so response time does not reveal which addresses exist (SEC-02).
        verify_password(password, _dummy_hash())
        return None
    if not verify_password(password, user.password_hash):
        return None
    if user.status != UserStatus.ACTIVE:
        return None
    return user
