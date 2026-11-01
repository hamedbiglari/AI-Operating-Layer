"""
User endpoints — all scoped to the caller's own organization.

Creating/updating users requires OWNER or ADMIN role. Every lookup by
ID goes through `user_service.get_user_or_404`, which enforces tenant
isolation (404 for cross-tenant IDs — see app.security.tenant).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ADMIN_ROLES, UserRole, UserStatus
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.core.config import settings
from app.schemas.user import EmailChangeRequestIn, EmailChangeVerifyIn, UserCreate, UserRead, UserSelfUpdate, UserUpdate
from app.security.dependencies import get_current_user, require_roles
from app.services import email_change_service, user_service

router = APIRouter(prefix="/users", tags=["users"])

_OWNER_ONLY = HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only an owner can grant the owner role or change an owner's account.")


def _active_owner_count(db: Session, organization_id: UUID) -> int:
    return db.execute(select(func.count()).select_from(User).where(
        User.organization_id == organization_id, User.role == UserRole.OWNER,
        User.status == UserStatus.ACTIVE)).scalar_one()


@router.get("", response_model=Page[UserRead])
def list_users(
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[UserRead]:
    items, total = user_service.list_users(
        db,
        organization_id=current_user.organization_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> User:
    # An admin may add teammates but not owners: otherwise an admin could create an owner account and take the
    # organization over (security audit SEC-14).
    if payload.role == UserRole.OWNER and current_user.role != UserRole.OWNER:
        raise _OWNER_ONLY
    try:
        return user_service.create_user(
            db,
            organization_id=current_user.organization_id,
            email=payload.email,
            name=payload.name,
            password=payload.password,
            role=payload.role,
            actor_user_id=current_user.id,
        )
    except user_service.EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        ) from None


# Declared before /{user_id}: "me" is not a UUID, so the parameterised route would answer 422 first.
@router.patch("/me", response_model=UserRead)
def update_me(
    payload: UserSelfUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Any signed-in user may change their own name (V5-settings-self-profile); nothing else. An `email` in the body
    is refused (422): the sign-in address changes only through the confirmed flow below."""
    if payload.name is not None and not payload.name.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name cannot be blank")
    return user_service.update_self(db, user=current_user, name=payload.name)


def _retry(seconds: int | None) -> dict:
    return {"Retry-After": str(seconds)} if seconds else {}


@router.post("/me/email-change-request", status_code=status.HTTP_202_ACCEPTED)
def request_email_change(
    payload: EmailChangeRequestIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Step 1 of a sign-in email change (V5-self-email-verification): a 6-digit code goes to the NEW address.
    Nothing changes until step 2 (email-change-verify) receives that code."""
    out = email_change_service.request(db, user=current_user, new_email=str(payload.new_email))
    if out.kind == "sent":
        return {"sent_to": str(payload.new_email).strip().lower(), "expires_in_seconds": settings.LOGIN_CODE_TTL_SECONDS,
                "resend_after_seconds": out.retry_after_seconds}
    if out.kind == "same":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That is already your sign-in email")
    if out.kind == "taken":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    if out.kind in ("cooldown", "too_many_requests"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers=_retry(out.retry_after_seconds),
                            detail="A code was sent recently. Try again later.")
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Email delivery is not configured, so no code can be sent.")


@router.post("/me/email-change-verify", response_model=UserRead)
def verify_email_change(
    payload: EmailChangeVerifyIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Step 2: the code from the new address. On success the sign-in email is the new one, the change is
    audit-logged and the old address is told."""
    out = email_change_service.verify(db, user=current_user, code=payload.code)
    if out.kind == "ok":
        return out.user
    if out.kind == "none":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No email change is waiting for a code. Ask for a new code.")
    if out.kind == "taken":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")
    if out.kind == "voided":
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many wrong codes. Ask for a new code.")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That code is not correct.")


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    return user_service.get_user_or_404(
        db, user_id=user_id, organization_id=current_user.organization_id
    )


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> User:
    target = user_service.get_user_or_404(
        db, user_id=user_id, organization_id=current_user.organization_id
    )
    # Owner-level changes need an owner (security audit SEC-14): an admin must not promote anyone (including
    # themselves) to owner, nor demote, rename or block an owner.
    touches_owner = target.role == UserRole.OWNER or payload.role == UserRole.OWNER
    changes_something = any(v is not None for v in (payload.name, payload.role, payload.status))
    if touches_owner and changes_something and current_user.role != UserRole.OWNER:
        raise _OWNER_ONLY
    # The organization always keeps at least one active owner.
    loses_owner = target.role == UserRole.OWNER and target.status == UserStatus.ACTIVE and (
        (payload.role is not None and payload.role != UserRole.OWNER)
        or (payload.status is not None and payload.status != UserStatus.ACTIVE))
    if loses_owner and _active_owner_count(db, current_user.organization_id) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This is the organization's only active owner. Make someone else owner first.")
    return user_service.update_user(
        db,
        user=target,
        name=payload.name,
        role=payload.role,
        status=payload.status,
        actor_user_id=current_user.id,
    )
