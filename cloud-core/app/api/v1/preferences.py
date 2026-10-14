"""GET/PUT /users/me/preferences — the signed-in user's own interface preferences (REQ-SET-001).
A user can only ever read or write their own row; there is no id in the path to tamper with."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.user_preferences import UserPreferences
from app.security.dependencies import get_current_user

router = APIRouter(prefix="/users/me", tags=["preferences"])
NOTIFICATION_KEYS = ("processing_failures", "weekly_summary", "ai_budget_warnings", "security_alerts")


class PreferencesIn(BaseModel):
    language: Literal["en", "fa"] | None = None
    theme: Literal["light", "dark", "system"] | None = None
    font: str | None = Field(default=None, max_length=60)
    notifications: dict[str, bool] | None = None


def _out(p: UserPreferences | None) -> dict:
    if p is None:
        return {"language": "en", "theme": "system", "font": None,
                "notifications": {k: True for k in NOTIFICATION_KEYS}, "persisted": False, "updated_at": None}
    return {"language": p.language, "theme": p.theme, "font": p.font,
            "notifications": {**{k: True for k in NOTIFICATION_KEYS}, **(p.notifications or {})},
            "persisted": True, "updated_at": p.updated_at}


def _row(db: Session, user: User) -> UserPreferences | None:
    return db.execute(select(UserPreferences).where(UserPreferences.organization_id == user.organization_id,
                                                    UserPreferences.user_id == user.id)).scalar_one_or_none()


@router.get("/preferences")
def get_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _out(_row(db, user))


@router.put("/preferences")
def put_preferences(body: PreferencesIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    row = _row(db, user)
    if row is None:
        row = UserPreferences(organization_id=user.organization_id, user_id=user.id, language="en", theme="system")
        db.add(row)
    data = body.model_dump(exclude_none=True)
    if "notifications" in data:
        unknown = set(data["notifications"]) - set(NOTIFICATION_KEYS)
        if unknown:
            from fastapi import HTTPException
            raise HTTPException(422, f"Unknown notification keys: {', '.join(sorted(unknown))}")
        data["notifications"] = {**(row.notifications or {}), **data["notifications"]}
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _out(row)
