"""
Text chunking.

Master spec section 44 calls for "SEMANTIC CHUNKING" as an ingestion
pipeline step. True semantic chunking (splitting on meaning/topic
boundaries via an NLP model) is a meaningfully larger undertaking than
Phase 3's stated scope ("Sources, Documents, Chunks, pgvector" —
section 62). This module implements a documented, honest baseline
instead: fixed-size character windows with overlap, breaking on
paragraph/sentence boundaries where possible so chunks don't split
mid-sentence. This is a known, standard first-pass chunking strategy
and is explicitly NOT the final word — swapping in a smarter chunker
later doesn't require changing any caller, since this returns the same
`list[str]` shape any better implementation would.
"""

import re

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\u061F])\s+")  # includes Arabic/Persian question mark


def chunk_text(content: str, *, target_chars: int = 1000, overlap_chars: int = 100) -> list[str]:
    """Split `content` into chunks of roughly `target_chars` characters,
    each overlapping the previous by `overlap_chars`, breaking on
    paragraph or sentence boundaries where possible rather than mid-word.

    Returns an empty list for empty/whitespace-only content — callers
    decide what that means for extraction_status (see
    `document_service.py`).
    """
    text = content.strip() if content else ""
    if not text:
        return []

    if len(text) <= target_chars:
        return [text]

    units: list[str] = []
    for paragraph in _PARAGRAPH_SPLIT.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= target_chars:
            units.append(paragraph)
        else:
            units.extend(s for s in _SENTENCE_SPLIT.split(paragraph) if s.strip())

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current} {unit}".strip() if current else unit
        if len(candidate) <= target_chars or not current:
            current = candidate
        else:
            chunks.append(current)
            tail = current[-overlap_chars:] if overlap_chars > 0 else ""
            current = f"{tail} {unit}".strip()
    if current:
        chunks.append(current)

    return chunks
