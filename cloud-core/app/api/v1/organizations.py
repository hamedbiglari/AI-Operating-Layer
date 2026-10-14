"""
Organization endpoints.

Phase 1 scope is deliberately narrow: an authenticated user can only
read/update THEIR OWN organization. There is no `/organizations/{id}`
listing across tenants — that would be a superadmin capability out of
MVP scope (master spec section 58: "no unnecessary enterprise
abstractions").
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ADMIN_ROLES
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import OrganizationRead, OrganizationUpdate
from app.security.dependencies import get_current_user, require_roles
from app.services.organization_service import update_organization

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/me", response_model=OrganizationRead)
def read_my_organization(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Organization:
    return db.get(Organization, current_user.organization_id)


@router.patch("/me", response_model=OrganizationRead)
def update_my_organization(
    payload: OrganizationUpdate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    db: Session = Depends(get_db),
) -> Organization:
    organization = db.get(Organization, current_user.organization_id)
    return update_organization(
        db, organization=organization, name=payload.name, actor_user_id=current_user.id
    )
