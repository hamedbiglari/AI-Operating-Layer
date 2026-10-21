"""
Extraction benchmark (prompt v4.0 §57–§58; ADR-122).

Measures a provider's canonical representation against ground truth. It exists so that statements like
"provider X is better at tables" are measured here rather than taken from anyone's marketing — including
our own. Nothing in this module ranks providers; it reports numbers per document and per metric, and a
metric that cannot be computed for a document is `None` with the reason, never 0.

Ground truth (one JSON-able dict per document):

    {"blocks":   [{"text": "...", "type": "paragraph"}, ...]    # in true reading order
     "headings": ["Composition of Taranjabin Manna", ...]
     "tables":   [[["Compound", "Amount"], ["Mannitol", "42.1"]], ...]
     "equations": ["a + b = g"],                               # text or LaTeX
     "captions": {"Table 1. ...": "table"}}                     # caption → kind of thing it labels

Metrics:
  text_cer / text_wer        character / word error rate of body text (lower is better)
  information_loss           share of ground-truth words absent from the extraction (§58)
  reading_order_tau          Kendall tau between true and extracted order of matched blocks (1 = perfect)
  heading_f1                 headings found vs. headings that exist
  table_cell_accuracy        share of ground-truth cells reproduced in the right row/column
  equation_recall            share of ground-truth equations located (recognition shown separately)
  caption_association        share of captions attached to the right kind of object
  provenance_completeness    share of elements with a page and a box (paginated sources only)
  confidence_calibration     mean |confidence − correct| over blocks that could be judged (lower is better)

Run:  python -m app.ingestion.benchmark <provider> <file> <truth.json> [...]
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from app.ingestion.cdr import CanonicalDocument, normalize_text

SKIP = ("header", "footer", "page_number", "page_break", "link")


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (normalize_text(s or "") or "")).strip().lower()


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def error_rate(truth: list, got: list) -> float | None:
    if not truth:
        return None
    return round(levenshtein(truth, got) / len(truth), 4) if isinstance(truth, str) else \
        round(_seq_distance(truth, got) / len(truth), 4)


def _seq_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def kendall_tau(order: list[int]) -> float | None:
    n = len(order)
    if n < 2:
        return None
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            if order[i] < order[j]:
                concordant += 1
            elif order[i] > order[j]:
                discordant += 1
    return round((concordant - discordant) / (n * (n - 1) / 2), 4)


@dataclass
class DocResult:
    name: str
    provider: str
    metrics: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def evaluate(doc: CanonicalDocument, truth: dict, *, name: str = "document") -> DocResult:
    r = DocResult(name=name, provider=doc.provider)
    body = [e for e in doc.elements if e.element_type not in SKIP]
    got_text = _norm(" ".join(e.normalized_text or e.text or "" for e in body))
    blocks = truth.get("blocks") or []
    true_text = _norm(" ".join(b["text"] for b in blocks))
    m = r.metrics

    # text
    if true_text:
        m["text_cer"] = round(levenshtein(true_text, got_text) / len(true_text), 4) if len(true_text) <= 20000 else None
        tw, gw = true_text.split(), got_text.split()
        m["text_wer"] = round(_seq_distance(tw, gw) / len(tw), 4) if len(tw) <= 4000 else None
        got_words = set(gw)
        m["information_loss"] = round(sum(1 for w in tw if w not in got_words) / len(tw), 4)
    else:
        m["text_cer"] = m["text_wer"] = m["information_loss"] = None
        r.notes.append("no ground-truth text")

    # reading order: match each truth block to the element that contains it best
    positions: list[int] = []
    judged: list[tuple[float | None, bool]] = []
    for b in blocks:
        t = _norm(b["text"])
        best, best_i, best_ratio = None, -1, 0.0
        for i, e in enumerate(body):
            et = _norm(e.normalized_text or e.text)
            if not et:
                continue
            # ratio(), not quick_ratio(): the latter is only an upper bound and pairs "first block" with "third block"
            ratio = 1.0 if t and t in et else SequenceMatcher(None, t, et).ratio()
            if ratio > best_ratio:
                best, best_i, best_ratio = e, i, ratio
        if best is not None and best_ratio >= 0.8:
            positions.append(best_i)
            correct = t in _norm(best.normalized_text or best.text)
            judged.append((best.confidence, correct))
    m["blocks_matched"] = f"{len(positions)}/{len(blocks)}"
    m["reading_order_tau"] = kendall_tau(positions)

    # headings
    th = {_norm(h) for h in truth.get("headings") or []}
    gh = {_norm(e.text) for e in doc.elements if e.element_type in ("heading", "title")}
    if th:
        tp = len(th & gh)
        precision = tp / len(gh) if gh else 0.0
        recall = tp / len(th)
        m["heading_f1"] = round(2 * precision * recall / (precision + recall), 4) if tp else 0.0
    else:
        m["heading_f1"] = None

    # tables
    tt = truth.get("tables") or []
    if tt:
        got_tables = [e.attributes.get("rows") or [] for e in doc.elements if e.element_type == "table"]
        total = sum(len(row) for t in tt for row in t)
        hit = 0
        for t in tt:
            best = 0
            for g in got_tables:
                score = sum(1 for ri, row in enumerate(t) for ci, cell in enumerate(row)
                            if ri < len(g) and ci < len(g[ri]) and _norm(g[ri][ci]) == _norm(cell))
                best = max(best, score)
            hit += best
        m["table_cell_accuracy"] = round(hit / total, 4) if total else None
    else:
        m["table_cell_accuracy"] = None

    # equations
    te = truth.get("equations") or []
    if te:
        eqs = [e for e in doc.elements if e.element_type in ("equation_display", "equation_inline")]
        found = sum(1 for t in te if any(_norm(t).replace(" ", "") in _norm(e.text).replace(" ", "")
                                         or _norm(t).replace(" ", "") in _norm(e.attributes.get("latex") or "").replace(" ", "")
                                         for e in eqs))
        m["equation_recall"] = round(found / len(te), 4)
        m["equations_recognised_as_latex"] = sum(1 for e in eqs if e.attributes.get("recognised"))
    else:
        m["equation_recall"] = None

    # captions
    tc = truth.get("captions") or {}
    if tc:
        by_id = {e.block_id: e for e in doc.elements}
        ok = 0
        for text_, kind in tc.items():
            cap = next((e for e in doc.elements if e.element_type == "caption" and _norm(e.text).startswith(_norm(text_)[:20])), None)
            if cap and cap.parent_block_id in by_id and by_id[cap.parent_block_id].element_type == kind:
                ok += 1
        m["caption_association"] = round(ok / len(tc), 4)
    else:
        m["caption_association"] = None

    # provenance
    paginated = [e for e in doc.elements if e.page is not None]
    if paginated:
        m["provenance_completeness"] = round(sum(1 for e in paginated if e.bbox) / len(paginated), 4)
    else:
        m["provenance_completeness"] = None
        r.notes.append("not paginated: page/box provenance does not apply")

    # calibration (§57): how far stated confidence is from observed correctness
    scored = [(c, ok) for c, ok in judged if c is not None]
    m["confidence_calibration"] = round(sum(abs(c - (1.0 if ok else 0.0)) for c, ok in scored) / len(scored), 4) \
        if scored else None
    m["overall_confidence_stated"] = doc.confidence.overall
    m["unprocessed_pages"] = doc.unprocessed_pages
    return r


def run(provider_name: str, cases: list[tuple[Path, dict]]) -> dict:
    from app.ingestion.providers import registry

    provider = registry()[provider_name]
    available = provider.availability()
    if not available.available:
        return {"provider": provider_name, "available": False, "reason": available.reason, "documents": []}
    out = []
    for path, truth in cases:
        try:
            doc = provider.extract(path)
            out.append(asdict(evaluate(doc, truth, name=path.name)))
        except Exception as exc:  # a failure is a result, reported as such
            out.append({"name": path.name, "provider": provider_name, "metrics": {},
                        "notes": [f"extraction failed: {type(exc).__name__}: {exc}"[:300]]})
    return {"provider": provider_name, "provider_version": provider.version, "available": True, "documents": out,
            "note": "Per-document metrics only. No ranking, and no claim of superiority over any other provider."}


if __name__ == "__main__":  # pragma: no cover
    name, *rest = sys.argv[1:]
    pairs = [(Path(rest[i]), json.loads(Path(rest[i + 1]).read_text(encoding="utf-8"))) for i in range(0, len(rest), 2)]
    print(json.dumps(run(name, pairs), indent=2, ensure_ascii=False))
