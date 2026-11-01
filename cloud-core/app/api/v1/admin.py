"""
Platform admin API (Step 14B): read-only views across organizations, for platform administrators only.

Every route depends on `require_platform_admin` (a platform_admins row, read from the database on each
request). These are the only routes that do not filter by the caller's organization; each names what it reads.
Tenant routes are unchanged, so organization isolation everywhere else still holds. Each list is one query
(user counts come from one grouped subquery, never a call per row). There are no writes here yet.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ai_center import AIJob
from app.models.audit_log import AuditLog
from app.models.enums import OrganizationStatus, SyncJobStatus, UserStatus
from app.models.organization import Organization
from app.models.sync_job import SyncJob
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams, apply_sort
from app.schemas.organization import OrganizationRead
from app.schemas.user import UserRead
from app.security.dependencies import require_platform_admin

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


def _admin_user(u: User, organization_name: str) -> AdminUser:
    return AdminUser(**UserRead.model_validate(u).model_dump(), organization_name=organization_name)


@router.get("/users", response_model=Page[AdminUser])
def list_users(p: PaginationParams = Depends(), sort: SortParams = Depends(), q: str | None = Query(default=None, max_length=200),
               status: UserStatus | None = None, _: User = PlatformAdmin, db: Session = Depends(get_db)) -> Page[AdminUser]:
    stmt = select(User, Organization.name).join(Organization, Organization.id == User.organization_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.name.ilike(like), Organization.name.ilike(like)))
    if status is not None:
        stmt = stmt.where(User.status == status)
    total = _count(db, stmt)
    stmt = apply_sort(stmt, User, sort, default_field="created_at")
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).all()
    return Page[AdminUser](items=[_admin_user(u, n) for u, n in rows], total=total, limit=p.limit, offset=p.offset)


@router.get("/users/{user_id}", response_model=AdminUser)
def get_user(user_id: UUID, _: User = PlatformAdmin, db: Session = Depends(get_db)) -> AdminUser:
    row = db.execute(select(User, Organization.name).join(Organization, Organization.id == User.organization_id)
                     .where(User.id == user_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return _admin_user(row[0], row[1])
