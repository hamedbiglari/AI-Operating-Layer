"""Dashboard summary - one tenant-scoped read for the Dashboard's count cards."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.security.dependencies import get_current_user
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardSummary:
    """Counts behind the Dashboard cards, each using the same filter as the
    list it links to. No score, by design."""
    return DashboardSummary(**dashboard_service.get_summary(db, organization_id=current_user.organization_id))
