"""Site management service — every query is scoped to organization_id."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import SitePlatform, SiteStatus
from app.models.site import Site
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log


class DomainAlreadyRegisteredError(Exception):
    pass


def list_sites(
    db: Session, *, organization_id: UUID, limit: int, offset: int, sort: SortParams | None = None
) -> tuple[list[Site], int]:
    base = select(Site).where(Site.organization_id == organization_id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, Site, sort, "created_at", SortDirection.ASC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_site_or_404(db: Session, *, site_id: UUID, organization_id: UUID) -> Site:
    return get_tenant_scoped_or_404(
        db, Site, site_id, organization_id=organization_id, not_found_message="Site not found"
    )


def create_site(
    db: Session,
    *,
    organization_id: UUID,
    name: str,
    domain: str,
    platform: SitePlatform,
    wordpress_url: str | None,
    woo_enabled: bool,
    actor_user_id: UUID,
) -> Site:
    site = Site(
        organization_id=organization_id,
        name=name,
        domain=domain,
        platform=platform,
        wordpress_url=wordpress_url,
        woo_enabled=woo_enabled,
        status=SiteStatus.ACTIVE,
    )
    db.add(site)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DomainAlreadyRegisteredError(domain) from exc

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="site.created",
        resource_type="site",
        resource_id=site.id,
        new_value={"name": site.name, "domain": site.domain},
    )
    db.commit()
    db.refresh(site)
    return site


def update_site(
    db: Session,
    *,
    site: Site,
    name: str | None,
    wordpress_url: str | None,
    woo_enabled: bool | None,
    status: SiteStatus | None,
    actor_user_id: UUID,
) -> Site:
    old_value = {"name": site.name, "status": site.status.value}

    if name is not None:
        site.name = name
    if wordpress_url is not None:
        site.wordpress_url = wordpress_url
    if woo_enabled is not None:
        site.woo_enabled = woo_enabled
    if status is not None:
        site.status = status

    db.flush()
    record_audit_log(
        db,
        organization_id=site.organization_id,
        user_id=actor_user_id,
        action="site.updated",
        resource_type="site",
        resource_id=site.id,
        old_value=old_value,
        new_value={"name": site.name, "status": site.status.value},
    )
    db.commit()
    db.refresh(site)
    return site


def archive_site(db: Session, *, site: Site, actor_user_id: UUID) -> Site:
    return update_site(
        db,
        site=site,
        name=None,
        wordpress_url=None,
        woo_enabled=None,
        status=SiteStatus.ARCHIVED,
        actor_user_id=actor_user_id,
    )
