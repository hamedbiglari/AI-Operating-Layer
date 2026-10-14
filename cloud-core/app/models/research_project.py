"""
ResearchProject: a bounded research investigation (master spec section
22) — the container a ResearchTask always belongs to. Its `mode`
records WHY the investigation exists (GAP_DRIVEN/USER_DRIVEN/
EXPLORATORY/CONTINUOUS); its `status` tracks whether the investigation
itself is still open (see ResearchProjectStatus for the full lifecycle
rationale — deliberately separate from ResearchTask's execution
lifecycle).

For GAP_DRIVEN research, `knowledge_gap_id` makes the originating
Knowledge Gap explicit (section 11's requirement) — the CHECK
constraint below prevents a GAP_DRIVEN project from silently existing
without one.
"""

import uuid

from sqlalchemy import CheckConstraint, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ResearchMode, ResearchProjectStatus


class ResearchProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "research_projects"
    __table_args__ = (
        CheckConstraint(
            "mode <> 'gap_driven' OR knowledge_gap_id IS NOT NULL",
            name="ck_research_projects_gap_driven_requires_gap",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[ResearchMode] = mapped_column(
        SAEnum(ResearchMode, name="research_mode", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    # Required (and validated, via the CHECK constraint above and
    # research_project_service.create_research_project) when
    # mode == GAP_DRIVEN; optional otherwise. SET NULL on gap delete —
    # a resolved/dismissed gap disappearing must not retroactively
    # break an already-completed research project's own history.
    knowledge_gap_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_gaps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[ResearchProjectStatus] = mapped_column(
        SAEnum(ResearchProjectStatus, name="research_project_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ResearchProjectStatus.DRAFT,
        server_default=ResearchProjectStatus.DRAFT.value,
    )

    knowledge_gap: Mapped["KnowledgeGap | None"] = relationship()  # noqa: F821
    tasks: Mapped[list["ResearchTask"]] = relationship(  # noqa: F821
        back_populates="research_project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ResearchProject id={self.id} mode={self.mode.value} status={self.status.value}>"
