"""
DocumentExtractionProvider — the provider boundary (prompt v4.0 §11, ADR-122).

Every way of reading a document — the local PDF layout reader, MarkItDown, Mathpix, a vision model,
whatever comes next — sits behind this one interface and returns the same thing: a
`CanonicalDocument`. Provider-specific output never leaves the provider; it is normalised into the CDR
here, so nothing downstream knows or cares which provider read a page.

Availability is a first-class answer, not an exception path: a provider without credentials or without
its binary reports `available=False` with the reason, and the pipeline records that it was skipped and
why. A provider that is unavailable is never reported as having found nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.ingestion.cdr import CanonicalDocument


class ProviderUnavailable(RuntimeError):
    """Not configured, missing binary, missing credential. Nothing ran."""


class ProviderFailed(RuntimeError):
    """It ran and failed. `retryable` distinguishes a timeout from a file the provider cannot read."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a provider can recover. Declared, not measured — `benchmark.py` measures."""
    formats: tuple[str, ...]
    geometry: bool = False
    reading_order: bool = False
    tables: bool = False
    table_spans: bool = False
    equations_latex: bool = False
    equation_detection: bool = False
    chemistry: bool = False
    figures: bool = False
    ocr: bool = False
    handwriting: bool = False
    languages: tuple[str, ...] = ()
    runs_locally: bool = True          # §55 privacy: does the document leave this deployment?
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class Availability:
    available: bool
    reason: str | None = None


class DocumentExtractionProvider:
    name = "abstract"
    capabilities = ProviderCapabilities(formats=())

    @property
    def version(self) -> str:
        return "0"

    def availability(self) -> Availability:  # pragma: no cover - interface
        raise NotImplementedError

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.capabilities.formats

    def extract(self, path: Path, *, options: dict | None = None) -> CanonicalDocument:  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> dict:
        a = self.availability()
        caps = self.capabilities
        return {"name": self.name, "version": self.version, "available": a.available, "reason": a.reason,
                "capabilities": {k: getattr(caps, k) for k in caps.__dataclass_fields__}}
