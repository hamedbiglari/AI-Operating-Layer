"""
DocumentConverter — the normalization boundary (ADR-065).

MarkItDown sits behind this interface and nothing else in the codebase
imports it directly. That indirection is the point: MarkItDown is the
*default* engine, not a hardcoded assumption, and a future format-specific
converter can be added without touching ingestion.

WHAT THIS LAYER ADDS ON TOP OF MARKITDOWN

Measured behaviour of MarkItDown 0.1.7 that this wrapper must correct:

  - `broken.pdf` returns the literal string `"None"` — a silent garbage
    success. Treated here as CONVERSION_FAILED, because passing `"None"`
    downstream would create a Document whose content is the word "None".
  - empty output is indistinguishable from successful conversion of an
    empty file. Treated as EMPTY, distinct from both success and failure.

Nothing here parses a binary itself. Table and image extraction live in
`extractors.py`, which runs *after* normalization.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ConversionStatus(str, Enum):
    """Explicit outcomes. `UNSUPPORTED` and `FAILED` are distinct because
    they need different operator responses: one is a missing capability,
    the other is a bad file."""

    SUCCEEDED = "succeeded"
    EMPTY = "empty"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass
class ConversionResult:
    """Carries provenance alongside content, so a caller cannot obtain the
    markdown without also obtaining how it was produced."""

    status: ConversionStatus
    markdown: str | None
    converter_name: str
    converter_version: str
    source_hash: str
    source_size_bytes: int
    source_mime_type: str | None
    output_size_bytes: int
    duration_seconds: float
    error: str | None = None
    conversion_options: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == ConversionStatus.SUCCEEDED


class DocumentConverter:
    """Abstract boundary. `MarkItDownConverter` is the default
    implementation; the interface exists so it is not the only possible
    one."""

    name = "abstract"
    version = "0"

    def supports(self, filename: str, mime_type: str | None) -> bool:  # pragma: no cover
        raise NotImplementedError

    def convert(self, path: Path, mime_type: str | None = None) -> ConversionResult:  # pragma: no cover
        raise NotImplementedError


def sha256_file(path: Path) -> str:
    """Hash of the ORIGINAL bytes — not of the derived text.

    The existing `Document.content_hash` hashes extracted text, which cannot
    detect that two different PDFs produced the same text, nor that the same
    PDF was re-uploaded. Deduplication and reprocessing both need the source
    hash."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class MarkItDownConverter(DocumentConverter):
    """Default engine (ADR-065, ADR-066).

    Extensions listed here are the ones actually verified in this
    environment plus those MarkItDown documents. `supports()` is advisory:
    a file that claims an extension it is not will still fail conversion,
    and that failure is reported rather than hidden.
    """

    name = "markitdown"

    SUPPORTED_EXTENSIONS = {
        ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".csv", ".json", ".xml",
        ".html", ".htm", ".txt", ".md", ".epub", ".zip",
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff",
    }

    def __init__(self, enable_plugins: bool = False) -> None:
        # Plugins default OFF. Measured: enabling them did not recover the
        # dropped PDF image, so they add cost without the benefit that
        # would justify it here. Kept as a flag rather than removed, since
        # a future plugin version may change that.
        self._enable_plugins = enable_plugins
        self._version = self._detect_version()

    @staticmethod
    def _detect_version() -> str:
        try:
            from importlib.metadata import version

            return version("markitdown")
        except Exception:  # pragma: no cover - defensive
            return "unknown"

    @property
    def version(self) -> str:  # type: ignore[override]
        return self._version

    def supports(self, filename: str, mime_type: str | None = None) -> bool:
        return Path(filename).suffix.lower() in self.SUPPORTED_EXTENSIONS

    def convert(self, path: Path, mime_type: str | None = None) -> ConversionResult:
        started = time.monotonic()
        source_hash = sha256_file(path)
        size = path.stat().st_size

        def result(status: ConversionStatus, markdown: str | None, error: str | None = None):
            return ConversionResult(
                status=status,
                markdown=markdown,
                converter_name=self.name,
                converter_version=self.version,
                source_hash=source_hash,
                source_size_bytes=size,
                source_mime_type=mime_type,
                output_size_bytes=len(markdown or ""),
                duration_seconds=round(time.monotonic() - started, 4),
                error=error,
                conversion_options={"enable_plugins": self._enable_plugins},
            )

        if not self.supports(path.name, mime_type):
            return result(ConversionStatus.UNSUPPORTED, None,
                          f"No converter for extension {path.suffix!r}")
        if size == 0:
            return result(ConversionStatus.EMPTY, None, "Source file is empty")

        try:
            from markitdown import MarkItDown

            converted = MarkItDown(enable_plugins=self._enable_plugins).convert(str(path))
            text = converted.text_content
        except Exception as exc:
            # A failed conversion is a recorded outcome, never an exception
            # escaping into the caller - ingestion must be able to store the
            # failure and move on.
            return result(ConversionStatus.FAILED, None, f"{type(exc).__name__}: {exc}"[:500])

        # THE GUARD. Measured: a malformed PDF returns the string "None".
        # Without this, a Document would be created whose entire content is
        # the word "None", and nothing downstream would notice.
        if text is None or text.strip() in ("", "None"):
            return result(
                ConversionStatus.EMPTY, None,
                "Converter produced no usable text (malformed or content-free source)",
            )

        return result(ConversionStatus.SUCCEEDED, text)


def default_converter() -> DocumentConverter:
    return MarkItDownConverter()
