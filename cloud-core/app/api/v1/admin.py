"""
Platform admin API (Step 14B): read-only views across organizations, for platform administrators only.

Every route depends on `require_platform_admin` (a platform_admins row, read from the database on each
request). These are the only routes that do not filter by the caller's organization; each names what it reads.
Tenant routes are unchanged, so organization isolation everywhere else still holds. Each list is one query
(user counts come from one grouped subquery, never a call per row). The only writes grant and revoke the platform-admin role itself, each audit-logged.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ai_center import AIJob
from app.models.audit_log import AuditLog
from app.models.enums import OrganizationStatus, SyncJobStatus, UserStatus
from app.models.organization import Organization
from app.models.platform_admin import PlatformAdmin as PlatformAdminGrant
from app.models.sync_job import SyncJob
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams, apply_sort
from app.schemas.organization import OrganizationRead
from app.schemas.user import UserRead
from app.security.dependencies import is_platform_admin, require_platform_admin
from app.services.audit import record_audit_log

router = APIRouter(prefix="/admin", tags=["platform-admin"])
PlatformAdmin = Depends(require_platform_admin)


class OverviewCount(BaseModel):
    total: int
    active: int


class AdminOverview(BaseModel):
    organizations: OverviewCount
    # users.active = distinct users with any audit-log entry in the last 30 days (there is no last-login column).
    users: OverviewCount
    # Background sync jobs that failed or were dead-lettered, and AI jobs that finished with failures, in 24 h.
    failed_sync_jobs_24h: int
    failed_ai_jobs_24h: int
    as_of: datetime


class AdminOrganization(OrganizationRead):
    user_count: int


class AdminUser(UserRead):
    organization_name: str
    is_platform_admin: bool = False


class GrantIn(BaseModel):
    """Who to grant: exactly one of user_id or email."""
    user_id: UUID | None = None
    email: EmailStr | None = None

    @model_validator(mode="after")
    def _one(self) -> "GrantIn":
        if (self.user_id is None) == (self.email is None):
            raise ValueError("Give exactly one of user_id or email.")
        return self


def _count(db: Session, stmt) -> int:
    return db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()


@router.get("/overview", response_model=AdminOverview)
def overview(_: User = PlatformAdmin, db: Session = Depends(get_db)) -> AdminOverview:
    now = datetime.now(timezone.utc)
    day, month = now - timedelta(hours=24), now - timedelta(days=30)
    return AdminOverview(
        organizations=OverviewCount(
            total=_count(db, select(Organization.id)),
            active=_count(db, select(Organization.id).where(Organization.status == OrganizationStatus.ACTIVE))),
        users=OverviewCount(
            total=_count(db, select(User.id)),
            active=_count(db, select(AuditLog.user_id).where(AuditLog.user_id.is_not(None),
                                                            AuditLog.created_at >= month).distinct())),
        failed_sync_jobs_24h=_count(db, select(SyncJob.id).where(
            SyncJob.status.in_((SyncJobStatus.FAILED, SyncJobStatus.DEAD_LETTER)), SyncJob.updated_at >= day)),
        failed_ai_jobs_24h=_count(db, select(AIJob.id).where(
            AIJob.status == "completed_with_failures", AIJob.updated_at >= day)),
        as_of=now,
    )


@router.get("/organizations", response_model=Page[AdminOrganization])
def list_organizations(p: PaginationParams = Depends(), sort: SortParams = Depends(), q: str | None = Query(default=None, max_length=200),
                       _: User = PlatformAdmin, db: Session = Depends(get_db)) -> Page[AdminOrganization]:
    users = select(User.organization_id, func.count(User.id).label("n")).group_by(User.organization_id).subquery()
    stmt = select(Organization, func.coalesce(users.c.n, 0)).outerjoin(users, users.c.organization_id == Organization.id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Organization.name.ilike(like), Organization.slug.ilike(like)))
    total = _count(db, stmt)
    stmt = apply_sort(stmt, Organization, sort, default_field="created_at")
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).all()
    items = [AdminOrganization(**OrganizationRead.model_validate(o).model_dump(), user_count=n) for o, n in rows]
    return Page[AdminOrganization](items=items, total=total, limit=p.limit, offset=p.offset)


def _admin_user(u: User, organization_name: str, grant_id: UUID | None = None) -> AdminUser:
    return AdminUser(**UserRead.model_validate(u).model_dump(), organization_name=organization_name,
                     is_platform_admin=grant_id is not None)


def _users_stmt():
    # One query: each user with its organization's name and whether it holds a platform-admin grant.
    return (select(User, Organization.name, PlatformAdminGrant.id)
            .join(Organization, Organization.id == User.organization_id)
            .outerjoin(PlatformAdminGrant, PlatformAdminGrant.user_id == User.id))


@router.get("/users", response_model=Page[AdminUser])
def list_users(p: PaginationParams = Depends(), sort: SortParams = Depends(), q: str | None = Query(default=None, max_length=200),
               status: UserStatus | None = None, _: User = PlatformAdmin, db: Session = Depends(get_db)) -> Page[AdminUser]:
    stmt = _users_stmt()
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.name.ilike(like), Organization.name.ilike(like)))
    if status is not None:
        stmt = stmt.where(User.status == status)
    total = _count(db, stmt)
    stmt = apply_sort(stmt, User, sort, default_field="created_at")
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).all()
    return Page[AdminUser](items=[_admin_user(u, n, g) for u, n, g in rows], total=total, limit=p.limit, offset=p.offset)


@router.get("/users/{user_id}", response_model=AdminUser)
def get_user(user_id: UUID, _: User = PlatformAdmin, db: Session = Depends(get_db)) -> AdminUser:
    row = db.execute(_users_stmt().where(User.id == user_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return _admin_user(row[0], row[1], row[2])


@router.post("/grant", response_model=AdminUser)
def grant(body: GrantIn, actor: User = PlatformAdmin, db: Session = Depends(get_db)) -> AdminUser:
    """Make a user a platform admin (V5-admin-grant). Idempotent: granting an admin again changes nothing."""
    where = User.id == body.user_id if body.user_id else func.lower(User.email) == str(body.email).lower()
    target = db.execute(select(User).where(where)).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if not is_platform_admin(db, target.id):
        db.add(PlatformAdminGrant(user_id=target.id, organization_id=target.organization_id))
        record_audit_log(db, organization_id=target.organization_id, user_id=actor.id, action="platform_admin.granted",
                         resource_type="user", resource_id=target.id, new_value={"granted_by": str(actor.id)})
        db.commit()
    return get_user(target.id, actor, db)


@router.delete("/grant/{user_id}", status_code=204)
def revoke(user_id: UUID, actor: User = PlatformAdmin, db: Session = Depends(get_db)) -> Response:
    """Remove a platform-admin grant. A platform admin cannot revoke their own, so nobody locks everyone out."""
    if user_id == actor.id:
        raise HTTPException(status_code=409, detail="You cannot revoke your own platform-admin grant.")
    row = db.execute(select(PlatformAdminGrant).where(PlatformAdminGrant.user_id == user_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="This user is not a platform admin.")
    record_audit_log(db, organization_id=row.organization_id, user_id=actor.id, action="platform_admin.revoked",
                     resource_type="user", resource_id=user_id, old_value={"granted_at": row.created_at.isoformat()})
    db.delete(row)
    db.commit()
    return Response(status_code=204)
