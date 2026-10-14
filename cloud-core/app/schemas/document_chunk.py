"""Pydantic contracts for DocumentChunk."""

import uuid

from pydantic import BaseModel, ConfigDict, Field


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int | None
    # Embeddings ARE returned here (as a plain float list) since hiding
    # them would make it impossible to verify what got stored — but a
    # 1536-float array per row is wasteful in list responses, so list
    # endpoints use DocumentChunkSummary (below) instead, which reports
    # only whether an embedding exists.
    embedding: list[float] | None
    metadata_value: dict = Field(validation_alias="metadata_", serialization_alias="metadata")


class DocumentChunkSummary(BaseModel):
    """Same as DocumentChunkRead but without the embedding vector — used
    for list endpoints. Built explicitly in the service/API layer
    (see `app/services/document_chunk_service.py::to_summary`) rather
    than parsed automatically from the ORM object, since "has_embedding"
    is a computed field with no direct ORM attribute to alias."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int | None
    has_embedding: bool
    metadata_value: dict = Field(validation_alias="metadata_", serialization_alias="metadata")


class DocumentChunkSearchResult(BaseModel):
    """A chunk plus how close it was to the query, from the pgvector
    similarity search endpoint. Also built explicitly, since `distance`
    comes from the query, not the row itself."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    distance: float
