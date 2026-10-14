"""
User management service — every query is scoped to organization_id.

This is where the Phase 0 review's "golden test" is enforced for the
Users resource: `get_user_or_404` uses `get_tenant_scoped_or_404`, so a
user ID from another organization returns 404 no matter what.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.security.passwords import hash_password
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log


class EmailAlreadyRegisteredError(Exception):
    pass


def list_users(
    db: Session, *, organization_id: UUID, limit: int, offset: int, sort: SortParams | None = None
) -> tuple[list[User], int]:
    base = select(User).where(User.organization_id == organization_id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, User, sort, "created_at", SortDirection.ASC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_user_or_404(db: Session, *, user_id: UUID, organization_id: UUID) -> User:
    return get_tenant_scoped_or_404(
        db, User, user_id, organization_id=organization_id, not_found_message="User not found"
    )


def create_user(
    db: Session,
    *,
    organization_id: UUID,
    email: str,
    name: str,
    password: str,
    role: UserRole,
    actor_user_id: UUID,
) -> User:
    user = User(
        organization_id=organization_id,
        email=email.lower(),
        name=name,
        role=role,
        status=UserStatus.ACTIVE,
        password_hash=hash_password(password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyRegisteredError(email) from exc

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="user.created",
        resource_type="user",
        resource_id=user.id,
        new_value={"email": user.email, "role": user.role.value},
    )
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    *,
    user: User,
    name: str | None,
    role: UserRole | None,
    status: UserStatus | None,
    actor_user_id: UUID,
) -> User:
    old_value = {"name": user.name, "role": user.role.value, "status": user.status.value}

    if name is not None:
        user.name = name
    if role is not None:
        user.role = role
    if status is not None:
        user.status = status

    db.flush()
    record_audit_log(
        db,
        organization_id=user.organization_id,
        user_id=actor_user_id,
        action="user.updated",
        resource_type="user",
        resource_id=user.id,
        old_value=old_value,
        new_value={"name": user.name, "role": user.role.value, "status": user.status.value},
    )
    db.commit()
    db.refresh(user)
    return user
