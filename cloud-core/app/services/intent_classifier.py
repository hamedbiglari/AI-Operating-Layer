"""
Rule-based intent classifier (master spec section 24).

Pure function, no DB/session dependency — app/services/intent_service.py
is the only caller, and owns turning matches into Intent rows.

Design principles (the specific failure mode this was built to avoid:
a bare "کجا" ("where") rule firing identically for "ترنجبین از کجا
می‌آید" [ORIGIN - where does it come from] and "کجا بخریم" [TRANSACTIONAL
- where to buy], which are opposite intents that happen to share one
token):

1. Every rule anchors on a multi-token phrase or an unambiguous single
   English word — never a bare, semantically-overloaded token like
   "کجا" on its own.
2. Rules are evaluated most-specific-first. A match "consumes" its
   matched character span; a later, looser rule is not allowed to
   fire again on a span already consumed by an earlier, more specific
   one. This is what stops a hypothetical generic "کجا" rule from also
   firing on the same substring a compound "کجا بخریم" rule already
   claimed — in practice this project's rule set never even defines
   that bare fallback, but the mechanism is real, not just documented
   intent, and is covered by test_intent_classifier.py.
3. Only compound, unambiguous anchors may reach HIGH confidence.
   Single-keyword rules are capped at a moderate ceiling. A query with
   no rule match produces ZERO intents (the query stays DISCOVERED),
   never a low-confidence guess.
4. A query can match MULTIPLE different intent types at once (genuine
   multi-intent) as long as the anchors don't overlap — "قیمت ترنجبین
   اصل کجا بخریم" legitimately is PRICE + AUTHENTICITY + TRANSACTIONAL
   simultaneously.
"""

import re
from dataclasses import dataclass

from app.models.enums import IntentType

# Compound/unambiguous anchors may reach this; the lone
# single-token-style rules below are all kept at or under
# _SINGLE_TOKEN_CEILING instead.
_SINGLE_TOKEN_CEILING = 0.6


@dataclass(frozen=True)
class RuleMatch:
    intent_type: IntentType
    confidence: float
    reason: str
    span: tuple[int, int]


@dataclass(frozen=True)
class _Rule:
    intent_type: IntentType
    pattern: re.Pattern
    confidence: float
    anchor_label: str


def _rule(intent_type: IntentType, pattern: str, confidence: float, anchor_label: str) -> _Rule:
    return _Rule(intent_type, re.compile(pattern, re.IGNORECASE | re.UNICODE), confidence, anchor_label)


# Ordered most-specific-first. Confidence: 0.85 for compound/verb-
# anchored phrases, 0.7 for still-specific-but-shorter phrases, capped
# at _SINGLE_TOKEN_CEILING (0.6) for the handful of genuinely
# single-word-but-unambiguous English anchors (e.g. "wholesale" isn't
# ambiguous the way "کجا" is, so it's allowed to exist, just not to
# out-rank compound matches).
_RULES: list[_Rule] = [
    # --- TRANSACTIONAL (purchase action) - checked before ORIGIN so a
    # shared "کجا" token resolves to the verb-anchored reading first.
    _rule(IntentType.TRANSACTIONAL, r"کجا\s+(می[‌ ]?توان(م)?\s+)?بخر", 0.85, "کجا...بخر"),
    _rule(IntentType.TRANSACTIONAL, r"خرید\s+(اینترنتی|آنلاین|از)", 0.85, "خرید اینترنتی/آنلاین/از"),
    _rule(IntentType.TRANSACTIONAL, r"سفارش\s+(دهم|بدهم|آنلاین)", 0.85, "سفارش دهم/بدهم/آنلاین"),
    _rule(IntentType.TRANSACTIONAL, r"where\s+(can\s+i|to)\s+buy", 0.85, "where (can i/to) buy"),
    _rule(IntentType.TRANSACTIONAL, r"\bbuy\s+\w+\s+online\b", 0.85, "buy ___ online"),
    _rule(IntentType.TRANSACTIONAL, r"\border\s+(online|now)\b", 0.7, "order online/now"),
    _rule(IntentType.TRANSACTIONAL, r"\bpurchase\b", 0.6, "purchase"),

    # --- ORIGIN (provenance) - requires "از کجا" + a
    # production/sourcing verb, never bare "کجا".
    _rule(IntentType.ORIGIN, r"منشا(ء)?", 0.85, "منشا"),
    _rule(IntentType.ORIGIN, r"از\s+کجا\s+(تولید|تهیه|استخراج|برداشت)\s*می[‌ ]?شود", 0.85, "از کجا تولید/تهیه می‌شود"),
    _rule(IntentType.ORIGIN, r"از\s+کجا\s+می[‌ ]?آید", 0.85, "از کجا می‌آید"),
    _rule(IntentType.ORIGIN, r"کشور\s+تولید", 0.85, "کشور تولید"),
    _rule(IntentType.ORIGIN, r"اصالت", 0.7, "اصالت"),
    _rule(IntentType.ORIGIN, r"where\s+(does|is)\s+\S+\s+(come\s+from|grown|from)\b", 0.85, "where does/is ... come from"),
    _rule(IntentType.ORIGIN, r"country\s+of\s+origin", 0.85, "country of origin"),
    _rule(IntentType.ORIGIN, r"\borigin\b", 0.6, "origin"),

    # --- AUTHENTICITY vs QUALITY vs TRUST
    _rule(IntentType.AUTHENTICITY, r"تشخیص\s+(اصل|تقلبی)", 0.85, "تشخیص اصل/تقلبی"),
    _rule(IntentType.AUTHENTICITY, r"تقلبی", 0.7, "تقلبی"),
    _rule(IntentType.AUTHENTICITY, r"اصل(ی)?\s+است", 0.7, "اصلی است"),
    _rule(IntentType.AUTHENTICITY, r"\b(is\s+it\s+)?(real|genuine|authentic)\b", 0.6, "real/genuine/authentic"),
    _rule(IntentType.AUTHENTICITY, r"real\s+or\s+fake", 0.85, "real or fake"),

    _rule(IntentType.TRUST, r"قابل\s+اعتماد", 0.85, "قابل اعتماد"),
    _rule(IntentType.TRUST, r"معتبر\s+است", 0.7, "معتبر است"),
    _rule(IntentType.TRUST, r"\btrustworthy\b", 0.6, "trustworthy"),
    _rule(IntentType.TRUST, r"\breliable\b", 0.6, "reliable"),

    _rule(IntentType.QUALITY, r"بهترین\s+کیفیت", 0.85, "بهترین کیفیت"),
    _rule(IntentType.QUALITY, r"کیفیت", 0.6, "کیفیت"),
    _rule(IntentType.QUALITY, r"\bbest\s+quality\b", 0.85, "best quality"),
    _rule(IntentType.QUALITY, r"\bquality\b", 0.6, "quality"),

    # --- PRICE / AVAILABILITY / SUPPLIER / WHOLESALE / LOCAL
    _rule(IntentType.PRICE, r"قیمت", 0.7, "قیمت"),
    _rule(IntentType.PRICE, r"نرخ\s+(روز|فروش)", 0.7, "نرخ روز/فروش"),
    _rule(IntentType.PRICE, r"چند\s+است", 0.6, "چند است"),
    _rule(IntentType.PRICE, r"how\s+much\s+(does|is|for)", 0.7, "how much does/is/for"),
    _rule(IntentType.PRICE, r"\bprice\s+of\b", 0.7, "price of"),

    _rule(IntentType.AVAILABILITY, r"موجود(ی)?\s+است", 0.7, "موجودی است"),
    _rule(IntentType.AVAILABILITY, r"در\s+دسترس", 0.6, "در دسترس"),
    _rule(IntentType.AVAILABILITY, r"\bin\s+stock\b", 0.7, "in stock"),
    _rule(IntentType.AVAILABILITY, r"\bavailability\b", 0.6, "availability"),

    _rule(IntentType.WHOLESALE, r"عمده\s*فروش(ی)?", 0.85, "عمده‌فروشی"),
    _rule(IntentType.WHOLESALE, r"خرید\s+عمده", 0.85, "خرید عمده"),
    _rule(IntentType.WHOLESALE, r"\bwholesale\b", 0.6, "wholesale"),
    _rule(IntentType.WHOLESALE, r"\bbulk\s+(order|buy|purchase)\b", 0.7, "bulk order/buy/purchase"),

    _rule(IntentType.SUPPLIER, r"تامین[‌ ]?کننده", 0.7, "تامین‌کننده"),
    _rule(IntentType.SUPPLIER, r"\bsupplier\b", 0.6, "supplier"),
    _rule(IntentType.SUPPLIER, r"\bdistributor\b", 0.6, "distributor"),

    _rule(IntentType.LOCAL, r"نزدیک\s+(من|ترین)", 0.7, "نزدیک من/ترین"),
    _rule(IntentType.LOCAL, r"\bnear\s+me\b", 0.85, "near me"),

    # --- COMPARISON / PROBLEM / RECOMMENDATION / COMMERCIAL
    _rule(IntentType.COMPARISON, r"تفاوت\s+(بین|میان)", 0.85, "تفاوت بین/میان"),
    _rule(IntentType.COMPARISON, r"در\s+مقابل", 0.7, "در مقابل"),
    _rule(IntentType.COMPARISON, r"\bvs\.?\b", 0.7, "vs"),
    _rule(IntentType.COMPARISON, r"\bcompar(e|ison)\b", 0.6, "compare/comparison"),
    _rule(IntentType.COMPARISON, r"difference\s+between", 0.85, "difference between"),

    _rule(IntentType.PROBLEM, r"عوارض\s+(جانبی)?", 0.7, "عوارض جانبی"),
    _rule(IntentType.PROBLEM, r"\bside\s+effects?\b", 0.7, "side effect(s)"),
    _rule(IntentType.PROBLEM, r"درمان\s+\S+\s+با", 0.7, "درمان ... با"),

    _rule(IntentType.RECOMMENDATION, r"پیشنهاد\s+می[‌ ]?کنید", 0.85, "پیشنهاد می‌کنید"),
    _rule(IntentType.RECOMMENDATION, r"توصیه\s+می[‌ ]?کنید", 0.85, "توصیه می‌کنید"),
    _rule(IntentType.RECOMMENDATION, r"\brecommend(ed|ation)?\b", 0.6, "recommend(ed/ation)"),

    _rule(IntentType.COMMERCIAL, r"بهترین\s+برند", 0.7, "بهترین برند"),
    _rule(IntentType.COMMERCIAL, r"\bbest\s+brand\b", 0.7, "best brand"),

    # --- EDUCATION / INFORMATION (broadest, checked last)
    _rule(IntentType.EDUCATION, r"طرز\s+تهیه", 0.85, "طرز تهیه"),
    _rule(IntentType.EDUCATION, r"چگونه\s+\S+\s+(کنیم|کنم|شود)", 0.7, "چگونه ... کنیم/کنم/شود"),
    _rule(IntentType.EDUCATION, r"آموزش\s", 0.6, "آموزش"),
    _rule(IntentType.EDUCATION, r"\bhow\s+to\b", 0.6, "how to"),
    _rule(IntentType.EDUCATION, r"\btutorial\b", 0.6, "tutorial"),

    _rule(IntentType.INFORMATION, r"\S+\s+چیست", 0.7, "___ چیست"),
    _rule(IntentType.INFORMATION, r"یعنی\s+چه", 0.6, "یعنی چه"),
    _rule(IntentType.INFORMATION, r"\bwhat\s+is\b", 0.6, "what is"),
]


def classify(text: str) -> list[RuleMatch]:
    """Returns every non-overlapping rule match, most-specific-first.
    Empty list means "no confident classification" — the caller must
    NOT invent a guess; the query stays DISCOVERED."""
    consumed: list[tuple[int, int]] = []
    matches: list[RuleMatch] = []

    for rule in _RULES:
        m = rule.pattern.search(text)
        if not m:
            continue
        span = m.span()
        if any(not (span[1] <= c[0] or span[0] >= c[1]) for c in consumed):
            continue  # overlaps a span an earlier, more specific rule already claimed
        confidence = min(rule.confidence, _SINGLE_TOKEN_CEILING) if rule.confidence <= _SINGLE_TOKEN_CEILING else rule.confidence
        matches.append(
            RuleMatch(
                intent_type=rule.intent_type,
                confidence=confidence,
                reason=f"matched anchor phrase '{rule.anchor_label}'",
                span=span,
            )
        )
        consumed.append(span)

    return matches


def pick_primary(matches: list[RuleMatch]) -> RuleMatch | None:
    """Highest confidence wins; ties broken by earliest match position
    (earlier in the query text = more likely to be the query's actual
    subject)."""
    if not matches:
        return None
    return sorted(matches, key=lambda m: (-m.confidence, m.span[0]))[0]
