"""Per-user interface preferences persisted in Cloud Core (REQ-SET-001).
One row per user; tenant-scoped with a composite FK so a row can never point
at another tenant's user."""
import uuid

from sqlalchemy import JSON, CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

LANGUAGES = ("en", "fa")
THEMES = ("light", "dark", "system")


class UserPreferences(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_user_preferences_user"),
        ForeignKeyConstraint(["user_id", "organization_id"], ["users.id", "users.organization_id"],
                             ondelete="CASCADE", name="fk_user_preferences_user_org"),
        CheckConstraint("language IN ('en', 'fa')", name="ck_user_preferences_language"),
        CheckConstraint("theme IN ('light', 'dark', 'system')", name="ck_user_preferences_theme"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    theme: Mapped[str] = mapped_column(String(10), nullable=False, default="system")
    font: Mapped[str | None] = mapped_column(String(60))
    notifications: Mapped[dict | None] = mapped_column(JSON)
