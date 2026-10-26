"""Source overview contract: sources with the status and counts the Sources
list shows per row. Plain counts only; no composite score (ADR-024)."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.schemas.source import SourceRead


class SourceDerivedStatus(str, Enum):
    # Derived from the source's documents and content_access; see
    # source_overview_service for the rules and their order.
    FAILED = "failed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ABSTRACT_ONLY = "abstract_only"
    REFERENCE_ONLY = "reference_only"


class SourceOverviewSort(str, Enum):
    UPDATED = "updated"
    NAME = "name"
    # claims and evidence sort descending, then most recently active.
    CLAIMS = "claims"
    EVIDENCE = "evidence"


class SourceCounts(BaseModel):
    documents: int
    # Distinct knowledge objects and claims behind the source's evidence
    # (evidence -> claim_evidence -> claims).
    knowledge_objects: int
    claims: int
    evidence: int


class SourceOverviewItem(SourceRead):
    counts: SourceCounts
    derived_status: SourceDerivedStatus
    # The later of the source's own updated_at and its newest document's.
    last_activity_at: datetime
    # Sum over the source's documents; null when none has a size.
    file_size: int | None
    # Only for a source with exactly one document: that document's original
    # file type when a conversion recorded it, else the document's own.
    mime_type: str | None


class SourceOverviewPage(BaseModel):
    items: list[SourceOverviewItem]
    total: int
    limit: int
    offset: int
    # Per derived status, after search and source_type but before the status
    # filter and paging, so the filter can show what each choice would return.
    counts_by_status: dict[SourceDerivedStatus, int]
