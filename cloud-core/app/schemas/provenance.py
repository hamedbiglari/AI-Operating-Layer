"""Provenance contract: a knowledge object's claims with their evidence links,
and the evidence, sources and documents those links reach, in one read
(Rule 17). Evidence, sources and documents are maps keyed by id, so a record
shared by several links appears once."""

import uuid

from pydantic import BaseModel

from app.models.enums import (
    ClaimEvidenceStrength,
    ClaimStatus,
    EvidenceDirectness,
    EvidenceRelation,
    EvidenceStatus,
    KnowledgeObjectStatus,
)


class ProvenanceKnowledgeObject(BaseModel):
    id: uuid.UUID
    canonical_name: str
    status: KnowledgeObjectStatus


class ProvenanceLink(BaseModel):
    # The claim_evidence row's id: DELETE /claim-evidence/{link_id} removes it.
    link_id: uuid.UUID
    evidence_id: uuid.UUID
    relation: EvidenceRelation
    weight: float | None


class ClaimWithLinks(BaseModel):
    id: uuid.UUID
    predicate: str
    object_value: str | None
    # predicate and object_value joined with a space, as the Knowledge detail shows them.
    text: str
    status: ClaimStatus
    evidence_strength: ClaimEvidenceStrength
    links: list[ProvenanceLink]


class ProvenanceEvidence(BaseModel):
    id: uuid.UUID
    status: EvidenceStatus
    directness: EvidenceDirectness
    basis: str | None
    subject_tested: str | None
    summary: str
    source_id: uuid.UUID
    document_id: uuid.UUID | None
    chunk_id: uuid.UUID | None
    page_number: int | None


class ProvenanceSource(BaseModel):
    id: uuid.UUID
    title: str
    doi: str | None
    full_text_accessed: bool


class ProvenanceDocument(BaseModel):
    id: uuid.UUID
    title: str
    mime_type: str
    # From the document's current conversion; null when it has none.
    converter_version: str | None


class ProvenanceRead(BaseModel):
    knowledge_object: ProvenanceKnowledgeObject
    claims: list[ClaimWithLinks]
    evidence: dict[uuid.UUID, ProvenanceEvidence]
    sources: dict[uuid.UUID, ProvenanceSource]
    documents: dict[uuid.UUID, ProvenanceDocument]
    # Every claim on the object, across pages.
    total_claims: int
    # Distinct evidence reached by this page's claims (the size of `evidence`).
    total_evidence: int
