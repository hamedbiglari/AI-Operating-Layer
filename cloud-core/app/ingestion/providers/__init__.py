"""Document extraction providers (ADR-122). `registry()` is the only place providers are constructed."""
from __future__ import annotations

from app.ingestion.providers.base import DocumentExtractionProvider


def registry(*, ocr_languages: str = "eng") -> dict[str, DocumentExtractionProvider]:
    from app.core.config import settings
    from app.ingestion.providers.image_provider import ImageOcrProvider
    from app.ingestion.providers.local_pdf import LocalPdfProvider
    from app.ingestion.providers.markitdown_provider import MarkItDownProvider
    from app.ingestion.providers.mathpix import MathpixProvider

    return {
        "local_pdf": LocalPdfProvider(max_pages=settings.DOCUMENT_MAX_PAGES, ocr_languages=ocr_languages),
        "mathpix": MathpixProvider(),
        "markitdown": MarkItDownProvider(),
        "image_ocr": ImageOcrProvider(),
    }


def configured_order() -> list[str]:
    from app.core.config import settings

    return [n.strip() for n in settings.DOCUMENT_PROVIDER_ORDER.split(",") if n.strip()]
