"""
Block classification rules shared by every provider that has to infer structure itself.

These are heuristics and they say so: anything classified here carries `attributes.classified_by =
"heuristic"`, and the equation and chemistry detectors give low confidence because they find
*candidates*, not recognised mathematics. A provider that genuinely recognises equations (Mathpix
returns LaTeX) overrides them.
"""
from __future__ import annotations

import re

CAPTION_RE = re.compile(
    r"^\s*(fig(?:ure)?\.?|table|tab\.|chart|scheme|plate|graph|شکل|جدول|نمودار|الشكل|جدول)\s*"
    r"([0-9۰-۹٠-٩]+[a-z]?)", re.IGNORECASE)
TABLE_CAPTION_RE = re.compile(r"^\s*(table|tab\.|جدول)", re.IGNORECASE)
LIST_RE = re.compile(r"^\s*([•●▪◦‣⁃\-–•·*]|\(?[0-9۰-۹]{1,3}[.)]|\(?[a-z][.)])\s+")
REFERENCES_HEADING_RE = re.compile(
    r"^\s*(\d+\.?\s*)?(references|bibliography|literature cited|works cited|sources|منابع|مراجع|المراجع|فهرست منابع)\s*$",
    re.IGNORECASE)
REFERENCE_SPLIT_RE = re.compile(r"(?m)^\s*(?=\[\d{1,4}\]|\d{1,4}\.\s)")
PAGE_NUMBER_RE = re.compile(
    r"^\W*(page|صفحه|p\.)?\s*[0-9۰-۹٠-٩ivxlc]{1,5}(\s*(of|/|از)\s*[0-9۰-۹]{1,5})?\W*$",
    re.IGNORECASE)
EQUATION_NUMBER_RE = re.compile(r"\(\s*(\d{1,3}(?:\.\d{1,3})?[a-z]?)\s*\)\s*$")
MATH_SYMBOLS = set("=+−×÷±∓≤≥≈≠≡∝∞∑∏∫∮√∂∇∆∈∉⊂⊃∪∩∀∃→←↔⇒⇔^_αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ′″")
MATH_FONT_HINTS = ("math", "cmmi", "cmsy", "cmex", "symbol", "stix", "cambria math", "msbm", "esint")
# a token that looks like a chemical formula: ≥2 element symbols with at least one count, e.g. C6H12O6, H2O
CHEM_FORMULA_RE = re.compile(r"\b(?:[A-Z][a-z]?\d{0,3}){2,}(?:[+-]|\d[+-])?\b")
CHEM_ARROW_RE = re.compile(r"(→|⟶|⇌|⇄|->|<=>|=>)")
_ELEMENTS = set(
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr "
    "Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W "
    "Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U".split())
_ELEMENT_TOKEN_RE = re.compile(r"([A-Z][a-z]?)(\d*)")


def math_symbol_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return sum(1 for c in chars if c in MATH_SYMBOLS) / len(chars)


def looks_like_display_equation(text: str, fontnames: list[str] | None = None) -> bool:
    t = text.strip()
    if not t or len(t) > 240:
        return False
    words = t.split()
    has_math_font = any(any(h in (f or "").lower() for h in MATH_FONT_HINTS) for f in (fontnames or []))
    ratio = math_symbol_ratio(t)
    if has_math_font and ratio >= 0.05:
        return True
    # prose with an "=" in it is not an equation: require density and few long words
    long_words = sum(1 for w in words if len(w) > 7 and w.isalpha())
    return ratio >= 0.15 and long_words <= 2


_TOKEN_SPLIT_RE = re.compile(r"[\s+,;()\[\]]+|→|⟶|⇌|⇄|->|<=>|=>")


def chemical_formulas(text: str) -> list[str]:
    """Formula-shaped tokens whose every symbol is a real element. A leading stoichiometric coefficient
    ('6CO2') is stripped. Without a reaction arrow a token needs two or more element symbols AND a count
    (C6H12O6, H2O) — otherwise every capitalised word would match; next to an arrow, 'O2' and 'NaCl'
    are accepted too."""
    found: list[str] = []
    arrow = bool(CHEM_ARROW_RE.search(text))
    for raw in _TOKEN_SPLIT_RE.split(text or ""):
        token = re.sub(r"^\d+", "", (raw or "").strip().rstrip(".:"))
        token = re.sub(r"(\d?[+-])$", "", token) if len(token) > 2 else token
        if not token or not token[0].isupper():
            continue
        parts = _ELEMENT_TOKEN_RE.findall(token)
        if not parts or "".join(s + n for s, n in parts) != token:
            continue
        if not all(sym in _ELEMENTS for sym, _ in parts):
            continue
        has_count = any(n for _, n in parts)
        if arrow:
            if len(parts) < 2 and not has_count:
                continue
        elif len(parts) < 2 or not has_count:
            continue
        if token not in found:
            found.append(token)
    return found


def is_chemical_equation(text: str) -> bool:
    return bool(CHEM_ARROW_RE.search(text)) and len(chemical_formulas(text)) >= 2


def caption_label(text: str) -> tuple[str, str] | None:
    m = CAPTION_RE.match(text or "")
    if not m:
        return None
    kind = "table" if TABLE_CAPTION_RE.match(text) else "figure"
    return kind, m.group(2)


def split_references(text: str) -> list[str]:
    parts = [p.strip() for p in REFERENCE_SPLIT_RE.split(text or "") if p and p.strip()]
    return parts or ([text.strip()] if text and text.strip() else [])


def strip_digits(text: str) -> str:
    return re.sub(r"[0-9۰-۹٠-٩]+", "#", (text or "").strip().lower())
