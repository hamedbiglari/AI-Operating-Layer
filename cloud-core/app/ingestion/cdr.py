"""
Canonical Document Representation — CDR (prompt v4.0 §5–§10, ADR-122).

The CDR is what a document *is* to this system. Markdown, MMD, HTML, LaTeX and JSON are all rendered
FROM it (`render.py`) and none of them is ever parsed back, so two outputs of one source cannot disagree
about what the source said (§7).

    CanonicalDocument
      ├── pages[]            size, rotation, how the page was read (digital | ocr | none)
      └── elements[]         one per block: heading, paragraph, list item, table, figure, caption,
                             equation, reference, footnote, header, footer, link, page number …
                             each with reading order, geometry, language/script, confidence, provenance

WHAT AN ELEMENT CARRIES, AND WHY

* `text` is exactly what the provider read. `normalized_text` is NFC + ligature expansion. Both are
  kept: normalisation is a lossy decision and the original must stay inspectable (§8.1, §26).
* `bbox` is `[x0, y0, x1, y1]` in PDF points from the page's top-left, with the page size on the page
  record, so a reviewer can find the exact place a claim came from (§9). Absent geometry is `None`,
  never `[0, 0, 0, 0]` — an invented box would point a reviewer at the wrong place.
* `confidence` is per element and `None` when the provider cannot say. It is EXTRACTION confidence —
  how sure we are the source says this — and never evidence quality (§78 prohibitions).
* `method` names how the element was obtained (`digital_text`, `ocr`, `vision`, `provider:mathpix` …),
  so OCR'd text never looks identical to typed text downstream.

Nothing here does I/O. Providers build these objects; `ingestion_service` persists them.
"""
from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field

CDR_SCHEMA_VERSION = 1

# Every kind of block the representation can hold. Order is not meaningful.
ELEMENT_TYPES = (
    "title", "heading", "paragraph", "list_item", "table", "figure", "caption",
    "equation_display", "equation_inline", "chemical", "reference", "footnote",
    "header", "footer", "page_number", "link", "code", "marginal", "page_break",
    "transcript_segment",      # audio/video: carries start_ms/end_ms, no bbox (§27 extension point)
    "unclassified",            # read but not classified — kept, never dropped (§13)
)

# How a page's text was obtained
PAGE_TEXT_SOURCES = ("digital", "ocr", "mixed", "none", "provider")

DOCUMENT_CLASSES = ("digital", "scanned", "hybrid", "not_paginated", "unknown")

_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
              "ﬅ": "st", "ﬆ": "st"}


def normalize_text(text: str | None) -> str | None:
    """NFC plus ligature expansion. Deliberately NOT NFKC: compatibility folding turns superscript ² into
    2 and changes the meaning of formulae (§8.4)."""
    if text is None:
        return None
    out = unicodedata.normalize("NFC", text)
    for lig, rep in _LIGATURES.items():
        out = out.replace(lig, rep)
    return out


def detect_script(text: str | None) -> tuple[str | None, str | None]:
    """(dominant script, direction). Counted over letters only, so digits and punctuation cannot tip a
    Persian paragraph into 'Latin'. Returns (None, None) when there are no letters to judge by."""
    if not text:
        return None, None
    counts: dict[str, int] = {}
    for ch in text:
        if not ch.isalpha():
            continue
        cp = ord(ch)
        if 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F or 0xFB50 <= cp <= 0xFDFF or 0xFE70 <= cp <= 0xFEFF:
            script = "Arab"
        elif 0x0590 <= cp <= 0x05FF:
            script = "Hebr"
        elif 0x0370 <= cp <= 0x03FF:
            script = "Grek"
        elif 0x0400 <= cp <= 0x04FF:
            script = "Cyrl"
        elif 0x4E00 <= cp <= 0x9FFF:
            script = "Hani"
        elif cp < 0x0250:
            script = "Latn"
        else:
            script = "Other"
        counts[script] = counts.get(script, 0) + 1
    if not counts:
        return None, None
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])
    total = sum(counts.values())
    dominant = ordered[0][0]
    # "mixed" only when a second script is a real share of the text, not a stray loanword
    if len(ordered) > 1 and ordered[1][1] / total >= 0.2:
        dominant = f"{ordered[0][0]}+{ordered[1][0]}"
    rtl = ordered[0][0] in ("Arab", "Hebr")
    return dominant, ("rtl" if rtl else "ltr")


def guess_language(text: str | None, script: str | None) -> str | None:
    """A conservative language hint from script and a few unambiguous letters. Never a confident claim:
    Arabic and Persian share a script, and only letters unique to Persian decide for Persian."""
    if not text or not script:
        return None
    if script.startswith("Arab"):
        # Persian-only letters, including the Persian forms of yeh (U+06CC) and keheh (U+06A9): Arabic writes
        # ي (U+064A) and ك (U+0643) instead, so these decide for Persian on their own.
        if any(ch in text for ch in "پچژگیک"):
            return "fa"
        if any(ch in text for ch in "ةيك"):
            return "ar"
        return None
    if script.startswith("Latn"):
        return None      # English vs. any other Latin-script language is not decidable from letters alone
    return None


@dataclass
class Element:
    element_type: str
    page: int | None                       # 1-based; None for non-paginated sources
    reading_order: int
    text: str | None = None
    normalized_text: str | None = None
    bbox: list[float] | None = None        # [x0, y0, x1, y1], PDF points, top-left origin
    block_id: str = ""                     # stable within one extraction: p{page}-b{n}
    parent_block_id: str | None = None     # a caption's figure, a cell's table, a list item's list
    level: int | None = None               # heading level, list depth
    language: str | None = None
    script: str | None = None
    direction: str | None = None
    confidence: float | None = None
    method: str = "digital_text"
    attributes: dict = field(default_factory=dict)   # table cells, latex, href, font size, start_ms …
    lines: list[dict] = field(default_factory=list)  # [{text, bbox, confidence}] where available

    def finalize(self) -> "Element":
        if self.element_type not in ELEMENT_TYPES:
            self.attributes.setdefault("original_type", self.element_type)
            self.element_type = "unclassified"
        if self.normalized_text is None and self.text is not None:
            self.normalized_text = normalize_text(self.text)
        if self.script is None and self.text:
            self.script, self.direction = detect_script(self.text)
        if self.language is None and self.text:
            self.language = guess_language(self.text, self.script)
        if self.confidence is not None:
            self.confidence = round(max(0.0, min(1.0, float(self.confidence))), 3)
        return self


@dataclass
class Page:
    number: int
    width: float | None = None
    height: float | None = None
    rotation: int = 0
    text_source: str = "digital"
    processed: bool = True
    note: str | None = None


@dataclass
class Confidence:
    """§10 — differentiated. `None` means *not measured*, and is never averaged in as zero."""
    text: float | None = None
    layout: float | None = None
    table: float | None = None
    equation: float | None = None
    figure: float | None = None

    @property
    def overall(self) -> float | None:
        # Conservative: a document is only as trustworthy as its weakest measured dimension.
        measured = [v for v in (self.text, self.layout, self.table, self.equation, self.figure) if v is not None]
        return round(min(measured), 3) if measured else None


@dataclass
class CanonicalDocument:
    provider: str
    provider_version: str
    document_class: str = "unknown"
    pages: list[Page] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    confidence: Confidence = field(default_factory=Confidence)
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    # §12: reasons a person should look at this extraction before trusting it
    review_reasons: list[str] = field(default_factory=list)
    unprocessed_pages: list[int] = field(default_factory=list)
    # verbatim provider outputs (e.g. Mathpix's .mmd), kept as candidate outputs for audit (§12)
    raw_outputs: dict = field(default_factory=dict)

    @property
    def partially_processed(self) -> bool:
        return bool(self.unprocessed_pages)

    def finalize(self) -> "CanonicalDocument":
        for i, el in enumerate(self.elements):
            el.finalize()
            if not el.block_id:
                el.block_id = f"p{el.page or 0}-b{i}"
        self.elements.sort(key=lambda e: e.reading_order)
        if self.page_count is None and self.pages:
            self.page_count = len(self.pages)
        return self

    def to_dict(self) -> dict:
        return {"schema_version": CDR_SCHEMA_VERSION, "provider": self.provider,
                "provider_version": self.provider_version, "document_class": self.document_class,
                "page_count": self.page_count, "pages": [asdict(p) for p in self.pages],
                "confidence": {**asdict(self.confidence), "overall": self.confidence.overall},
                "warnings": self.warnings, "review_reasons": self.review_reasons,
                "unprocessed_pages": self.unprocessed_pages,
                "elements": [asdict(e) for e in self.elements]}

    def text_content(self) -> str:
        """Body text in reading order, excluding running headers/footers — what a reader would read."""
        skip = {"header", "footer", "page_number", "page_break", "link"}
        return "\n".join((e.normalized_text or e.text or "") for e in self.elements
                         if e.element_type not in skip and (e.text or ""))
