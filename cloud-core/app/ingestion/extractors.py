"""
Structured extraction — tables, images, OCR (ADR-065, ADR-066).

This module exists because MarkItDown measurably does not do these things:
it flattens PDF tables and silently drops embedded images. Everything here
runs AFTER normalization and enriches the result; nothing here replaces the
converter.

COST-AWARE LEVELS (recorded per document, never inferred)

    Level 1  MarkItDown conversion            always, negligible
    Level 2  tables + image extraction        PDFs only, ~0.01-0.05s/page
    Level 3  OCR of extracted images          only when likely to help
    Level 4  Vision/LLM interpretation        NOT BUILT, policy-gated

The level actually used is stored, so a reader can tell whether a figure's
text came from cheap OCR or expensive model interpretation - or from
nothing at all.

WHAT IS DELIBERATELY NOT HERE

Figure/chart *semantics* (what a chart means) needs a vision model. That is
Level 4 and is not built. An OCR string is not an interpretation, and
promoting one to the other is exactly the kind of silent upgrade the
evidence rules forbid.
"""

from __future__ import annotations

import shutil
from app.ingestion.providers.ocr import safe_languages
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ExtractionLevel(int, Enum):
    NORMALIZE = 1
    STRUCTURE = 2
    OCR = 3
    VISION = 4


class AssetStatus(str, Enum):
    """`DETECTED_NOT_EXTRACTED` is the important value: it records that an
    image exists even when we could not pull the bytes out. Dropping it
    would repeat MarkItDown's failure mode."""

    EXTRACTED = "extracted"
    DETECTED_NOT_EXTRACTED = "detected_not_extracted"
    FAILED = "failed"


class OcrStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    SUCCEEDED = "succeeded"
    NO_TEXT_FOUND = "no_text_found"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


# Bounds. Untrusted input: a PDF can claim thousands of pages or embed a
# decompression bomb. These are ceilings, not targets.
MAX_PAGES = 200
MAX_TABLES = 200
MAX_IMAGES = 100
MAX_IMAGE_BYTES = 25 * 1024 * 1024
OCR_TIMEOUT_SECONDS = 20
# Below this an image is almost certainly an icon or rule, not content.
MIN_OCR_IMAGE_BYTES = 1024


@dataclass
class ExtractedTable:
    page_number: int
    row_count: int
    column_count: int
    headers: list[str]
    rows: list[list[str]]
    markdown: str
    strategy: str
    confidence: float


@dataclass
class ExtractedImage:
    page_number: int
    asset_id: str
    byte_size: int
    source_hash: str
    status: AssetStatus
    ocr_status: OcrStatus = OcrStatus.NOT_ATTEMPTED
    ocr_text: str | None = None
    ocr_engine: str | None = None
    ocr_version: str | None = None
    error: str | None = None


@dataclass
class ExtractionResult:
    level_used: ExtractionLevel
    tables: list[ExtractedTable] = field(default_factory=list)
    images: list[ExtractedImage] = field(default_factory=list)
    page_count: int | None = None
    duration_seconds: float = 0.0
    notes: list[str] = field(default_factory=list)


def _rows_to_markdown(headers: list[str], rows: list[list[str]]) -> str:
    def esc(cell: str) -> str:
        return (cell or "").replace("|", "\\|").replace("\n", " ").strip()

    head = "| " + " | ".join(esc(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(esc(c) for c in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def _clean_table(raw: list[list]) -> tuple[list[str], list[list[str]]]:
    """Drops the all-empty spacer rows the `text` strategy produces.

    Measured: the text strategy returned real rows interleaved with
    `['', '', '']`. Keeping those would put empty rows in the Markdown and
    inflate row counts."""
    cleaned = [
        [(c if c is not None else "").strip() for c in row]
        for row in raw
        if any((c or "").strip() for c in row)
    ]
    if not cleaned:
        return [], []
    return cleaned[0], cleaned[1:]


def extract_pdf_tables(path: Path) -> tuple[list[ExtractedTable], list[str]]:
    """Recovers tables MarkItDown flattens.

    Strategy order is evidence-based (ADR-066): `lines` first because a
    ruled table extracts perfectly and unambiguously; `text` as fallback
    because it recovers unruled tables but is more speculative - hence the
    lower recorded confidence."""
    notes: list[str] = []
    try:
        import pdfplumber
    except ImportError:
        return [], ["pdfplumber unavailable; PDF tables not extracted"]

    tables: list[ExtractedTable] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for index, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
                found = page.extract_tables()
                strategy, confidence = "lines", 0.9
                if not found:
                    found = page.extract_tables(
                        {"vertical_strategy": "text", "horizontal_strategy": "text"}
                    )
                    strategy, confidence = "text", 0.6
                for raw in found:
                    if len(tables) >= MAX_TABLES:
                        notes.append(f"table cap {MAX_TABLES} reached; extraction truncated")
                        return tables, notes
                    headers, rows = _clean_table(raw)
                    if not headers:
                        continue
                    tables.append(ExtractedTable(
                        page_number=index,
                        row_count=len(rows),
                        column_count=len(headers),
                        headers=headers,
                        rows=rows,
                        markdown=_rows_to_markdown(headers, rows),
                        strategy=strategy,
                        confidence=confidence,
                    ))
    except Exception as exc:
        notes.append(f"table extraction failed: {type(exc).__name__}: {exc}"[:300])
    return tables, notes


def extract_pdf_images(path: Path) -> tuple[list[ExtractedImage], list[str], dict[str, bytes]]:
    """Recovers embedded images MarkItDown drops.

    An image that cannot be extracted is still RECORDED, with
    `DETECTED_NOT_EXTRACTED`. Silently omitting it would reproduce exactly
    the failure this module exists to fix."""
    import hashlib

    notes: list[str] = []
    payloads: dict[str, bytes] = {}
    try:
        import pypdf
    except ImportError:
        return [], ["pypdf unavailable; embedded images not extracted"], {}

    images: list[ExtractedImage] = []
    try:
        reader = pypdf.PdfReader(str(path))
        for index, page in enumerate(reader.pages[:MAX_PAGES], start=1):
            try:
                embedded = list(page.images)
            except Exception as exc:
                notes.append(f"page {index}: image listing failed ({type(exc).__name__})")
                continue
            for item in embedded:
                if len(images) >= MAX_IMAGES:
                    notes.append(f"image cap {MAX_IMAGES} reached; extraction truncated")
                    return images, notes, payloads
                try:
                    data = item.data
                    if len(data) > MAX_IMAGE_BYTES:
                        images.append(ExtractedImage(
                            page_number=index, asset_id=item.name, byte_size=len(data),
                            source_hash="", status=AssetStatus.DETECTED_NOT_EXTRACTED,
                            error=f"exceeds {MAX_IMAGE_BYTES} byte cap",
                        ))
                        continue
                    digest = hashlib.sha256(data).hexdigest()
                    payloads[digest] = data
                    images.append(ExtractedImage(
                        page_number=index, asset_id=item.name, byte_size=len(data),
                        source_hash=digest, status=AssetStatus.EXTRACTED,
                    ))
                except Exception as exc:
                    images.append(ExtractedImage(
                        page_number=index, asset_id=getattr(item, "name", "unknown"),
                        byte_size=0, source_hash="", status=AssetStatus.FAILED,
                        error=f"{type(exc).__name__}"[:120],
                    ))
    except Exception as exc:
        notes.append(f"image extraction failed: {type(exc).__name__}: {exc}"[:300])
    return images, notes, payloads


def tesseract_version() -> str | None:
    if not shutil.which("tesseract"):
        return None
    try:
        out = subprocess.run(["tesseract", "--version"], capture_output=True,
                             text=True, timeout=10)
        return out.stdout.splitlines()[0].strip() if out.stdout else "unknown"
    except Exception:  # pragma: no cover - defensive
        return None


def ocr_image(data: bytes, languages: str = "eng") -> tuple[OcrStatus, str | None, str | None]:
    """Level 3. Runs tesseract over untrusted image bytes.

    Security: a subprocess with a timeout, no shell, and a temp file rather
    than stdin so a malformed payload cannot confuse argument parsing. A
    missing binary yields UNAVAILABLE - never an empty string, which would
    be indistinguishable from 'no text in this image'."""
    version = tesseract_version()
    if version is None:
        return OcrStatus.UNAVAILABLE, None, None
    if len(data) < MIN_OCR_IMAGE_BYTES:
        return OcrStatus.NOT_ATTEMPTED, None, version

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "asset.bin"
        target.write_bytes(data)
        try:
            out = subprocess.run(
                ["tesseract", str(target), "stdout", "-l", safe_languages(languages)],
                capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS, shell=False,
            )
        except subprocess.TimeoutExpired:
            return OcrStatus.FAILED, None, version
        except Exception:
            return OcrStatus.FAILED, None, version

    text = (out.stdout or "").strip()
    if not text:
        return OcrStatus.NO_TEXT_FOUND, None, version
    return OcrStatus.SUCCEEDED, text, version


def extract_structure(
    path: Path, *, mime_type: str | None = None, enable_ocr: bool = True,
    ocr_languages: str = "eng",
) -> ExtractionResult:
    """Levels 2 and 3. Non-PDF inputs return Level 1 untouched, because
    MarkItDown already handles DOCX/XLSX tables correctly (measured) and
    duplicating that would risk disagreeing with it."""
    started = time.monotonic()
    if path.suffix.lower() != ".pdf":
        return ExtractionResult(
            level_used=ExtractionLevel.NORMALIZE,
            notes=["Non-PDF: MarkItDown handles structure for this format"],
            duration_seconds=round(time.monotonic() - started, 4),
        )

    tables, table_notes = extract_pdf_tables(path)
    images, image_notes, payloads = extract_pdf_images(path)
    notes = [*table_notes, *image_notes]
    level = ExtractionLevel.STRUCTURE

    if enable_ocr and images:
        for image in images:
            if image.status != AssetStatus.EXTRACTED:
                continue
            data = payloads.get(image.source_hash)
            if data is None:
                continue
            status, text, version = ocr_image(data, languages=ocr_languages)
            image.ocr_status = status
            image.ocr_text = text
            image.ocr_engine = "tesseract" if version else None
            image.ocr_version = version
            if status == OcrStatus.SUCCEEDED:
                level = ExtractionLevel.OCR

    page_count = None
    try:
        import pypdf

        page_count = len(pypdf.PdfReader(str(path)).pages)
    except Exception:
        pass
    if page_count is not None and page_count > MAX_PAGES:
        # v4 §13: this cap used to apply silently. Pages beyond it are not scanned for tables or images
        # by this legacy pass; say so. (The canonical representation has its own, configurable limit and
        # lists unprocessed pages explicitly.)
        notes.append(f"legacy table/image pass covered pages 1–{MAX_PAGES} of {page_count}; "
                     f"pages {MAX_PAGES + 1}–{page_count} were not scanned for tables or images")

    return ExtractionResult(
        level_used=level, tables=tables, images=images, page_count=page_count,
        duration_seconds=round(time.monotonic() - started, 4), notes=notes,
    )
