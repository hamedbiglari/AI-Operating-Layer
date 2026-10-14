"""
Source: where a piece of knowledge came from (master spec section 13).

Critical distinction the master spec insists on, and this model exists
to preserve: source EXISTENCE, source ACCESSIBILITY, source
RELIABILITY, and EVIDENCE STRENGTH are four different things. A Source
row can exist for a paper Claude has never read the full text of —
`access_status` records that honestly instead of pretending the source
doesn't exist or was fully reviewed. EVIDENCE STRENGTH (Phase 4, see
app/models/evidence.py) rates one specific finding drawn from this
source, not the source as a whole — a generally reliable source
(`reliability_score`) can still contain one weak, underpowered study.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SourceAccessStatus, SourceRightsStatus


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Open vocabulary (scientific_paper, book, pdf, website, government,
    # dataset, supplier_document, lab_report, user_upload, first_party,
    # review, news, ...) - plain indexed string, same rationale as
    # object_type/entity_type: new source formats keep appearing.
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True, index=True)
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    pmid: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    isbn: Mapped[str | None] = mapped_column(String(50), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publication_date: Mapped[str | None] = mapped_column(Date, nullable=True)

    access_status: Mapped[SourceAccessStatus] = mapped_column(
        SAEnum(SourceAccessStatus, name="source_access_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SourceAccessStatus.UNKNOWN,
        server_default=SourceAccessStatus.UNKNOWN.value,
    )
    rights_status: Mapped[SourceRightsStatus] = mapped_column(
        SAEnum(SourceRightsStatus, name="source_rights_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SourceRightsStatus.UNKNOWN,
        server_default=SourceRightsStatus.UNKNOWN.value,
    )
    # 0-1: how much this source is trusted in general, independent of
    # any specific finding it contains (that's Evidence.evidence_strength,
    # Phase 4 — see app/models/evidence.py).
    # --- pilot-ready access model (migration 0025): existence / access / rights / acquisition / review
    existence_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unconfirmed", server_default="unconfirmed")
    content_access: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown", server_default="unknown")
    full_text_accessed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    accessed_parts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    acquisition_paths: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_reviewed", server_default="not_reviewed")
    canonical_title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    # how the full text was obtained (migration 0028): open_access_fetch | user_upload
    full_text_origin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    full_text_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    access_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    access_blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reliability_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        back_populates="source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Source id={self.id} type={self.source_type!r} title={self.title!r}>"
