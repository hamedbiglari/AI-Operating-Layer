"""
Renderers: CDR → Markdown · MMD · HTML · LaTeX · JSON (prompt v4.0 §7, ADR-122).

Every output is a pure function of the canonical representation. None of them is parsed back, and none
re-reads the original file, so all formats agree about what the document says — a table is the same
table in Markdown and in HTML because both are drawn from the same cells.

Two rendering rules matter for honesty:

* **Nothing is silently left out.** Running headers, footers and page numbers are omitted from the
  *body* of a rendering (a reader does not want "Journal of X — Vol 3" between every paragraph), but
  the rendering says how many were omitted and that they remain in the canonical representation.
* **An unrecognised equation is not dressed up as mathematics.** A heuristic candidate is rendered as
  the text as printed, labelled as such; only a provider-recognised equation is emitted as LaTeX.

DOCX and PDF are listed in §7. They are *not* produced here: no DOCX or PDF writer is a dependency of
this project, and a fake file would be worse than a clear refusal. `render()` raises
`UnsupportedFormat` with the reason; the API answers 501.
"""
from __future__ import annotations

import html
import json

from app.ingestion.cdr import CanonicalDocument, Element

FORMATS = ("markdown", "mmd", "html", "latex", "json")
UNAVAILABLE_FORMATS = {
    "docx": "no DOCX writer is installed in Cloud Core (python-docx is not a dependency)",
    "pdf": "no PDF writer is installed in Cloud Core",
}
FURNITURE = ("header", "footer", "page_number", "page_break")


class UnsupportedFormat(ValueError):
    pass


def _body(doc: CanonicalDocument) -> tuple[list[Element], int]:
    body = [e for e in doc.elements if e.element_type not in FURNITURE and e.element_type != "link"]
    return body, sum(1 for e in doc.elements if e.element_type in FURNITURE)


def _captions(doc: CanonicalDocument) -> dict[str, Element]:
    return {e.parent_block_id: e for e in doc.elements if e.element_type == "caption" and e.parent_block_id}


def _rows(e: Element) -> list[list[str]]:
    rows = e.attributes.get("rows")
    if rows:
        return [[("" if c is None else str(c)) for c in r] for r in rows]
    return [line.split("\t") for line in (e.text or "").splitlines()]


def _md_table(e: Element) -> str:
    rows = _rows(e)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    esc = lambda c: c.replace("|", "\\|").replace("\n", " ").strip()  # noqa: E731
    out = ["| " + " | ".join(esc(c) for c in rows[0]) + " |", "| " + " | ".join("---" for _ in rows[0]) + " |"]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows[1:]]
    if e.attributes.get("spans_inferred"):
        out.append("\n*Merged cells are flattened in Markdown; the HTML and JSON renderings keep the spans.*")
    return "\n".join(out)


def _where(e: Element) -> str:
    return f"page {e.page}" if e.page else "no page"


def to_markdown(doc: CanonicalDocument, *, mmd: bool = False) -> str:
    body, omitted = _body(doc)
    captions = _captions(doc)
    parts: list[str] = []
    for e in body:
        t = (e.normalized_text or e.text or "").strip()
        k = e.element_type
        if k == "caption" and e.parent_block_id and e.parent_block_id in {b.block_id for b in body}:
            continue                       # rendered with the table/figure it belongs to
        if k == "title":
            parts.append(f"# {t}")
        elif k == "heading":
            parts.append(f"{'#' * min(6, (e.level or 1) + 1)} {t}")
        elif k == "list_item":
            parts.append(t if t[:1] in "-*•" or t[:1].isdigit() else f"- {t}")
        elif k == "table":
            cap = captions.get(e.block_id)
            if cap:
                parts.append(f"**{cap.text.strip()}**")
            parts.append(_md_table(e))
        elif k == "figure":
            cap = captions.get(e.block_id)
            label = cap.text.strip() if cap else f"Figure ({_where(e)})"
            parts.append(f"![{label}](#{e.block_id})")
            ocr = e.attributes.get("ocr_text")
            if ocr:
                parts.append(f"*[Image OCR — {_where(e)}, engine {e.attributes.get('ocr_engine')}]*\n\n{ocr}\n\n*[End OCR]*")
            elif not e.attributes.get("interpreted"):
                parts.append(f"*Figure present ({_where(e)}); not interpreted — no claim is made about its content.*")
        elif k == "equation_display":
            latex = e.attributes.get("latex")
            num = e.attributes.get("equation_number")
            if latex and e.attributes.get("recognised"):
                body_tex = latex + (f" \\tag{{{num}}}" if num and "\\tag" not in latex else "")
                parts.append(f"\\[\n{body_tex}\n\\]" if mmd else f"$$\n{body_tex}\n$$")
            else:
                parts.append(f"> *Equation (not recognised — text as printed{', no. ' + num if num else ''}):* `{t}`")
        elif k == "chemical":
            parts.append(f"`{t}`" if not mmd else f"<smiles>{e.attributes['smiles']}</smiles>"
                         if e.attributes.get("smiles") else f"`{t}`")
        elif k == "code":
            parts.append(f"```\n{e.text or ''}\n```")
        elif k == "reference":
            refs = e.attributes.get("references") or [t]
            parts.extend(refs)
        elif k == "footnote":
            parts.append(f"<small>{t}</small>" if mmd else f"> {t}")
        elif k == "transcript_segment":
            a, b = e.attributes.get("start_ms"), e.attributes.get("end_ms")
            parts.append(f"[{a}–{b} ms] {t}")
        else:
            if e.method == "ocr" and not mmd:
                parts.append(f"{t}")
            else:
                parts.append(t)
    if omitted:
        parts.append(f"<!-- {omitted} running header/footer/page-number element(s) are omitted from this "
                     f"rendering and preserved in the canonical representation. -->")
    if doc.unprocessed_pages:
        parts.append(f"> **Pages not processed:** {', '.join(map(str, doc.unprocessed_pages))}. "
                     "Their content is not in this rendering.")
    return "\n\n".join(p for p in parts if p is not None and p != "").strip() + "\n"


def to_html(doc: CanonicalDocument) -> str:
    body, omitted = _body(doc)
    captions = _captions(doc)
    esc = html.escape
    out: list[str] = []
    for e in body:
        t = esc((e.normalized_text or e.text or "").strip())
        # Every attribute value is escaped: page, bbox, direction and language can come from an external
        # extraction provider, and this HTML is served as text/html (security audit SEC-05).
        loc = f' data-page="{esc(str(e.page))}" data-block="{esc(str(e.block_id))}"'
        if e.bbox:
            loc += f' data-bbox="{esc(",".join(str(v) for v in e.bbox))}"'
        dir_attr = f' dir="{esc(str(e.direction))}"' if e.direction else ""
        lang = f' lang="{esc(str(e.language))}"' if e.language else ""
        k = e.element_type
        if k == "caption" and e.parent_block_id in {b.block_id for b in body}:
            continue
        if k in ("title", "heading"):
            n = 1 if k == "title" else min(6, (e.level or 1) + 1)
            out.append(f"<h{n}{loc}{dir_attr}{lang}>{t}</h{n}>")
        elif k == "list_item":
            out.append(f"<ul><li{loc}{dir_attr}{lang}>{t}</li></ul>")
        elif k == "table":
            cells = e.attributes.get("cells")
            cap = captions.get(e.block_id)
            rows_html = []
            if cells:
                by_row: dict[int, list[dict]] = {}
                for c in cells:
                    by_row.setdefault(c["row"], []).append(c)
                header_rows = int(e.attributes.get("header_rows") or 0)
                for r in sorted(by_row):
                    tag = "th" if r < header_rows else "td"
                    tds = "".join(
                        f"<{tag}{' rowspan=%d' % c['rowspan'] if c.get('rowspan', 1) > 1 else ''}"
                        f"{' colspan=%d' % c['colspan'] if c.get('colspan', 1) > 1 else ''}>{esc(c['text'])}</{tag}>"
                        for c in sorted(by_row[r], key=lambda c: c["col"]))
                    rows_html.append(f"<tr>{tds}</tr>")
            else:
                for r in _rows(e):
                    rows_html.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>")
            caption = f"<caption>{esc(cap.text.strip())}</caption>" if cap else ""
            out.append(f"<table{loc}>{caption}{''.join(rows_html)}</table>")
        elif k == "figure":
            cap = captions.get(e.block_id)
            fc = f"<figcaption>{esc(cap.text.strip())}</figcaption>" if cap else ""
            note = "" if e.attributes.get("interpreted") else "<p class=\"not-interpreted\">Figure not interpreted.</p>"
            out.append(f"<figure{loc}>{fc}{note}</figure>")
        elif k == "equation_display":
            latex = e.attributes.get("latex")
            if latex and e.attributes.get("recognised"):
                out.append(f"<div class=\"math display\"{loc}>\\[{esc(latex)}\\]</div>")
            else:
                out.append(f"<div class=\"equation-unrecognised\"{loc}><code>{t}</code></div>")
        elif k == "code":
            out.append(f"<pre{loc}><code>{esc(e.text or '')}</code></pre>")
        else:
            cls = f' class="{esc(k)}"' if k != "paragraph" else ""
            out.append(f"<p{cls}{loc}{dir_attr}{lang}>{t}</p>")
    if omitted:
        out.append(f"<!-- {omitted} running header/footer/page-number element(s) omitted from this rendering -->")
    return "<article>\n" + "\n".join(out) + "\n</article>\n"


def _tex(s: str) -> str:
    for a, b in (("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"), ("$", "\\$"), ("#", "\\#"),
                 ("_", "\\_"), ("{", "\\{"), ("}", "\\}"), ("~", "\\textasciitilde{}"), ("^", "\\^{}")):
        s = s.replace(a, b)
    return s


def to_latex(doc: CanonicalDocument) -> str:
    body, omitted = _body(doc)
    out = ["\\documentclass{article}", "\\usepackage[utf8]{inputenc}", "\\usepackage{amsmath}", "\\begin{document}"]
    for e in body:
        t = _tex((e.normalized_text or e.text or "").strip())
        k = e.element_type
        if k == "title":
            out.append(f"\\section*{{{t}}}")
        elif k == "heading":
            out.append(["\\section", "\\subsection", "\\subsubsection"][min(2, (e.level or 1) - 1)] + f"*{{{t}}}")
        elif k == "equation_display":
            latex = e.attributes.get("latex")
            if latex and e.attributes.get("recognised"):
                out.append(f"\\begin{{equation*}}\n{latex}\n\\end{{equation*}}")
            else:
                out.append(f"% equation not recognised; text as printed\n\\texttt{{{t}}}")
        elif k == "table":
            rows = _rows(e)
            if rows:
                width = max(len(r) for r in rows)
                out.append("\\begin{tabular}{" + "l" * width + "}")
                out += [" & ".join(_tex(c) for c in r + [""] * (width - len(r))) + " \\\\" for r in rows]
                out.append("\\end{tabular}")
        elif k == "figure":
            out.append(f"% figure {e.block_id} ({_where(e)}) — not interpreted")
        elif k == "list_item":
            out.append(f"\\begin{{itemize}}\\item {t}\\end{{itemize}}")
        elif t:
            out.append(t + "\n")
    if omitted:
        out.append(f"% {omitted} running header/footer/page-number element(s) omitted")
    out.append("\\end{document}")
    return "\n".join(out) + "\n"


def render(doc: CanonicalDocument, fmt: str) -> str:
    fmt = fmt.lower()
    if fmt in UNAVAILABLE_FORMATS:
        raise UnsupportedFormat(UNAVAILABLE_FORMATS[fmt])
    if fmt == "markdown":
        return to_markdown(doc)
    if fmt == "mmd":
        return to_markdown(doc, mmd=True)
    if fmt == "html":
        return to_html(doc)
    if fmt == "latex":
        return to_latex(doc)
    if fmt == "json":
        return json.dumps(doc.to_dict(), ensure_ascii=False, indent=2)
    raise UnsupportedFormat(f"unknown format {fmt!r}; available: {', '.join(FORMATS)}")


MEDIA_TYPES = {"markdown": "text/markdown; charset=utf-8", "mmd": "text/markdown; charset=utf-8",
               "html": "text/html; charset=utf-8", "latex": "application/x-latex; charset=utf-8",
               "json": "application/json"}
