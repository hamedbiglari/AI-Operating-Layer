"""
LocalPdfProvider — layout-aware PDF reading on this deployment (prompt v4.0 §8, §9, ADR-122).

Built on pdfplumber (MIT) because it exposes what MarkItDown throws away: every word with its box, font
and size; every ruled table with its cell boxes; every image's position; every hyperlink's rectangle.
From those it reconstructs, per page:

    words → lines → blocks → reading order (columns, full-width bands, RTL)
          → classification (heading, list, caption, equation candidate, chemistry, reference, footnote)
          → document level: running headers/footers and page numbers by repetition across pages,
            captions joined to their figure/table, tables continued across a page break

Scanned pages (no text layer, mostly image) are rendered and read by tesseract with word geometry
(`providers/ocr.py`). When tesseract is absent the page is listed in `unprocessed_pages` with the reason
— the document becomes `partially_processed`, never silently shorter.

WHAT IT DOES NOT DO, AND SAYS SO
* No LaTeX. Equation *candidates* are detected (symbol density, math fonts) at low confidence; their
  text is the PDF's own glyph sequence. Recognising mathematics needs a provider such as Mathpix.
* No figure semantics. A figure is located and captioned, never interpreted (§8.6).
* Bidirectional text: pdfminer reports glyphs in visual order. Words are re-ordered right-to-left for
  RTL lines, but character order inside a digital RTL word is not independently verified, so such
  documents are flagged for review rather than assumed correct.
"""
from __future__ import annotations

import re
import statistics
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.ingestion.cdr import CanonicalDocument, Confidence, Element, Page, detect_script
from app.ingestion.providers import classify as C
from app.ingestion.providers import ocr as tess
from app.ingestion.providers.base import (
    Availability, DocumentExtractionProvider, ProviderCapabilities, ProviderFailed,
)

DEFAULT_MAX_PAGES = 2000
MARGIN_BAND = 0.09            # top/bottom share of the page where running headers/footers live
LINE_GAP_FACTOR = 1.6         # horizontal gap (× font size) that splits a line into column segments
OCR_RESOLUTION = 300


@dataclass
class _Seg:
    """One line segment: words on one baseline with no column gutter between them."""
    words: list[dict]
    x0: float
    top: float
    x1: float
    bottom: float
    size: float
    fonts: list[str]
    rtl: bool
    upright: bool

    @property
    def text(self) -> str:
        ordered = sorted(self.words, key=lambda w: -w["x1"]) if self.rtl else sorted(self.words, key=lambda w: w["x0"])
        return " ".join(w["text"] for w in ordered)


@dataclass
class _Block:
    segs: list[_Seg] = field(default_factory=list)

    @property
    def x0(self): return min(s.x0 for s in self.segs)
    @property
    def x1(self): return max(s.x1 for s in self.segs)
    @property
    def top(self): return min(s.top for s in self.segs)
    @property
    def bottom(self): return max(s.bottom for s in self.segs)
    @property
    def size(self): return statistics.median(s.size for s in self.segs)
    @property
    def text(self): return "\n".join(s.text for s in sorted(self.segs, key=lambda s: s.top))
    @property
    def rtl(self): return sum(1 for s in self.segs if s.rtl) * 2 > len(self.segs)


def _is_rtl_text(text: str) -> bool:
    script, direction = detect_script(text)
    return direction == "rtl"


class LocalPdfProvider(DocumentExtractionProvider):
    name = "local_pdf"
    capabilities = ProviderCapabilities(
        formats=(".pdf",), geometry=True, reading_order=True, tables=True, table_spans=True,
        equation_detection=True, chemistry=True, figures=True, ocr=True, languages=("any (digital)", "tesseract langs (scanned)"),
        runs_locally=True,
        notes=("equations are detected, not recognised (no LaTeX)", "figures are located, not interpreted"))

    def __init__(self, *, max_pages: int = DEFAULT_MAX_PAGES, ocr_languages: str = "eng") -> None:
        self.max_pages = max_pages
        self.ocr_languages = ocr_languages

    @property
    def version(self) -> str:
        try:
            from importlib.metadata import version
            return f"pdfplumber-{version('pdfplumber')}"
        except Exception:  # pragma: no cover
            return "pdfplumber-unknown"

    def availability(self) -> Availability:
        try:
            import pdfplumber  # noqa: F401
        except ImportError:
            return Availability(False, "pdfplumber is not installed")
        return Availability(True, None if tess.tesseract_available() else
                            "available; scanned pages cannot be read because tesseract is not installed")

    # ------------------------------------------------------------------ entry point
    def extract(self, path: Path, *, options: dict | None = None) -> CanonicalDocument:
        import pdfplumber

        options = options or {}
        ocr_languages = options.get("ocr_languages", self.ocr_languages)
        doc = CanonicalDocument(provider=self.name, provider_version=self.version,
                                config={"max_pages": self.max_pages, "ocr_languages": ocr_languages})
        try:
            pdf = pdfplumber.open(str(path))
        except Exception as exc:
            raise ProviderFailed(f"cannot open PDF: {type(exc).__name__}: {exc}"[:300]) from exc
        with pdf:
            total = len(pdf.pages)
            doc.page_count = total
            if total > self.max_pages:
                doc.unprocessed_pages = list(range(self.max_pages + 1, total + 1))
                doc.warnings.append(f"{total} pages; pages {self.max_pages + 1}–{total} exceed the configured "
                                    f"limit of {self.max_pages} and were NOT processed")
                doc.review_reasons.append("page_limit_exceeded")
            order = 0
            stats = _Stats()
            per_page_blocks: list[tuple[Page, list[Element]]] = []
            for index, page in enumerate(pdf.pages[: self.max_pages], start=1):
                p = Page(number=index, width=float(page.width), height=float(page.height),
                         rotation=int(getattr(page, "rotation", 0) or 0))
                try:
                    elements = self._read_page(page, p, stats, ocr_languages)
                except Exception as exc:  # one bad page must not lose the rest of the document
                    p.processed, p.text_source = False, "none"
                    p.note = f"page failed: {type(exc).__name__}: {exc}"[:200]
                    doc.unprocessed_pages.append(index)
                    doc.review_reasons.append("page_extraction_failed")
                    elements = []
                if not p.processed and index not in doc.unprocessed_pages:
                    doc.unprocessed_pages.append(index)
                for el in elements:
                    el.reading_order = order
                    order += 1
                doc.pages.append(p)
                per_page_blocks.append((p, elements))

        self._mark_running_furniture(per_page_blocks)
        self._link_captions(per_page_blocks)
        self._link_continued_tables(per_page_blocks)
        self._classify_references([e for _, els in per_page_blocks for e in els])
        doc.elements = [e for _, els in per_page_blocks for e in els]
        doc.unprocessed_pages = sorted(set(doc.unprocessed_pages))
        doc.document_class = stats.document_class(len(doc.pages))
        doc.confidence = stats.confidence(doc)
        if stats.rtl_digital_segments:
            doc.review_reasons.append("rtl_digital_text_order_unverified")
        if stats.rotated_chars and stats.rotated_chars > 0.05 * max(stats.total_chars, 1):
            doc.warnings.append("rotated or vertical text present; its reading order is approximate")
        if stats.scanned_pages_unread:
            doc.review_reasons.append("ocr_unavailable_for_scanned_pages")
        return doc.finalize()

    # ------------------------------------------------------------------ one page
    def _read_page(self, page, p: Page, stats: "_Stats", ocr_languages: str) -> list[Element]:
        words = page.extract_words(keep_blank_chars=False, use_text_flow=False,
                                   extra_attrs=["size", "fontname", "upright"])
        images = list(page.images or [])
        page_area = max(p.width * p.height, 1.0)
        image_area = sum(max(0.0, (i["x1"] - i["x0"]) * (i["bottom"] - i["top"])) for i in images)
        stats.total_chars += sum(len(w["text"]) for w in words)
        stats.rotated_chars += sum(len(w["text"]) for w in words if not w.get("upright", True))
        stats.garbage_chars += sum(w["text"].count("(cid:") * 5 + w["text"].count("�") for w in words)

        if len(words) < 3 and (image_area / page_area > 0.4 or not words):
            return self._ocr_page(page, p, stats, ocr_languages, images)

        p.text_source = "digital"
        stats.digital_pages += 1
        elements: list[Element] = []

        # tables first: their words must not also appear as paragraphs
        tables = self._tables(page, p, stats)
        table_boxes = [t.bbox for t in tables]
        free = [w for w in words if not any(_inside(w, b) for b in table_boxes)]

        segments = self._segments(free, stats)
        blocks = self._blocks(segments)
        body_size = stats.observe_sizes(blocks)
        ordered = self._reading_order(blocks + [_TableRef(t) for t in tables], p.width, p.height)

        for item in ordered:
            if isinstance(item, _TableRef):
                elements.append(item.element)
            else:
                elements.extend(self._classify_block(item, p, body_size))

        for i, img in enumerate(images):
            elements.append(Element(
                element_type="figure", page=p.number, reading_order=0,
                bbox=_box(img["x0"], img["top"], img["x1"], img["bottom"]),
                block_id=f"p{p.number}-fig{i}", confidence=0.9, method="pdf_image_object",
                attributes={"image_index": i, "name": img.get("name"), "src_size": list(img.get("srcsize") or []),
                            "interpreted": False}))
            stats.figures += 1
        for i, link in enumerate(page.hyperlinks or []):
            uri = link.get("uri")
            if not uri:
                continue
            box = _box(link["x0"], link["top"], link["x1"], link["bottom"])
            anchor = " ".join(w["text"] for w in words if _inside(w, box)) or None
            elements.append(Element(element_type="link", page=p.number, reading_order=0, text=anchor, bbox=box,
                                    block_id=f"p{p.number}-link{i}", confidence=0.95, method="pdf_annotation",
                                    attributes={"href": uri}))
        # figures and links slot into reading order by position, after the text that precedes them
        return _merge_by_position(elements)

    # ------------------------------------------------------------------ scanned page
    def _ocr_page(self, page, p: Page, stats: "_Stats", languages: str, images: list) -> list[Element]:
        elements: list[Element] = []
        for i, img in enumerate(images):
            elements.append(Element(element_type="figure", page=p.number, reading_order=0,
                                    bbox=_box(img["x0"], img["top"], img["x1"], img["bottom"]),
                                    block_id=f"p{p.number}-scan{i}", confidence=0.9, method="pdf_image_object",
                                    attributes={"image_index": i, "role": "page_scan", "interpreted": False}))
        if not tess.tesseract_available():
            p.text_source, p.processed = "none", False
            p.note = "scanned page; tesseract is not installed, so its text was not read"
            stats.scanned_pages_unread += 1
            return elements
        try:
            rendered = page.to_image(resolution=OCR_RESOLUTION).original
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / "page.png"
                rendered.save(target)
                paragraphs = tess.ocr_image_file(target, languages)
        except Exception as exc:
            p.text_source, p.processed = "none", False
            p.note = f"OCR failed: {type(exc).__name__}"[:200]
            stats.scanned_pages_unread += 1
            return elements
        scale = 72.0 / OCR_RESOLUTION
        p.text_source = "ocr"
        stats.ocr_pages += 1
        for i, para in enumerate(paragraphs):
            b = para.bbox
            conf = para.confidence
            stats.ocr_confidences.append(conf if conf is not None else 0.0)
            elements.append(Element(
                element_type="paragraph", page=p.number, reading_order=0, text=para.text,
                bbox=[round(v * scale, 2) for v in b], block_id=f"p{p.number}-ocr{i}", confidence=conf,
                method="ocr", attributes={"ocr_engine": "tesseract", "ocr_version": tess.tesseract_version(),
                                          "ocr_languages": languages},
                lines=[{"text": l.text, "bbox": [round(v * scale, 2) for v in l.bbox], "confidence": l.confidence}
                       for l in para.lines]))
        return elements

    # ------------------------------------------------------------------ words → segments → blocks
    def _segments(self, words: list[dict], stats: "_Stats") -> list[_Seg]:
        rows: list[list[dict]] = []
        for w in sorted(words, key=lambda w: (round(w["top"], 0), w["x0"])):
            size = float(w.get("size") or 10)
            for row in rows:
                ref = row[0]
                if abs(ref["top"] - w["top"]) <= 0.45 * size and ref.get("upright", True) == w.get("upright", True):
                    row.append(w)
                    break
            else:
                rows.append([w])
        segs: list[_Seg] = []
        for row in rows:
            row.sort(key=lambda w: w["x0"])
            current = [row[0]]
            for w in row[1:]:
                size = float(w.get("size") or 10)
                if w["x0"] - current[-1]["x1"] > LINE_GAP_FACTOR * size:
                    segs.append(self._seg(current))
                    current = [w]
                else:
                    current.append(w)
            segs.append(self._seg(current))
        for s in segs:
            if s.rtl:
                stats.rtl_digital_segments += 1
        return segs

    @staticmethod
    def _seg(words: list[dict]) -> _Seg:
        text = " ".join(w["text"] for w in words)
        return _Seg(words=words, x0=min(w["x0"] for w in words), top=min(w["top"] for w in words),
                    x1=max(w["x1"] for w in words), bottom=max(w["bottom"] for w in words),
                    size=statistics.median(float(w.get("size") or 10) for w in words),
                    fonts=sorted({w.get("fontname") or "" for w in words}), rtl=_is_rtl_text(text),
                    upright=all(w.get("upright", True) for w in words))

    @staticmethod
    def _blocks(segs: list[_Seg]) -> list[_Block]:
        blocks: list[_Block] = []
        for s in sorted(segs, key=lambda s: (s.top, s.x0)):
            best = None
            for b in blocks:
                last = max(b.segs, key=lambda x: x.bottom)
                gap = s.top - last.bottom
                overlap = min(b.x1, s.x1) - max(b.x0, s.x0)
                narrow = min(b.x1 - b.x0, s.x1 - s.x0) or 1
                same_size = abs(last.size - s.size) <= max(1.0, 0.12 * last.size)
                if -0.5 * s.size <= gap <= 0.85 * s.size and overlap / narrow > 0.3 and same_size \
                        and last.upright == s.upright:
                    best = b
            if best is None:
                blocks.append(_Block([s]))
            else:
                best.segs.append(s)
        return blocks

    # ------------------------------------------------------------------ reading order
    @staticmethod
    def _reading_order(items: list, page_width: float, page_height: float) -> list:
        """Recursive XY-cut. Items wholly inside the top or bottom margin band (running headers, page
        numbers) are taken out first and read before / after the body, so a page number cannot pose as a
        column. The body is then cut horizontally at whitespace strips that cross the whole region, and
        each band vertically at gutters; columns are read left-to-right, or right-to-left when most of
        the band is RTL text."""
        if not items:
            return []
        top_band = page_height * MARGIN_BAND
        bottom_band = page_height * (1 - MARGIN_BAND)
        head = sorted((i for i in items if i.bottom <= top_band), key=lambda i: (i.top, i.x0))
        foot = sorted((i for i in items if i.top >= bottom_band), key=lambda i: (i.top, i.x0))
        body = [i for i in items if i not in head and i not in foot]
        return head + _xycut(body, horizontal=True) + foot

    # ------------------------------------------------------------------ classification
    def _classify_block(self, b: _Block, p: Page, body_size: float) -> list[Element]:
        text = b.text.strip()
        fonts = sorted({f for s in b.segs for f in s.fonts})
        box = _box(b.x0, b.top, b.x1, b.bottom)
        base = dict(page=p.number, reading_order=0, bbox=box,
                    lines=[{"text": s.text, "bbox": _box(s.x0, s.top, s.x1, s.bottom)}
                           for s in sorted(b.segs, key=lambda s: s.top)])
        attrs: dict = {"font_size": round(b.size, 2), "fonts": fonts, "classified_by": "heuristic"}
        if not all(s.upright for s in b.segs):
            attrs["rotated"] = True
        conf = 0.95
        top_band, bottom_band = p.height * MARGIN_BAND, p.height * (1 - MARGIN_BAND)
        in_margin = b.bottom <= top_band or b.top >= bottom_band

        if in_margin and C.PAGE_NUMBER_RE.match(text):
            return [Element(element_type="page_number", method="digital_text", text=text, confidence=0.9, attributes=attrs, **base)]
        cap = C.caption_label(text)
        if cap:
            attrs.update({"caption_kind": cap[0], "label": cap[1]})
            return [Element(element_type="caption", method="digital_text", text=text, confidence=0.85, attributes=attrs, **base)]
        if C.is_chemical_equation(text) and len(text) < 240:
            attrs["chemical_formulas"] = C.chemical_formulas(text)
            return [Element(element_type="chemical", method="digital_text", text=text, confidence=0.5, attributes=attrs, **base)]
        if C.looks_like_display_equation(text, fonts):
            num = C.EQUATION_NUMBER_RE.search(text)
            if num:
                attrs["equation_number"] = num.group(1)
            attrs.update({"latex": None, "recognised": False})
            return [Element(element_type="equation_display", text=text, confidence=0.35,
                            method="heuristic_equation_candidate", attributes=attrs, **base)]  # noqa: E501
        lines = len(b.segs)
        is_bold = any("bold" in f.lower() for f in fonts)
        if (b.size >= body_size * 1.18 or (is_bold and b.size >= body_size * 0.98 and lines <= 2
                                            and not text.endswith((".", ":", "،")))) \
                and lines <= 3 and len(text) <= 220:
            attrs["size_ratio"] = round(b.size / body_size, 2) if body_size else None
            return [Element(element_type="heading", method="digital_text", text=text.replace("\n", " "), confidence=0.8,
                            attributes=attrs, **base)]
        if b.top >= p.height * 0.78 and b.size < body_size * 0.92 and \
                (text[:1].isdigit() or text[:1] in "*†‡§¹²³⁴⁵⁶⁷⁸⁹"):
            return [Element(element_type="footnote", method="digital_text", text=text, confidence=0.7, attributes=attrs, **base)]
        if C.LIST_RE.match(text):
            items: list[Element] = []
            current: list[_Seg] = []
            for s in sorted(b.segs, key=lambda s: s.top):
                if C.LIST_RE.match(s.text) and current:
                    items.append(self._list_item(current, p, attrs))
                    current = []
                current.append(s)
            if current:
                items.append(self._list_item(current, p, attrs))
            return items
        formulas = C.chemical_formulas(text)
        if formulas:
            attrs["chemical_formulas"] = formulas
        if C.math_symbol_ratio(text) >= 0.04 and any(any(h in f.lower() for h in C.MATH_FONT_HINTS) for f in fonts):
            attrs["contains_inline_math"] = True
        return [Element(element_type="paragraph", method="digital_text", text=text, confidence=conf, attributes=attrs, **base)]

    @staticmethod
    def _list_item(segs: list[_Seg], p: Page, attrs: dict) -> Element:
        text = " ".join(s.text for s in segs)
        indent = min(s.x0 for s in segs)
        return Element(element_type="list_item", page=p.number, reading_order=0, text=text,
                       bbox=_box(min(s.x0 for s in segs), min(s.top for s in segs),
                                 max(s.x1 for s in segs), max(s.bottom for s in segs)),
                       confidence=0.85, method="digital_text",
                       attributes={**attrs, "marker": C.LIST_RE.match(text).group(1), "indent": round(indent, 1)})

    # ------------------------------------------------------------------ tables
    def _tables(self, page, p: Page, stats: "_Stats") -> list["_Table"]:
        found = []
        try:
            ruled = page.find_tables()
        except Exception:
            ruled = []
        strategy, base_conf = "lines", 0.9
        candidates = list(ruled)
        if not candidates:
            try:
                candidates = page.find_tables({"vertical_strategy": "text", "horizontal_strategy": "text"})
            except Exception:
                candidates = []
            strategy, base_conf = "text", 0.6
        for i, t in enumerate(candidates):
            try:
                raw = t.extract()
            except Exception:
                continue
            # blank spacer rows (the text strategy emits them between real rows) are dropped here, with
            # their geometry, so row counts describe the table rather than the whitespace in it
            geometry = list(getattr(t, "rows", []) or [])
            kept = [i for i, r in enumerate(raw) if any((c or "").strip() for c in r)]
            rows = [raw[i] for i in kept]
            t = _RowView(t, [geometry[i] for i in kept if i < len(geometry)])
            raw = rows
            if len(rows) < 2 or max((len(r) for r in rows), default=0) < 2:
                continue          # a "table" of one row or one column is a paragraph mis-detected
            if strategy == "text" and not _plausible_unruled_table(rows):
                continue
            cells, spans = _cells(t, raw)
            conf = base_conf * (0.9 if spans else 1.0)
            stats.table_confidences.append(conf)
            n_cols = max(len(r) for r in raw)
            text = "\n".join("\t".join((c or "").strip() for c in r) for r in rows)
            el = Element(element_type="table", page=p.number, reading_order=0, text=text,
                         bbox=_box(*t.bbox), block_id=f"p{p.number}-t{i}", confidence=conf,
                         method=f"pdf_table:{strategy}",
                         attributes={"strategy": strategy, "n_rows": len(raw), "n_cols": n_cols,
                                     "header_rows": 1, "header_rows_inferred": True, "cells": cells,
                                     "spans_inferred": spans,
                                     "rows": [[(c or "").strip() if c is not None else None for c in r] for r in raw]})
            found.append(_Table(el))
        return found

    # ------------------------------------------------------------------ document-level passes
    @staticmethod
    def _mark_running_furniture(pages: list[tuple[Page, list[Element]]]) -> None:
        """A block repeated in the same margin on at least half the pages is a running header/footer —
        kept, typed as such, and excluded from body text, never deleted (§13)."""
        if len(pages) < 2:
            return
        seen: dict[tuple[str, str], set[int]] = {}
        for p, els in pages:
            for e in els:
                if e.bbox is None or e.element_type not in ("paragraph", "heading", "page_number"):
                    continue
                zone = "top" if e.bbox[3] <= (p.height or 0) * MARGIN_BAND else \
                       "bottom" if e.bbox[1] >= (p.height or 0) * (1 - MARGIN_BAND) else None
                if zone:
                    seen.setdefault((zone, C.strip_digits(e.text)), set()).add(p.number)
        threshold = max(2, len(pages) // 2)
        repeated = {k for k, v in seen.items() if len(v) >= threshold}
        for p, els in pages:
            for e in els:
                if e.bbox is None or e.element_type not in ("paragraph", "heading"):
                    continue
                for zone in ("top", "bottom"):
                    if (zone, C.strip_digits(e.text)) in repeated:
                        e.element_type = "header" if zone == "top" else "footer"
                        e.attributes["detected_by"] = "repetition_across_pages"

    @staticmethod
    def _link_captions(pages: list[tuple[Page, list[Element]]]) -> None:
        for p, els in pages:
            targets = [e for e in els if e.element_type in ("figure", "table") and e.bbox]
            for cap in (e for e in els if e.element_type == "caption" and e.bbox):
                kind = cap.attributes.get("caption_kind")
                pool = [t for t in targets if t.element_type == kind] or targets
                if not pool:
                    cap.attributes["associated"] = False
                    continue
                def distance(t):
                    if cap.bbox[1] >= t.bbox[3]:
                        return cap.bbox[1] - t.bbox[3]
                    if t.bbox[1] >= cap.bbox[3]:
                        return t.bbox[1] - cap.bbox[3]
                    return 0.0
                best = min(pool, key=distance)
                cap.parent_block_id = best.block_id
                cap.attributes["associated"] = True
                cap.attributes["association_distance_pt"] = round(distance(best), 1)
                best.attributes["caption_block_id"] = cap.block_id
                best.attributes["caption"] = cap.text

    @staticmethod
    def _link_continued_tables(pages: list[tuple[Page, list[Element]]]) -> None:
        """§8.3 — a table at the foot of one page and one at the head of the next with the same number of
        columns are linked as a continuation. Linked, not merged: the original tables stay as read."""
        for (p1, a), (p2, b) in zip(pages, pages[1:]):
            last = [e for e in a if e.element_type == "table"]
            first = [e for e in b if e.element_type == "table"]
            if not last or not first:
                continue
            t1 = max(last, key=lambda e: e.bbox[3])
            t2 = min(first, key=lambda e: e.bbox[1])
            if t1.attributes.get("n_cols") != t2.attributes.get("n_cols"):
                continue
            if t1.bbox[3] < (p1.height or 0) * 0.6 or t2.bbox[1] > (p2.height or 0) * 0.4:
                continue
            t1.attributes["continued_on"] = t2.block_id
            t2.attributes["continues_from"] = t1.block_id
            t2.attributes["continuation_inferred"] = True

    @staticmethod
    def _classify_references(elements: list[Element]) -> None:
        in_refs = False
        for e in elements:
            if e.element_type == "heading":
                in_refs = bool(C.REFERENCES_HEADING_RE.match(e.text or ""))
                continue
            if in_refs and e.element_type in ("paragraph", "list_item"):
                e.attributes["references"] = C.split_references(e.text or "")
                e.element_type = "reference"


# ---------------------------------------------------------------------- helpers
@dataclass
class _Table:
    element: Element

    @property
    def bbox(self):
        return self.element.bbox


class _RowView:
    """A pdfplumber table seen through a subset of its rows (bbox unchanged)."""
    def __init__(self, table, rows) -> None:
        self.bbox = table.bbox
        self.rows = rows


class _TableRef:
    def __init__(self, t: _Table) -> None:
        self.element = t.element
        self.x0, self.top, self.x1, self.bottom = t.bbox


class _Stats:
    def __init__(self) -> None:
        self.total_chars = 0
        self.rotated_chars = 0
        self.garbage_chars = 0
        self.digital_pages = 0
        self.ocr_pages = 0
        self.scanned_pages_unread = 0
        self.rtl_digital_segments = 0
        self.ocr_confidences: list[float] = []
        self.table_confidences: list[float] = []
        self.figures = 0
        self.sizes: list[float] = []
        self.equations = 0

    def observe_sizes(self, blocks: list[_Block]) -> float:
        for b in blocks:
            self.sizes.extend([b.size] * max(1, len(b.text)))
        return statistics.median(self.sizes) if self.sizes else 10.0

    def document_class(self, pages: int) -> str:
        if not pages:
            return "unknown"
        if self.digital_pages and (self.ocr_pages or self.scanned_pages_unread):
            return "hybrid"
        if self.digital_pages:
            return "digital"
        return "scanned"

    def confidence(self, doc: CanonicalDocument) -> Confidence:
        text = None
        if self.digital_pages or self.ocr_confidences:
            digital = max(0.0, 0.97 - 2.0 * self.garbage_chars / max(self.total_chars, 1)) if self.digital_pages else None
            ocr = sum(self.ocr_confidences) / len(self.ocr_confidences) if self.ocr_confidences else None
            parts = [(digital, self.digital_pages), (ocr, self.ocr_pages)]
            weight = sum(n for v, n in parts if v is not None)
            text = round(sum(v * n for v, n in parts if v is not None) / weight, 3) if weight else None
        layout = None
        if text is not None:
            layout = 0.9
            if any(e.attributes.get("rotated") for e in doc.elements):
                layout -= 0.2
            if self.rtl_digital_segments:
                layout -= 0.15
        equations = [e for e in doc.elements if e.element_type == "equation_display"]
        return Confidence(
            text=text, layout=round(layout, 3) if layout is not None else None,
            table=round(sum(self.table_confidences) / len(self.table_confidences), 3) if self.table_confidences else None,
            equation=0.35 if equations else None,
            figure=0.9 if self.figures else None)


def _plausible_unruled_table(rows: list[list]) -> bool:
    """The text strategy turns any whitespace-aligned prose (two columns of a paper, say) into a grid.
    Without ruling lines, accept a grid only if it looks like data: short cells, mostly filled, and at
    least one column that is mostly numeric. Prose fails all three; a rejected candidate's words stay in
    the text flow, so nothing is lost by refusing."""
    cells = [(c or "").strip() for r in rows for c in r]
    filled = [c for c in cells if c]
    if not cells or len(filled) < 0.6 * len(cells):
        return False
    if sum(len(c) for c in filled) / len(filled) > 30:
        return False
    n_cols = max(len(r) for r in rows)
    numeric = re.compile(r"^[<>≈~±+-]?\d[\d.,]*\s*%?$")
    for c in range(n_cols):
        column = [(r[c] or "").strip() for r in rows[1:] if c < len(r) and (r[c] or "").strip()]
        if column and sum(1 for v in column if numeric.match(v)) >= 0.7 * len(column):
            return True
    return False


def _box(x0, top, x1, bottom) -> list[float]:
    return [round(float(x0), 2), round(float(top), 2), round(float(x1), 2), round(float(bottom), 2)]


def _inside(word: dict, box: list[float]) -> bool:
    cx = (word["x0"] + word["x1"]) / 2
    cy = (word["top"] + word["bottom"]) / 2
    return box[0] - 1 <= cx <= box[2] + 1 and box[1] - 1 <= cy <= box[3] + 1


MIN_H_GAP = 12.0     # pt of horizontal whitespace that separates bands (larger than a paragraph break)
MIN_V_GAP = 8.0      # pt of vertical whitespace that separates columns


def _groups(spans: list[tuple[float, float, object]], min_gap: float) -> list[list]:
    """Split items by gaps in a 1-D projection. Returns groups in ascending coordinate order."""
    groups: list[list] = []
    end = None
    for lo, hi, it in sorted(spans, key=lambda s: s[0]):
        if end is not None and lo - end >= min_gap:
            groups.append([])
        if not groups:
            groups.append([])
        groups[-1].append(it)
        end = hi if end is None else max(end, hi)
    return groups


def _xycut(items: list, *, horizontal: bool, depth: int = 0) -> list:
    if len(items) <= 1 or depth > 12:
        return sorted(items, key=lambda i: (i.top, i.x0))
    if horizontal:
        parts = _groups([(i.top, i.bottom, i) for i in items], MIN_H_GAP)
    else:
        parts = _groups([(i.x0, i.x1, i) for i in items], MIN_V_GAP)
        rtl = sum(1 for i in items if isinstance(i, _Block) and i.rtl)
        if rtl * 2 > len(items):
            parts.reverse()
    if len(parts) == 1:
        other = _groups([(i.x0, i.x1, i) for i in items], MIN_V_GAP) if horizontal else \
                _groups([(i.top, i.bottom, i) for i in items], MIN_H_GAP)
        if len(other) == 1:
            return sorted(items, key=lambda i: (i.top, i.x0))
        return _xycut(items, horizontal=not horizontal, depth=depth + 1)
    out: list = []
    for part in parts:
        out.extend(_xycut(part, horizontal=not horizontal, depth=depth + 1))
    return out


def _cells(table, raw: list[list]) -> tuple[list[dict], bool]:
    """Cells with geometry; a `None` that pdfplumber leaves where a merged cell continues becomes a span
    on the cell it belongs to. Spans are marked inferred because the PDF does not state them."""
    cells: list[dict] = []
    spans = False
    by_pos: dict[tuple[int, int], dict] = {}
    rows = getattr(table, "rows", []) or []
    for r, row in enumerate(raw):
        geom = rows[r].cells if r < len(rows) else []
        for c, value in enumerate(row):
            if value is None:
                left = by_pos.get((r, c - 1))
                above = by_pos.get((r - 1, c))
                if left is not None:
                    left["colspan"] += 1
                    by_pos[(r, c)] = left
                    spans = True
                elif above is not None:
                    above["rowspan"] += 1
                    by_pos[(r, c)] = above
                    spans = True
                continue
            box = geom[c] if c < len(geom) and geom[c] is not None else None
            cell = {"row": r, "col": c, "text": value.strip(), "rowspan": 1, "colspan": 1,
                    "bbox": _box(*box) if box else None}
            cells.append(cell)
            by_pos[(r, c)] = cell
    return cells, spans


def _merge_by_position(elements: list[Element]) -> list[Element]:
    """Text blocks are already in reading order. Figures and links are placed after the last text block
    that starts above them, so 'read the page in order' includes them where they sit."""
    text = [e for e in elements if e.element_type not in ("figure", "link")]
    extra = [e for e in elements if e.element_type in ("figure", "link")]
    for e in sorted(extra, key=lambda e: (e.bbox[1] if e.bbox else 0)):
        pos = 0
        for i, t in enumerate(text):
            if t.bbox and e.bbox and t.bbox[1] <= e.bbox[1]:
                pos = i + 1
        text.insert(pos, e)
    return text
