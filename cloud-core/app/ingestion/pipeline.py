"""
Document Intelligence pipeline — assembles the canonical Markdown artifact.

ORDER MATTERS AND IS NOT ARBITRARY (ADR-065):

    MarkItDown output          the normalized body
  + extracted tables           replacing what MarkItDown flattened
  + OCR blocks                 recovering what MarkItDown dropped
  = canonical Markdown artifact

The artifact is DERIVED. The original file remains authoritative, and
`source_hash` ties the two together so reprocessing after a converter
upgrade is possible without guessing what produced what.

OCR TEXT IS FENCED AND LABELLED, NOT INLINED

An OCR block is marked `[Image OCR ...]`/`[End OCR]` rather than merged
into the prose. Downstream, claim extraction must be able to tell that a
sentence came from a machine reading a picture rather than from the
document's own text: OCR text is lower-confidence and a claim resting on it
should not look identical to one resting on a typed paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.ingestion.converter import (
    ConversionResult,
    ConversionStatus,
    DocumentConverter,
    default_converter,
)
from app.ingestion.extractors import (
    AssetStatus,
    ExtractionLevel,
    ExtractionResult,
    OcrStatus,
    extract_structure,
)


@dataclass
class PipelineResult:
    conversion: ConversionResult
    extraction: ExtractionResult
    canonical_markdown: str | None
    table_count: int = 0
    image_count: int = 0
    ocr_block_count: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.conversion.ok and self.canonical_markdown is not None


def _assemble(conversion: ConversionResult, extraction: ExtractionResult) -> tuple[str, int]:
    parts: list[str] = [conversion.markdown or ""]
    ocr_blocks = 0

    real_tables = [t for t in extraction.tables if t.row_count > 0]
    if real_tables:
        parts.append("\n\n## Extracted tables\n")
        for index, table in enumerate(real_tables, start=1):
            parts.append(
                f"\n### Table {index} (page {table.page_number}, "
                f"strategy={table.strategy}, confidence={table.confidence})\n\n"
                f"{table.markdown}\n"
            )

    readable = [
        i for i in extraction.images
        if i.ocr_status == OcrStatus.SUCCEEDED and i.ocr_text
    ]
    if readable:
        parts.append("\n\n## Text recovered from images\n")
        for image in readable:
            ocr_blocks += 1
            parts.append(
                f"\n*[Image OCR — page {image.page_number}, asset {image.asset_id}, "
                f"engine {image.ocr_engine}]*\n\n{image.ocr_text}\n\n*[End OCR]*\n"
            )

    # Images we could see but could not read are recorded too. A figure that
    # exists and was not understood is information; omitting it would leave
    # the artifact quietly claiming the page had no figure.
    unread = [
        i for i in extraction.images
        if i.ocr_status in (OcrStatus.NO_TEXT_FOUND, OcrStatus.NOT_ATTEMPTED,
                            OcrStatus.UNAVAILABLE, OcrStatus.FAILED)
        or i.status != AssetStatus.EXTRACTED
    ]
    if unread:
        parts.append("\n\n## Images present but not interpreted\n")
        for image in unread:
            parts.append(
                f"\n- page {image.page_number}, asset `{image.asset_id}` "
                f"({image.byte_size} bytes) — status `{image.status.value}`, "
                f"OCR `{image.ocr_status.value}`. Not interpreted; no claim is "
                f"made about its content.\n"
            )

    return "".join(parts).strip() + "\n", ocr_blocks


def process_document(
    path: Path, *, mime_type: str | None = None, converter: DocumentConverter | None = None,
    enable_ocr: bool = True, ocr_languages: str = "eng",
) -> PipelineResult:
    """Full Level 1-3 pipeline. Level 4 (vision) is not built."""
    converter = converter or default_converter()
    conversion = converter.convert(path, mime_type=mime_type)

    if conversion.status in (ConversionStatus.FAILED, ConversionStatus.UNSUPPORTED):
        # No structure pass on a file we could not normalize: running
        # extractors over it would produce fragments with no context.
        return PipelineResult(
            conversion=conversion,
            extraction=ExtractionResult(level_used=ExtractionLevel.NORMALIZE),
            canonical_markdown=None,
            warnings=[conversion.error or "conversion did not succeed"],
        )

    extraction = extract_structure(
        path, mime_type=mime_type, enable_ocr=enable_ocr, ocr_languages=ocr_languages
    )

    if conversion.status == ConversionStatus.EMPTY:
        # Normalization found no text, but a scanned page may still have
        # yielded OCR. That is a real result and must not be discarded.
        if not any(i.ocr_status == OcrStatus.SUCCEEDED for i in extraction.images):
            return PipelineResult(
                conversion=conversion, extraction=extraction, canonical_markdown=None,
                warnings=[conversion.error or "no usable text"],
            )

    markdown, ocr_blocks = _assemble(conversion, extraction)
    return PipelineResult(
        conversion=conversion,
        extraction=extraction,
        canonical_markdown=markdown,
        table_count=len([t for t in extraction.tables if t.row_count > 0]),
        image_count=len(extraction.images),
        ocr_block_count=ocr_blocks,
        warnings=list(extraction.notes),
    )
