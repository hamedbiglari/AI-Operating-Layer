"""
MarkItDownProvider — non-PDF formats into the CDR (ADR-065 converter, ADR-122 representation).

DOCX, PPTX, XLSX, HTML, EPUB, CSV, JSON, TXT and MD have no page geometry to recover, but they do have
structure, and MarkItDown measurably preserves it for these formats (headings, lists, DOCX/XLSX tables).
Its Markdown is parsed ONCE, here, into elements; from then on the document is a CDR like any other and
every output is rendered from that, not from MarkItDown's string.

Geometry is `None` and pages are `None` — the formats are not paginated, and inventing a page 1 would
give every claim a location that does not exist (§9). Layout confidence is therefore *not measured*.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.ingestion.cdr import CanonicalDocument, Confidence, Element
from app.ingestion.converter import ConversionStatus, MarkItDownConverter
from app.ingestion.providers import classify as C
from app.ingestion.providers.base import (
    Availability, DocumentExtractionProvider, ProviderCapabilities, ProviderFailed,
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_FENCE = re.compile(r"^\s*```")
_DISPLAY_MATH = re.compile(r"^\s*(\$\$|\\\[)(.*?)(\$\$|\\\])\s*$", re.S)


def _split_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", inner)]


def parse_markdown(markdown: str, *, method: str) -> list[Element]:
    """Markdown → elements, in source order. Anything not recognised becomes a paragraph — never dropped."""
    lines = markdown.splitlines()
    out: list[Element] = []
    i = 0
    para: list[str] = []

    def flush():
        if para:
            text = "\n".join(para).strip()
            if text:
                out.append(_paragraph(text, method))
            para.clear()

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            flush()
            i += 1
            continue
        if _FENCE.match(line):
            flush()
            j = i + 1
            while j < len(lines) and not _FENCE.match(lines[j]):
                j += 1
            out.append(Element(element_type="code", page=None, reading_order=0,
                               text="\n".join(lines[i + 1:j]), confidence=0.9, method=method,
                               attributes={"fence": line.strip()[3:] or None}))
            i = j + 1
            continue
        m = _HEADING.match(line)
        if m:
            flush()
            out.append(Element(element_type="heading", page=None, reading_order=0, text=m.group(2).strip(),
                               level=len(m.group(1)), confidence=0.9, method=method))
            i += 1
            continue
        if _TABLE_ROW.match(line) and i + 1 < len(lines) and _TABLE_SEP.match(lines[i + 1]):
            flush()
            header = _split_row(line)
            rows = [header]
            j = i + 2
            while j < len(lines) and _TABLE_ROW.match(lines[j]):
                rows.append(_split_row(lines[j]))
                j += 1
            cells = [{"row": r, "col": c, "text": v, "rowspan": 1, "colspan": 1, "bbox": None}
                     for r, row in enumerate(rows) for c, v in enumerate(row)]
            out.append(Element(element_type="table", page=None, reading_order=0,
                               text="\n".join("\t".join(r) for r in rows), confidence=0.85, method=method,
                               attributes={"strategy": "markdown", "n_rows": len(rows),
                                           "n_cols": max(len(r) for r in rows), "header_rows": 1,
                                           "header_rows_inferred": False, "cells": cells, "rows": rows,
                                           "spans_inferred": False}))
            i = j
            continue
        if C.LIST_RE.match(line):
            flush()
            out.append(Element(element_type="list_item", page=None, reading_order=0, text=line.strip(),
                               level=(len(line) - len(line.lstrip())) // 2 + 1, confidence=0.9, method=method,
                               attributes={"marker": C.LIST_RE.match(line).group(1)}))
            i += 1
            continue
        para.append(line)
        i += 1
    flush()
    for n, el in enumerate(out):
        el.reading_order = n
        el.block_id = f"b{n}"
    return out


def _paragraph(text: str, method: str) -> Element:
    m = _DISPLAY_MATH.match(text)
    if m:
        return Element(element_type="equation_display", page=None, reading_order=0, text=m.group(2).strip(),
                       confidence=0.8, method=method, attributes={"latex": m.group(2).strip(), "recognised": True})
    attrs: dict = {}
    if C.is_chemical_equation(text):
        return Element(element_type="chemical", page=None, reading_order=0, text=text, confidence=0.5,
                       method=method, attributes={"chemical_formulas": C.chemical_formulas(text)})
    formulas = C.chemical_formulas(text)
    if formulas:
        attrs["chemical_formulas"] = formulas
    if C.caption_label(text):
        kind, label = C.caption_label(text)
        return Element(element_type="caption", page=None, reading_order=0, text=text, confidence=0.8,
                       method=method, attributes={"caption_kind": kind, "label": label})
    return Element(element_type="paragraph", page=None, reading_order=0, text=text, confidence=0.9,
                   method=method, attributes=attrs)


class MarkItDownProvider(DocumentExtractionProvider):
    name = "markitdown"
    capabilities = ProviderCapabilities(
        formats=(".docx", ".pptx", ".xlsx", ".xls", ".csv", ".json", ".xml", ".html", ".htm", ".txt", ".md",
                 ".epub"),
        tables=True, reading_order=True, runs_locally=True,
        notes=("no page geometry for non-paginated formats", "PDF tables and images are NOT recovered by it"))

    def __init__(self) -> None:
        self._converter = MarkItDownConverter()

    @property
    def version(self) -> str:
        return f"markitdown-{self._converter.version}"

    def availability(self) -> Availability:
        try:
            import markitdown  # noqa: F401
        except ImportError:
            return Availability(False, "markitdown is not installed")
        return Availability(True)

    def extract(self, path: Path, *, options: dict | None = None) -> CanonicalDocument:
        result = self._converter.convert(path)
        if result.status in (ConversionStatus.FAILED, ConversionStatus.UNSUPPORTED):
            raise ProviderFailed(result.error or "conversion failed", retryable=False)
        doc = CanonicalDocument(provider=self.name, provider_version=self.version, document_class="not_paginated",
                                config={"enable_plugins": False})
        if result.status == ConversionStatus.EMPTY:
            doc.warnings.append(result.error or "no usable text")
            doc.review_reasons.append("no_text_extracted")
            return doc.finalize()
        doc.elements = parse_markdown(result.markdown or "", method="markitdown")
        tables = [e for e in doc.elements if e.element_type == "table"]
        doc.confidence = Confidence(text=0.9 if doc.elements else None, layout=None,
                                    table=0.85 if tables else None,
                                    equation=0.8 if any(e.element_type == "equation_display" for e in doc.elements) else None)
        return doc.finalize()
