"""Knowledge Transfer Package v1 (prompt v5 §21, §51; ADR-134).

What a worker hands back instead of prose: claims, each carrying the evidence that supports or contradicts it,
with the exact quote and its source location, plus the things a summary loses (gaps, open questions,
assumptions, rejected interpretations, negative and unique findings).

The package is untrusted model output. Parsing it proves only its shape; `knowledge_reconciliation_service`
checks every reference and every quote against stored source text before anything reaches the knowledge layer.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

KTP_VERSION = 1
EVIDENCE_ROUTES = ("direct_subject", "compound_human", "mechanistic", "co_occurrence", "general",
                   "indirect_taxonomic", "indirect_analogous_species", "indirect_formulation", "combination",
                   "background")


class _Strict(BaseModel):
    # Unknown keys are refused: a misspelt field must fail validation, not vanish silently.
    model_config = ConfigDict(extra="forbid")


class KTPEvidence(_Strict):
    source_id: UUID
    document_id: UUID | None = None
    document_element_id: UUID | None = None
    page: int | None = Field(default=None, ge=1)
    # Verbatim text from the source. It is searched for in the stored text; a paraphrase will not be found.
    quote: str = Field(min_length=8, max_length=4000)
    relation: Literal["supports", "contradicts"] = "supports"
    directness: Literal["direct", "indirect"] = "direct"
    route: str | None = None
    # What the evidence is actually about, when that is not the claim's subject (e.g. mannitol for Toranjebin).
    about: str | None = Field(default=None, max_length=300)
    study_type: str | None = Field(default=None, max_length=100)
    population: str | None = Field(default=None, max_length=500)
    sample_size: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)


class KTPClaim(_Strict):
    local_id: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=500)          # entity canonical name or alias
    predicate: str = Field(min_length=1, max_length=200)
    object_value: str | None = Field(default=None, max_length=4000)
    object_entity: str | None = Field(default=None, max_length=500)
    section_key: str | None = Field(default=None, max_length=100)
    claim_type: str | None = Field(default=None, max_length=100)
    finding_kind: Literal["qualitative", "numerical", "negative", "unique", "rare"] = "qualitative"
    evidence: list[KTPEvidence] = Field(default_factory=list, max_length=50)
    uncertainty: str | None = Field(default=None, max_length=1000)


class KnowledgeTransferPackage(_Strict):
    ktp_version: Literal[1] = 1
    task_key: str | None = Field(default=None, max_length=200)
    claims: list[KTPClaim] = Field(default_factory=list, max_length=200)
    open_questions: list[str] = Field(default_factory=list, max_length=100)
    gaps: list[str] = Field(default_factory=list, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    rejected_interpretations: list[str] = Field(default_factory=list, max_length=100)
    # "complete" or a statement of what was not processed; never assumed.
    processing_status: str = Field(default="complete", max_length=500)


def instructions() -> str:
    """The output contract text a planner puts in a worker's task prompt."""
    return ("Return ONLY one JSON object, no prose, matching Knowledge Transfer Package v1: "
            '{"ktp_version": 1, "claims": [{"local_id", "subject", "predicate", "object_value" | "object_entity", '
            '"finding_kind", "evidence": [{"source_id", "document_id", "quote" (verbatim from the source), '
            '"relation": "supports"|"contradicts", "directness": "direct"|"indirect", "about"}]}], '
            '"open_questions", "gaps", "assumptions", "rejected_interpretations", "processing_status"}. '
            "Every claim needs at least one evidence item quoted verbatim. If evidence is about a different "
            "substance than the subject, mark it indirect and name it in `about`.")
