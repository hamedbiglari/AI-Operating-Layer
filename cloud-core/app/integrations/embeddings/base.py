"""
Embedding provider interface.

The ingestion pipeline (master spec section 44) needs to turn text into
vectors, but WHICH model does that is explicitly meant to be swappable
("Do not hard-code assumptions that prevent changing embedding models
later" — Phase 0 design note). This module defines the interface every
provider implements; `app/services/document_chunk_service.py` depends
only on this interface, never on a concrete provider.
"""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Anything that turns text into a fixed-length vector."""

    dimensions: int

    def embed(self, text: str) -> list[float]:
        """Return a single embedding vector for `text`."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input string, same order."""
        ...
