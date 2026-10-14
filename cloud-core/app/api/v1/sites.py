"""
Site endpoints — all scoped to the caller's own organization.

DELETE is intentionally not destructive: `DELETE /sites/{id}` archives
the site (status=ARCHIVED) rather than removing the row, per the
soft-delete/archive principle in master spec section 8.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ADMIN_ROLES
from app.models.site import Site
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.site import SiteCreate, SiteRead, SiteUpdate
from app.security.dependencies import get_current_user, require_roles
from app.services import site_service

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=Page[SiteRead])
def list_sites(
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[SiteRead]:
    items, total = site_service.list_sites(
        db,
        organization_id=current_user.organization_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> Site:
    try:
        return site_service.create_site(
            db,
            organization_id=current_user.organization_id,
            name=payload.name,
            domain=payload.domain,
            platform=payload.platform,
            wordpress_url=payload.wordpress_url,
            woo_enabled=payload.woo_enabled,
            actor_user_id=current_user.id,
        )
    except site_service.DomainAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This domain is already registered for your organization",
        ) from None


@router.get("/{site_id}", response_model=SiteRead)
def get_site(
    site_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Site:
    return site_service.get_site_or_404(
        db, site_id=site_id, organization_id=current_user.organization_id
    )


@router.patch("/{site_id}", response_model=SiteRead)
def update_site(
    site_id: UUID,
    payload: SiteUpdate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> Site:
    target = site_service.get_site_or_404(
        db, site_id=site_id, organization_id=current_user.organization_id
    )
    return site_service.update_site(
        db,
        site=target,
        name=payload.name,
        wordpress_url=payload.wordpress_url,
        woo_enabled=payload.woo_enabled,
        status=payload.status,
        actor_user_id=current_user.id,
    )


@router.delete("/{site_id}", response_model=SiteRead)
def archive_site(
    site_id: UUID,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> Site:
    target = site_service.get_site_or_404(
        db, site_id=site_id, organization_id=current_user.organization_id
    )
    return site_service.archive_site(db, site=target, actor_user_id=current_user.id)
