"""
MathpixProvider — Mathpix's PDF API normalised into the CDR (prompt v4.0 §4, §11; ADR-122).

Mathpix is a *benchmark and an optional provider*, never the architecture: nothing outside this file
knows its API exists, and the system runs fully without it.

WHAT IS FACT AND WHAT IS NOT (classified per §3, researched 2026-10-14 at docs.mathpix.com)

FACT (documented in the v3/pdf reference):
  * `POST {base}/v3/pdf` creates a job and returns `pdf_id`; auth headers are `app_id` and `app_key`.
  * Options used here exist and have these defaults: `math_inline_delimiters` ["\\(","\\)"],
    `math_display_delimiters` ["\\[","\\]"], `rm_spaces` true, `include_page_info`, `include_hyperlinks`.
  * `GET {base}/v3/pdf/{pdf_id}` → `status` in received | loaded | split | completed | error, and the docs
    say to poll `status`, not `percent_done` (which can reach 100 while status is still `split`).
  * `GET {base}/v3/pdf/{pdf_id}.{ext}` downloads a result; `.mmd` and `.lines.json` are documented
    extensions. A 404 whose body has a non-completed status means "not ready yet".
SIGNAL (widely shown in Mathpix examples, not re-verified here):
  * a local file is sent as multipart `file` with the options as a JSON string in `options_json`.
HYPOTHESIS (the published reference reached on 2026-10-14 did not document it):
  * the field-level schema of `lines.json`. The SDK documents `cnt`, `confidence_rate`, `is_printed`
    and `is_handwritten` for image line data; the parser below accepts those and the obvious
    alternatives, keeps every field it does not understand under `attributes.provider_raw`, and never
    fails a document because a field is missing. It is exercised only against a mock transport here.

Every claim of accuracy is Mathpix's own; nothing here asserts that it is better than the local
provider. That is what `benchmark.py` is for.

PRIVACY: this provider sends the document to Mathpix's servers (`runs_locally=False`). It is only tried
when both credentials are configured.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

from app.core.config import settings
from app.ingestion.cdr import CanonicalDocument, Confidence, Element, Page
from app.ingestion.providers.base import (
    Availability, DocumentExtractionProvider, ProviderCapabilities, ProviderFailed, ProviderUnavailable,
)

TERMINAL = ("completed", "error")
_INLINE_MATH = re.compile(r"\\\((.+?)\\\)")

# Mathpix line `type` → CDR element type. Unknown types become `unclassified` with the original kept.
TYPE_MAP = {
    "text": "paragraph", "paragraph": "paragraph", "title": "title", "section_header": "heading",
    "header": "header", "footer": "footer", "page_info": "page_number", "math": "equation_display",
    "equation_number": "equation_display", "table": "table", "figure": "figure", "diagram": "figure",
    "chart": "figure", "figure_label": "caption", "caption": "caption", "footnote": "footnote",
    "code": "code", "pseudocode": "code", "chemistry": "chemical", "smiles": "chemical",
    "column": "unclassified", "page_break": "page_break",
}


class MathpixProvider(DocumentExtractionProvider):
    name = "mathpix"
    capabilities = ProviderCapabilities(
        formats=(".pdf", ".png", ".jpg", ".jpeg"), geometry=True, reading_order=True, tables=True,
        equations_latex=True, equation_detection=True, chemistry=True, figures=True, ocr=True,
        handwriting=True, languages=("as documented by Mathpix",), runs_locally=False,
        notes=("documents leave this deployment", "lines.json schema parsed defensively (HYPOTHESIS)"))

    def __init__(self, *, transport: httpx.BaseTransport | None = None, app_id: str | None = None,
                 app_key: str | None = None, base_url: str | None = None, poll_interval: float = 2.0,
                 poll_timeout: float | None = None, sleep=time.sleep) -> None:
        self._transport = transport
        self._app_id = app_id
        self._app_key = app_key
        self._base = (base_url or settings.MATHPIX_API_BASE_URL).rstrip("/")
        self._interval = poll_interval
        self._timeout = poll_timeout or float(settings.MATHPIX_POLL_TIMEOUT_SECONDS)
        self._sleep = sleep

    @property
    def version(self) -> str:
        return "mathpix-v3-pdf"

    def _credentials(self) -> tuple[str | None, str | None]:
        key = self._app_key
        if key is None and settings.MATHPIX_APP_KEY is not None:
            key = settings.MATHPIX_APP_KEY.get_secret_value()
        return self._app_id or settings.MATHPIX_APP_ID, key

    def availability(self) -> Availability:
        app_id, key = self._credentials()
        if not app_id or not key:
            return Availability(False, "MATHPIX_APP_ID / MATHPIX_APP_KEY are not configured")
        return Availability(True)

    # ------------------------------------------------------------------ HTTP
    def _client(self) -> httpx.Client:
        app_id, key = self._credentials()
        return httpx.Client(base_url=self._base, transport=self._transport, timeout=60.0,
                            headers={"app_id": app_id or "", "app_key": key or ""})

    @staticmethod
    def _raise_for(resp: httpx.Response, what: str) -> None:
        if resp.status_code < 400:
            return
        retryable = resp.status_code in (429, 500, 502, 503, 504)
        # the body is not echoed: it may quote the request, and the request carries the document
        raise ProviderFailed(f"Mathpix {what} returned HTTP {resp.status_code}", retryable=retryable)

    def extract(self, path: Path, *, options: dict | None = None) -> CanonicalDocument:
        if not self.availability().available:
            raise ProviderUnavailable(self.availability().reason)
        request_options = {"math_inline_delimiters": ["\\(", "\\)"], "math_display_delimiters": ["\\[", "\\]"],
                           "rm_spaces": True, "include_page_info": True, "include_hyperlinks": True}
        try:
            with self._client() as client:
                with path.open("rb") as fh:
                    resp = client.post("/v3/pdf", files={"file": (path.name, fh)},
                                       data={"options_json": json.dumps(request_options)})
                self._raise_for(resp, "submission")
                body = resp.json()
                if body.get("error") or not body.get("pdf_id"):
                    raise ProviderFailed(f"Mathpix refused the document: {str(body.get('error'))[:200]}")
                pdf_id = str(body["pdf_id"])
                status = self._poll(client, pdf_id)
                if status.get("status") == "error":
                    raise ProviderFailed(f"Mathpix processing error: {str(status.get('error'))[:200]}")
                lines = client.get(f"/v3/pdf/{pdf_id}.lines.json")
                self._raise_for(lines, "lines.json download")
                mmd = client.get(f"/v3/pdf/{pdf_id}.mmd")
                mmd_text = mmd.text if mmd.status_code < 400 else None
        except httpx.TimeoutException as exc:
            raise ProviderFailed("Mathpix timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderFailed(f"Mathpix transport error: {type(exc).__name__}", retryable=True) from exc
        try:
            payload = lines.json()
        except ValueError as exc:
            raise ProviderFailed("Mathpix lines.json was not JSON") from exc
        doc = normalize_lines_json(payload, provider_version=self.version)
        doc.config = {"request_options": request_options, "pdf_id": pdf_id,
                      "num_pages": status.get("num_pages")}
        if mmd_text is not None:
            doc.raw_outputs["mmd"] = mmd_text      # kept verbatim as a candidate output (§12)
        return doc

    def _poll(self, client: httpx.Client, pdf_id: str) -> dict:
        deadline = time.monotonic() + self._timeout
        while True:
            resp = client.get(f"/v3/pdf/{pdf_id}")
            self._raise_for(resp, "status")
            status = resp.json()
            if status.get("status") in TERMINAL:
                return status
            if time.monotonic() > deadline:
                raise ProviderFailed(f"Mathpix did not finish within {int(self._timeout)}s "
                                     f"(last status {status.get('status')!r})", retryable=True)
            self._sleep(self._interval)


# ---------------------------------------------------------------------- normalisation
def _bbox(line: dict) -> list[float] | None:
    region = line.get("region")
    if isinstance(region, dict) and {"top_left_x", "top_left_y", "width", "height"} <= set(region):
        x, y = float(region["top_left_x"]), float(region["top_left_y"])
        return [x, y, x + float(region["width"]), y + float(region["height"])]
    cnt = line.get("cnt")
    if isinstance(cnt, list) and cnt and all(isinstance(p, (list, tuple)) and len(p) >= 2 for p in cnt):
        xs = [float(p[0]) for p in cnt]
        ys = [float(p[1]) for p in cnt]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


def _confidence(line: dict) -> float | None:
    for key in ("confidence", "confidence_rate"):
        value = line.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def normalize_lines_json(payload: dict, *, provider_version: str = "mathpix-v3-pdf") -> CanonicalDocument:
    """Pure function: lines.json → CDR. Unknown fields are preserved, never discarded."""
    doc = CanonicalDocument(provider="mathpix", provider_version=provider_version)
    pages = payload.get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, list):
        doc.review_reasons.append("provider_output_unrecognised")
        doc.warnings.append("lines.json had no `pages` list; nothing could be normalised")
        return doc.finalize()
    order = 0
    known = {"type", "subtype", "text", "text_display", "cnt", "region", "confidence", "confidence_rate",
             "id", "parent_id", "children_ids", "is_handwritten", "is_printed", "conversion_output", "line",
             "column", "font_size"}
    confs: dict[str, list[float]] = {"text": [], "table": [], "equation": [], "figure": []}
    handwritten = 0
    for index, page in enumerate(pages, start=1):
        number = int(page.get("page", index)) if isinstance(page, dict) else index
        doc.pages.append(Page(number=number, width=page.get("page_width"), height=page.get("page_height"),
                              text_source="provider"))
        for line in (page.get("lines") or []):
            if not isinstance(line, dict):
                continue
            kind = str(line.get("type") or "text").lower()
            etype = TYPE_MAP.get(kind, kind)
            text = line.get("text") if isinstance(line.get("text"), str) else None
            conf = _confidence(line)
            attrs: dict = {"provider_type": kind, "subtype": line.get("subtype"), "column": line.get("column"),
                           "is_handwritten": line.get("is_handwritten"), "is_printed": line.get("is_printed")}
            if line.get("is_handwritten"):
                handwritten += 1
            if etype == "equation_display" and text:
                latex = text.strip()
                if latex.startswith("\\[") and latex.endswith("\\]"):
                    latex = latex[2:-2].strip()
                attrs.update({"latex": latex, "recognised": True})
                m = re.search(r"\\tag\{([^}]*)\}", latex)
                if m:
                    attrs["equation_number"] = m.group(1)
                confs["equation"].append(conf if conf is not None else 0.0)
            elif etype == "table":
                attrs.update({"strategy": "mathpix", "source_markup": text})
                confs["table"].append(conf if conf is not None else 0.0)
            elif etype == "figure":
                attrs["interpreted"] = False
                confs["figure"].append(conf if conf is not None else 0.0)
            else:
                if text:
                    inline = _INLINE_MATH.findall(text)
                    if inline:
                        attrs["inline_math"] = inline
                if conf is not None:
                    confs["text"].append(conf)
            extra = {k: v for k, v in line.items() if k not in known}
            if extra:
                attrs["provider_raw"] = extra
            el = Element(element_type=etype, page=number, reading_order=order, text=text, bbox=_bbox(line),
                         block_id=str(line.get("id") or f"p{number}-l{order}"),
                         parent_block_id=str(line["parent_id"]) if line.get("parent_id") else None,
                         confidence=conf, method="provider:mathpix",
                         attributes={k: v for k, v in attrs.items() if v is not None})
            doc.elements.append(el)
            order += 1

    def mean(v: list[float]) -> float | None:
        return round(sum(v) / len(v), 3) if v else None

    doc.document_class = "unknown"
    doc.page_count = len(doc.pages)
    doc.confidence = Confidence(text=mean(confs["text"]), layout=None, table=mean(confs["table"]),
                                equation=mean(confs["equation"]), figure=mean(confs["figure"]))
    if handwritten:
        doc.warnings.append(f"{handwritten} handwritten line(s); recognition of handwriting is less certain")
    if not doc.elements:
        doc.review_reasons.append("no_text_extracted")
    return doc.finalize()
