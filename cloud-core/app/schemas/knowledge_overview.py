"""Knowledge overview contract: knowledge objects with the counts the Knowledge
list shows per row. Plain counts only; no composite score (ADR-024)."""

from enum import Enum

from pydantic import BaseModel

from app.schemas.knowledge_object import KnowledgeObjectRead


class KnowledgeOverviewSort(str, Enum):
    # conflicting claims, then open gaps, then evidence pending review (all
    # descending), then most recently updated: an order, not a score.
    ACTION_NEEDED = "action_needed"
    NAME = "name"
    UPDATED = "updated"


class KnowledgeCounts(BaseModel):
    # Distinct sources behind the object's evidence (claims -> claim_evidence -> evidence).
    sources: int
    claims: int
    claims_conflicting: int
    # Distinct evidence linked to the object's claims.
    evidence: int
    evidence_verified: int
    evidence_pending_review: int
    gaps_open: int


class KnowledgeOverviewItem(KnowledgeObjectRead):
    counts: KnowledgeCounts
    # Nothing left to do: published, with no conflicting claim, open gap or
    # evidence pending review.
    finished: bool


class KnowledgeOverviewPage(BaseModel):
    items: list[KnowledgeOverviewItem]
    total: int
    limit: int
    offset: int
    # Whether finished objects are part of this result, so the page knows
    # what the "Show finished" toggle is currently showing.
    finished_visible: bool
