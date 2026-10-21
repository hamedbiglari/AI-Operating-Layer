"""
ImageOcrProvider — a photographed or scanned page delivered as an image (§8.1, §27).

The image itself is one `figure` element covering the whole frame; whatever tesseract reads is laid over
it as OCR paragraphs with pixel geometry (the image's own coordinate space — `Page.width/height` are
the pixel dimensions, and the page record says so). Without tesseract the provider is unavailable and
says so; it never returns an empty document that would look like "this image has no text".
"""
from __future__ import annotations

from pathlib import Path

from app.ingestion.cdr import CanonicalDocument, Confidence, Element, Page
from app.ingestion.providers import ocr as tess
from app.ingestion.providers.base import (
    Availability, DocumentExtractionProvider, ProviderCapabilities, ProviderFailed, ProviderUnavailable,
)


class ImageOcrProvider(DocumentExtractionProvider):
    name = "image_ocr"
    capabilities = ProviderCapabilities(
        formats=(".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"), geometry=True, ocr=True, figures=True,
        runs_locally=True, languages=("tesseract langs",), notes=("text only; no figure interpretation",))

    @property
    def version(self) -> str:
        return f"tesseract-{tess.tesseract_version() or 'absent'}"

    def availability(self) -> Availability:
        if not tess.tesseract_available():
            return Availability(False, "tesseract is not installed")
        return Availability(True)

    def extract(self, path: Path, *, options: dict | None = None) -> CanonicalDocument:
        if not tess.tesseract_available():
            raise ProviderUnavailable("tesseract is not installed")
        languages = (options or {}).get("ocr_languages", "eng")
        try:
            from PIL import Image

            with Image.open(path) as im:
                width, height = im.size
        except Exception as exc:
            raise ProviderFailed(f"unreadable image: {type(exc).__name__}") from exc
        try:
            paragraphs = tess.ocr_image_file(path, languages)
        except Exception as exc:
            raise ProviderFailed(f"OCR failed: {type(exc).__name__}: {exc}"[:300], retryable=True) from exc
        doc = CanonicalDocument(provider=self.name, provider_version=self.version, document_class="scanned",
                                pages=[Page(number=1, width=width, height=height, text_source="ocr",
                                            note="coordinates are image pixels")],
                                config={"ocr_languages": languages})
        doc.elements.append(Element(element_type="figure", page=1, reading_order=0, bbox=[0, 0, width, height],
                                    block_id="p1-image", confidence=1.0, method="whole_image",
                                    attributes={"role": "source_image", "interpreted": False}))
        confs = []
        for i, para in enumerate(paragraphs, start=1):
            confs.append(para.confidence or 0.0)
            doc.elements.append(Element(element_type="paragraph", page=1, reading_order=i, text=para.text,
                                        bbox=para.bbox, block_id=f"p1-ocr{i}", confidence=para.confidence,
                                        method="ocr", lines=[{"text": l.text, "bbox": l.bbox,
                                                              "confidence": l.confidence} for l in para.lines],
                                        attributes={"ocr_engine": "tesseract", "ocr_languages": languages}))
        if not paragraphs:
            doc.review_reasons.append("ocr_found_no_text")
        doc.confidence = Confidence(text=round(sum(confs) / len(confs), 3) if confs else None,
                                    layout=None, figure=1.0)
        return doc.finalize()
