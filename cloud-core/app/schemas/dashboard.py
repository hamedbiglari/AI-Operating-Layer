"""Dashboard summary contract. Plain counts only; no composite score (ADR-024)."""

from datetime import datetime

from pydantic import BaseModel


class SourceCounts(BaseModel):
    total: int
    added_last_30d: int


class ConversionCounts(BaseModel):
    # Every in-flight attempt, current or not (a reprocess runs as a non-current row).
    in_progress: int
    # NULL when nothing is queued.
    oldest_queued_at: datetime | None
    # Current conversion per document only.
    succeeded: int
    failed: int


class ReviewCounts(BaseModel):
    # Current conversions that are partially_processed or needs_review.
    conversions: int
    evidence_pending: int
    claims_conflicting: int
    gaps_open: int


class DashboardSummary(BaseModel):
    sources: SourceCounts
    conversions: ConversionCounts
    review: ReviewCounts
    # Not tracked yet: always NULL, never 0.
    duplicate_decisions: int | None
    generated_at: datetime
