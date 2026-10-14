"""
Unit tests for app/services/intent_classifier.py — a pure function, no
DB session needed. Focused especially on the exact failure mode the
design review called out: a bare "کجا" ("where") token must never be
the anchor for either ORIGIN or TRANSACTIONAL; only the full,
verb-anchored compound phrase should classify.
"""

from app.models.enums import IntentType
from app.services import intent_classifier


def _types(text: str) -> set[IntentType]:
    return {m.intent_type for m in intent_classifier.classify(text)}


def test_kojia_bekharim_is_transactional_not_origin() -> None:
    """The exact case the design review flagged: 'کجا بخریم' (where to
    buy) must classify as TRANSACTIONAL, and must NOT also fire ORIGIN
    just because it shares the token 'کجا' with an origin-style
    query."""
    matches = intent_classifier.classify("ترنجبین را از کجا بخریم")
    types = {m.intent_type for m in matches}
    assert IntentType.TRANSACTIONAL in types
    assert IntentType.ORIGIN not in types


def test_az_koja_miayad_is_origin_not_transactional() -> None:
    """The mirror case: 'از کجا می‌آید' (where does it come from) is
    ORIGIN, and must NOT fire TRANSACTIONAL despite sharing 'کجا'."""
    matches = intent_classifier.classify("ترنجبین از کجا می‌آید")
    types = {m.intent_type for m in matches}
    assert IntentType.ORIGIN in types
    assert IntentType.TRANSACTIONAL not in types


def test_manshaa_is_origin() -> None:
    assert IntentType.ORIGIN in _types("منشا ترنجبین چیست")


def test_gheymat_is_price() -> None:
    assert IntentType.PRICE in _types("قیمت ترنجبین")


def test_where_to_buy_english_is_transactional() -> None:
    assert IntentType.TRANSACTIONAL in _types("where to buy taranjabin")


def test_country_of_origin_english_is_origin() -> None:
    assert IntentType.ORIGIN in _types("country of origin of taranjabin")


def test_multi_intent_query_matches_multiple_non_overlapping_types() -> None:
    matches = intent_classifier.classify("قیمت ترنجبین اصل کجا بخریم")
    types = {m.intent_type for m in matches}
    assert IntentType.PRICE in types
    assert IntentType.TRANSACTIONAL in types


def test_no_match_returns_empty_list() -> None:
    assert intent_classifier.classify("زضصثقفغعهخحجچ") == []


def test_every_match_has_a_reason_naming_its_anchor() -> None:
    matches = intent_classifier.classify("قیمت ترنجبین چقدر است")
    assert matches
    for m in matches:
        assert m.reason
        assert "matched anchor phrase" in m.reason


def test_pick_primary_selects_highest_confidence() -> None:
    matches = intent_classifier.classify("قیمت ترنجبین اصل کجا بخریم")
    primary = intent_classifier.pick_primary(matches)
    assert primary is not None
    assert primary.confidence == max(m.confidence for m in matches)


def test_pick_primary_of_empty_list_is_none() -> None:
    assert intent_classifier.pick_primary([]) is None


def test_wholesale_vs_price_do_not_conflate() -> None:
    matches = intent_classifier.classify("خرید عمده ترنجبین قیمت چقدر است")
    types = {m.intent_type for m in matches}
    assert IntentType.WHOLESALE in types
    assert IntentType.PRICE in types


def test_single_token_english_rules_never_exceed_ceiling() -> None:
    for match in intent_classifier.classify("is this authentic and reliable and wholesale"):
        # every rule confidence in the table is either a compound
        # phrase (>0.6, exempt) or explicitly capped - this asserts no
        # single bare-token match ever silently exceeds the documented
        # ceiling for the ambiguous cases in this test sentence.
        assert match.confidence <= 0.85
