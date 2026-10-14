"""
Deterministic hash-based embedding provider.

**This is a placeholder, not a real embedding model.** It exists so the
entire storage/indexing/similarity-search pipeline (chunk -> embed ->
store in pgvector -> nearest-neighbor query) can be built, run, and
tested end-to-end in Phase 3 without requiring an external API key or
network access to an embedding provider — this environment's own
network allow-list doesn't include any embedding API, and requiring one
would break `docker compose up --build` working out of the box for
anyone who clones this repo.

It is deterministic (same text always produces the same vector) and
unit-length (so cosine distance behaves sensibly), but the vector space
has NO semantic structure: "cat" and "dog" are exactly as close to each
other as "cat" and "refrigerator". Anyone using semantic search results
from this provider to make real product decisions would be making a
mistake — that mistake is prevented here only by this docstring and by
`docs/development.md` saying the same thing loudly.

**Before using this for anything user-facing**, swap in a real
provider (OpenAI, Cohere, a local sentence-transformers model, etc.)
implementing the same `EmbeddingProvider` interface — no other code
changes needed, since `document_chunk_service.py` depends only on the
interface in `app/integrations/embeddings/base.py`.
"""

import hashlib
import struct

from app.core.config import settings


class DeterministicHashEmbeddingProvider:
    """Derives a unit-length pseudo-random vector from SHA-256(text).

    Implementation: hash the text, use the digest bytes (repeated /
    extended as needed via a simple counter-based expansion) as a seed
    for `dimensions` pseudo-random floats in [-1, 1], then L2-normalize.
    No ML model, no network call, no dependency beyond the standard
    library.
    """

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS

    def _expand_seed_bytes(self, text: str) -> bytes:
        needed = self.dimensions * 4  # 4 bytes per float32-ish value
        out = bytearray()
        counter = 0
        base = text.encode("utf-8")
        while len(out) < needed:
            out.extend(hashlib.sha256(base + counter.to_bytes(4, "big")).digest())
            counter += 1
        return bytes(out[:needed])

    def embed(self, text: str) -> list[float]:
        raw = self._expand_seed_bytes(text)
        ints = struct.unpack(f">{self.dimensions}I", raw)
        # Map uint32 -> [-1, 1]
        values = [(v / 0xFFFFFFFF) * 2 - 1 for v in ints]
        norm = sum(v * v for v in values) ** 0.5
        if norm == 0:
            return values
        return [v / norm for v in values]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


_default_provider: DeterministicHashEmbeddingProvider | None = None


def get_embedding_provider() -> DeterministicHashEmbeddingProvider:
    """Single shared provider instance. Swapping providers later means
    changing this function's return value, not any caller."""
    global _default_provider
    if _default_provider is None:
        _default_provider = DeterministicHashEmbeddingProvider()
    return _default_provider
