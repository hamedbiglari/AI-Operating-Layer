"""
ResearchTask: one executable unit of work under a ResearchProject
(master spec section 22) — "ResearchTask created -> queued -> worker
execution -> result -> completed / failed" (section 17). `task_type`
identifies which app/integrations/research/ provider should handle the
query (see app/integrations/research/base.py); `result` is a JSONB
payload holding the outcome status, a summary, and raw provider output
- structured but flexible, since providers are still an open interface
with exactly one placeholder implementation today.

`organization_id` is denormalized here (not just reachable via
research_project_id -> research_projects.organization_id) for the same
reason as every other tenant-owned child table since Phase 2's
KnowledgeVersion: section 8 makes it mandatory on every tenant-owned
row, and it means a task's own tenant check never depends on a join.
research_task_service.create_research_task additionally validates this
column against the PARENT project's actual organization_id before
insert (section 7: "A task must never be able to escape the
organization of its ResearchProject" — enforced at both the DB-FK
level, via research_project_id, and the service level, via that
equality check).

`started_at` is one field beyond section 22's literal list, added
because section 10's research-trail requirement explicitly asks "when
was it executed?" — `completed_at` alone only answers "when did it
finish", not "when did RUNNING actually begin" (there can be a real gap
between QUEUED and a worker picking the task up).
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ResearchTaskStatus


class ResearchTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_tasks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    research_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Open vocabulary (web_search, pubmed_lookup, doi_lookup,
    # manual_entry, document_reingest, ...) - plain indexed string, same
    # rationale as source_type/study_type.
    task_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[ResearchTaskStatus] = mapped_column(
        SAEnum(ResearchTaskStatus, name="research_task_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ResearchTaskStatus.PENDING,
        server_default=ResearchTaskStatus.PENDING.value,
        index=True,
    )
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    research_project: Mapped["ResearchProject"] = relationship(back_populates="tasks")  # noqa: F821
    references: Mapped[list["ResearchTaskReference"]] = relationship(  # noqa: F821
        back_populates="research_task", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ResearchTask id={self.id} task_type={self.task_type!r} status={self.status.value}>"
