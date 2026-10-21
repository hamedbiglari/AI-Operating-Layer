"""
Extraction with fallback and recovery (prompt v4.0 §12, ADR-122).

    primary provider → validate → confidence check
        ↓ (failed, partial, or below DOCUMENT_MIN_CONFIDENCE)
    next provider in DOCUMENT_PROVIDER_ORDER → same checks
        ↓
    choose the best candidate · keep EVERY candidate · flag for human review when warranted

Two rules this module exists to keep:

* **Candidates are never merged.** If two providers disagree about what a document says, the
  disagreement is recorded (`providers_disagree`) and a person decides. Silently splicing two readings
  together would produce a document neither provider actually read.
* **An unavailable provider is not a provider that found nothing.** Each skipped provider is recorded
  with its reason, so "Mathpix was not configured" can never be read as "Mathpix found no equations".
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from app.ingestion.cdr import CanonicalDocument
from app.ingestion.providers import configured_order, registry
from app.ingestion.providers.base import DocumentExtractionProvider, ProviderFailed, ProviderUnavailable


@dataclass
class Candidate:
    provider: str
    provider_version: str | None
    status: str                       # succeeded | failed | skipped
    document: CanonicalDocument | None = None
    reason: str | None = None
    retryable: bool = False

    @property
    def overall(self) -> float | None:
        return self.document.confidence.overall if self.document else None


@dataclass
class ExtractionOutcome:
    candidates: list[Candidate] = field(default_factory=list)
    selected: Candidate | None = None
    review_reasons: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)

    @property
    def processing_state(self) -> str:
        """§25 vocabulary. `processed` is only claimed for a complete, unflagged extraction."""
        if self.selected is None:
            return "failed"
        if self.selected.document.partially_processed:
            return "partially_processed"
        if self.needs_review:
            return "needs_review"
        return "processed"


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff")


def _image_inventory(path: Path) -> CanonicalDocument | None:
    from app.ingestion.cdr import Element, Page

    try:
        from PIL import Image

        with Image.open(path) as im:
            width, height = im.size
    except Exception:
        return None
    doc = CanonicalDocument(provider="inventory", provider_version="1", document_class="scanned",
                            pages=[Page(number=1, width=width, height=height, text_source="none", processed=False,
                                        note="no OCR provider available; text not read")])
    doc.elements.append(Element(element_type="figure", page=1, reading_order=0, bbox=[0, 0, width, height],
                                block_id="p1-image", confidence=1.0, method="whole_image",
                                attributes={"role": "source_image", "interpreted": False}))
    doc.unprocessed_pages = [1]
    doc.review_reasons.append("ocr_unavailable_for_image")
    return doc.finalize()


def _rank(c: Candidate) -> tuple:
    doc = c.document
    return (0 if doc.partially_processed else 1,
            1 if doc.elements else 0,
            c.overall if c.overall is not None else 0.0)


def run(path: Path, *, providers: dict[str, DocumentExtractionProvider] | None = None,
        order: list[str] | None = None, min_confidence: float | None = None,
        options: dict | None = None, exhaustive: bool = False) -> ExtractionOutcome:
    from app.core.config import settings

    providers = providers or registry(ocr_languages=(options or {}).get("ocr_languages", "eng"))
    order = order or configured_order()
    floor = settings.DOCUMENT_MIN_CONFIDENCE if min_confidence is None else min_confidence
    out = ExtractionOutcome()

    for name in order:
        provider = providers.get(name)
        if provider is None:
            out.candidates.append(Candidate(name, None, "skipped", reason="unknown provider name in configuration"))
            continue
        if not provider.supports(path):
            continue                     # not a candidate for this format at all; nothing to record
        availability = provider.availability()
        if not availability.available:
            out.candidates.append(Candidate(name, provider.version, "skipped", reason=availability.reason))
            continue
        try:
            doc = provider.extract(path, options=options)
        except ProviderUnavailable as exc:
            out.candidates.append(Candidate(name, provider.version, "skipped", reason=str(exc)))
            continue
        except ProviderFailed as exc:
            out.candidates.append(Candidate(name, provider.version, "failed", reason=str(exc)[:500],
                                            retryable=exc.retryable))
            continue
        except Exception as exc:  # a provider bug must not take the document down with it
            out.candidates.append(Candidate(name, provider.version, "failed",
                                            reason=f"{type(exc).__name__}: {exc}"[:500]))
            continue
        cand = Candidate(name, provider.version, "succeeded", document=doc)
        out.candidates.append(cand)
        good_enough = (not doc.partially_processed and doc.elements
                       and (cand.overall is None or cand.overall >= floor))
        if good_enough and not exhaustive:
            break

    succeeded = [c for c in out.candidates if c.status == "succeeded"]
    if not succeeded and path.suffix.lower() in IMAGE_SUFFIXES:
        # §13: an image nobody could read is still an image. Record that it exists, where, and how big,
        # flagged for review — rather than leaving no trace of it.
        inventory = _image_inventory(path)
        if inventory is not None:
            out.candidates.append(Candidate("inventory", "1", "succeeded", document=inventory,
                                            reason="no text-reading provider available; image recorded only"))
            succeeded = [out.candidates[-1]]
    if not succeeded:
        out.review_reasons.append("no_provider_succeeded")
        return out
    out.selected = max(succeeded, key=_rank)
    doc = out.selected.document
    out.review_reasons.extend(r for r in doc.review_reasons if r not in out.review_reasons)
    if out.selected.overall is not None and out.selected.overall < floor:
        out.review_reasons.append("low_extraction_confidence")
    if not doc.elements:
        out.review_reasons.append("no_content_extracted")
    base = doc.text_content()[:20000]
    for other in succeeded:
        if other is out.selected or not other.document.elements:
            continue
        ratio = difflib.SequenceMatcher(None, base, other.document.text_content()[:20000]).quick_ratio()
        if ratio < 0.8:
            if "providers_disagree" not in out.review_reasons:
                out.review_reasons.append("providers_disagree")
    _flag_prompt_injection(out, doc)
    return out


def _flag_prompt_injection(out, doc) -> None:  # noqa: ANN001
    """ADR-126: a document carrying instructions aimed at an AI model, or text hidden with invisible characters,
    is flagged for review at ingestion — before any synthesis can use it. The text itself is kept unchanged:
    the evidence record must show what the source really says."""
    from app.ai import prompt_safety

    raw = "\n".join(e.text or "" for e in doc.elements)[:2_000_000]
    s = prompt_safety.sanitize(raw)
    a = prompt_safety.detect(s.text, hidden=s.removed)
    if a.risk in ("medium", "high") and "possible_prompt_injection" not in out.review_reasons:
        out.review_reasons.append("possible_prompt_injection")
    if a.hidden_characters and "hidden_text_characters" not in out.review_reasons:
        out.review_reasons.append("hidden_text_characters")
    if a.signals:
        doc.warnings.append("prompt-safety: " + "; ".join(
            f"{x['category']} ({x['severity']})" for x in a.signals)[:500])
