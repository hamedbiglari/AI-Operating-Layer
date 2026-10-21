"""
Tesseract with geometry (§8.1, §9).

The Phase 3 OCR (`extractors.ocr_image`) returns a string. A string cannot say where on the page a
word was, or how sure the engine was about it. Here tesseract's own TSV output is read instead: every
word with its box and its confidence, grouped by the engine's own block / paragraph / line numbers.

Same safety rules as before: subprocess without a shell, a temp file rather than stdin, a timeout, and
`unavailable` — never an empty result — when the binary is missing.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

OCR_TIMEOUT_SECONDS = 60


@dataclass
class OcrLine:
    text: str
    bbox: list[float]           # in the IMAGE's pixel space; the caller scales to page points
    confidence: float | None    # 0..1, mean of word confidences; None if tesseract gave none


@dataclass
class OcrParagraph:
    lines: list[OcrLine]

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)

    @property
    def bbox(self) -> list[float]:
        xs0, ys0, xs1, ys1 = zip(*(l.bbox for l in self.lines))
        return [min(xs0), min(ys0), max(xs1), max(ys1)]

    @property
    def confidence(self) -> float | None:
        vals = [l.confidence for l in self.lines if l.confidence is not None]
        return round(sum(vals) / len(vals), 3) if vals else None


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def tesseract_version() -> str | None:
    if not tesseract_available():
        return None
    try:
        out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=10)
        return (out.stdout or out.stderr).splitlines()[0].strip() or "unknown"
    except Exception:  # pragma: no cover - defensive
        return None


def parse_tsv(tsv: str) -> list[OcrParagraph]:
    """Tesseract TSV → paragraphs of lines. Pure function, so it is testable without the binary."""
    rows = tsv.splitlines()
    if not rows:
        return []
    header = rows[0].split("\t")
    idx = {name: i for i, name in enumerate(header)}
    needed = ("level", "block_num", "par_num", "line_num", "left", "top", "width", "height", "conf", "text")
    if not all(n in idx for n in needed):
        return []
    lines: dict[tuple, dict] = {}
    order: list[tuple] = []
    for raw in rows[1:]:
        cols = raw.split("\t")
        if len(cols) < len(header):
            continue
        if cols[idx["level"]] != "5":           # 5 = word
            continue
        text = cols[idx["text"]].strip()
        if not text:
            continue
        key = (int(cols[idx["block_num"]]), int(cols[idx["par_num"]]), int(cols[idx["line_num"]]))
        left, top = float(cols[idx["left"]]), float(cols[idx["top"]])
        right, bottom = left + float(cols[idx["width"]]), top + float(cols[idx["height"]])
        try:
            conf = float(cols[idx["conf"]])
        except ValueError:
            conf = -1.0
        if key not in lines:
            lines[key] = {"words": [], "bbox": [left, top, right, bottom], "confs": []}
            order.append(key)
        entry = lines[key]
        entry["words"].append(text)
        b = entry["bbox"]
        entry["bbox"] = [min(b[0], left), min(b[1], top), max(b[2], right), max(b[3], bottom)]
        if conf >= 0:                                  # -1 = tesseract had no opinion
            entry["confs"].append(conf / 100.0)
    paragraphs: dict[tuple, list[OcrLine]] = {}
    par_order: list[tuple] = []
    for key in order:
        entry = lines[key]
        confs = entry["confs"]
        line = OcrLine(text=" ".join(entry["words"]), bbox=entry["bbox"],
                       confidence=round(sum(confs) / len(confs), 3) if confs else None)
        pkey = key[:2]
        if pkey not in paragraphs:
            paragraphs[pkey] = []
            par_order.append(pkey)
        paragraphs[pkey].append(line)
    return [OcrParagraph(lines=paragraphs[k]) for k in par_order]


# Tesseract language codes ("eng", "fas", "chi_sim"), up to five joined by "+". Anything else — a path such as
# "../../tmp/x" would make tesseract load that file as language data — is refused (security audit SEC-15).
_LANGS_RE = re.compile(r"[a-z]{3}(?:_[a-z]{3,4})?(?:\+[a-z]{3}(?:_[a-z]{3,4})?){0,4}")


def safe_languages(languages: str | None) -> str:
    value = (languages or "eng").strip()
    if not _LANGS_RE.fullmatch(value):
        raise ValueError("OCR languages must be tesseract codes such as 'eng' or 'eng+fas'")
    return value


def ocr_image_file(path: Path, languages: str = "eng") -> list[OcrParagraph]:
    """Raises FileNotFoundError when tesseract is absent, so the caller records `unavailable`."""
    if not tesseract_available():
        raise FileNotFoundError("tesseract")
    out = subprocess.run(["tesseract", str(path), "stdout", "-l", safe_languages(languages), "tsv"],
                         capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS, shell=False)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "tesseract failed")[:300])
    return parse_tsv(out.stdout or "")


def ocr_image_bytes(data: bytes, languages: str = "eng", suffix: str = ".png") -> list[OcrParagraph]:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / f"page{suffix}"
        target.write_bytes(data)
        return ocr_image_file(target, languages)
