"""
Unit tests for app/services/recommendation_policy.py — pure functions,
no database.

These test the semantics that a naive scorer gets wrong, and that the
Phase 8 brief calls out explicitly: UNKNOWN is not NEGATIVE, missing
price is not free, and no score may overturn a hard gate.
"""

from datetime import datetime, timedelta, timezone

from app.contracts.commerce import (
    OfferReadModel,
    ProductEvidenceSummary,
    ProductReadModel,
    TrustSummary,
)
from app.models.enums import (
    ConsentStatus,
    NeedLevel,
    OfferAvailability,
    ProductStatus,
    RecommendationStatus,
    ResponseMode,
    SignalState,
    TrustType,
)
from app.services import recommendation_policy as policy

_UUID_A = __import__("uuid").uuid4()
_UUID_B = __import__("uuid").uuid4()


def _product(status: ProductStatus = ProductStatus.PUBLISHED, **kw) -> ProductReadModel:
    return ProductReadModel(
        id=kw.get("id", _UUID_A),
        organization_id=_UUID_B,
        name=kw.get("name", "Taranjabin 500g"),
        slug="taranjabin-500g",
        brand=kw.get("brand"),
        category=kw.get("category"),
        origin=None,
        status=status,
        knowledge_object_id=kw.get("knowledge_object_id"),
    )


def _offer(**kw) -> OfferReadModel:
    return OfferReadModel(
        id=kw.get("id", _UUID_B),
        product_id=_UUID_A,
        price=kw.get("price", 100.0),
        currency=kw.get("currency", "EUR"),
        availability=kw.get("availability", OfferAvailability.IN_STOCK),
        stock_quantity=kw.get("stock_quantity"),
        valid_from=kw.get("valid_from"),
        valid_until=kw.get("valid_until"),
    )


# --- THE central semantic: UNKNOWN != NEGATIVE -----------------------------


def test_no_evidence_is_unknown_and_neutral_not_zero() -> None:
    """A product with no evidence must NOT be scored as though evidence
    contradicted it. Scoring 0.0 here would punish every new honest
    product."""
    result = policy.score_evidence(None, need=NeedLevel.NORMAL)
    assert result.state == SignalState.UNKNOWN
    assert result.score == 0.5
    assert result.score > 0.0


def test_rejected_evidence_is_negative_and_scores_low() -> None:
    """Contrast with the test above: rejection IS a negative fact."""
    summary = ProductEvidenceSummary(product_id=_UUID_A, rejected=2)
    result = policy.score_evidence(summary, need=NeedLevel.NORMAL)
    assert result.state == SignalState.NEGATIVE
    assert result.score < 0.5


def test_no_evidence_scores_strictly_higher_than_rejected_evidence() -> None:
    """The invariant that makes the distinction meaningful rather than
    cosmetic."""
    unknown = policy.score_evidence(None, need=NeedLevel.NORMAL)
    rejected = policy.score_evidence(
        ProductEvidenceSummary(product_id=_UUID_A, rejected=1), need=NeedLevel.NORMAL
    )
    assert unknown.score > rejected.score


def test_unverified_claims_never_count_as_evidence() -> None:
    summary = ProductEvidenceSummary(product_id=_UUID_A, unverified=5, pending_review=3)
    result = policy.score_evidence(summary, need=NeedLevel.NORMAL)
    assert result.state == SignalState.UNKNOWN
    assert result.score == 0.5  # eight unreviewed claims buy exactly nothing


def test_verified_evidence_is_established_and_scores_high() -> None:
    summary = ProductEvidenceSummary(
        product_id=_UUID_A, verified=2, verified_claims=["Origin = Iran", "Grade = A"]
    )
    result = policy.score_evidence(summary, need=NeedLevel.NORMAL)
    assert result.state == SignalState.ESTABLISHED
    assert result.score > 0.5


def test_mixed_verified_and_rejected_is_conflicting() -> None:
    summary = ProductEvidenceSummary(product_id=_UUID_A, verified=1, rejected=1)
    result = policy.score_evidence(summary, need=NeedLevel.NORMAL)
    assert result.state == SignalState.CONFLICTING


def test_no_trust_record_is_unknown_not_untrustworthy() -> None:
    result = policy.score_trust(None, need=NeedLevel.NORMAL)
    assert result.state == SignalState.UNKNOWN
    assert result.score == 0.5


def test_rejected_trust_is_negative() -> None:
    summary = TrustSummary(subject_id=_UUID_A, rejected=1)
    result = policy.score_trust(summary, need=NeedLevel.NORMAL)
    assert result.state == SignalState.NEGATIVE
    assert result.score < 0.5


def test_verified_trust_is_established() -> None:
    summary = TrustSummary(
        subject_id=_UUID_A, verified=2, verified_trust_types=[TrustType.ORIGIN, TrustType.QUALITY]
    )
    result = policy.score_trust(summary, need=NeedLevel.NORMAL)
    assert result.state == SignalState.ESTABLISHED


# --- Hard gates cannot be outscored ------------------------------------------


def test_unpublished_product_fails_gate_regardless_of_everything_else() -> None:
    for status in (ProductStatus.DRAFT, ProductStatus.IN_REVIEW, ProductStatus.ARCHIVED):
        gate = policy.check_product_eligible(_product(status), [_offer()])
        assert not gate.passed
        assert gate.failed_gate == "product_not_published"


def test_published_product_with_purchasable_offer_passes_gate() -> None:
    gate = policy.check_product_eligible(_product(), [_offer()])
    assert gate.passed


def test_product_with_no_offer_fails_gate() -> None:
    gate = policy.check_product_eligible(_product(), [])
    assert not gate.passed
    assert gate.failed_gate == "no_offer"


def test_out_of_stock_only_fails_gate() -> None:
    gate = policy.check_product_eligible(
        _product(), [_offer(availability=OfferAvailability.OUT_OF_STOCK)]
    )
    assert not gate.passed
    assert gate.failed_gate == "no_purchasable_offer"


def test_withdrawn_consent_is_a_hard_gate() -> None:
    assert not policy.check_consent(ConsentStatus.WITHDRAWN).passed
    assert policy.check_consent(ConsentStatus.GRANTED).passed
    assert policy.check_consent(None).passed


def test_educate_and_reassure_modes_block_product_push() -> None:
    """Section 34: do not push products when intent doesn't justify it."""
    assert not policy.check_response_mode(ResponseMode.EDUCATE).passed
    assert not policy.check_response_mode(ResponseMode.REASSURE).passed
    for mode in (ResponseMode.COMPARE, ResponseMode.RECOMMEND, ResponseMode.TRANSACT):
        assert policy.check_response_mode(mode).passed


# --- Offer semantics ----------------------------------------------------------


def test_untracked_stock_is_purchasable_but_zero_stock_is_not() -> None:
    """NULL stock means untracked, not zero — the distinction Phase 7
    deliberately preserved and Phase 8 must not collapse."""
    assert _offer(stock_quantity=None).is_purchasable()
    assert not _offer(stock_quantity=0).is_purchasable()


def test_price_on_request_is_not_treated_as_cheapest() -> None:
    """A priceless offer must never win on price."""
    priced = _offer(id=_UUID_A, price=50.0)
    priceless = _offer(id=_UUID_B, price=None)
    result, chosen = policy.score_availability([priceless, priced], mode=ResponseMode.RECOMMEND)
    assert chosen.price == 50.0
    assert result.state == SignalState.ESTABLISHED


def test_expired_offer_is_not_purchasable() -> None:
    past = datetime.now(timezone.utc) - timedelta(days=1)
    assert not _offer(valid_until=past).is_purchasable()


def test_future_offer_is_not_yet_purchasable() -> None:
    future = datetime.now(timezone.utc) + timedelta(days=7)
    assert not _offer(valid_from=future).is_purchasable()


def test_preorder_scores_lower_under_transact_than_recommend() -> None:
    """Under TRANSACT the user wants it now, so 'available later'
    matters more."""
    offers = [_offer(availability=OfferAvailability.PREORDER)]
    transact, _ = policy.score_availability(offers, mode=ResponseMode.TRANSACT)
    recommend, _ = policy.score_availability(offers, mode=ResponseMode.RECOMMEND)
    assert transact.score < recommend.score


# --- Decision / abstention ------------------------------------------------------


def test_unknown_signals_produce_a_caveat_not_a_confident_recommendation() -> None:
    unknown = policy.SignalResult(0.5, SignalState.UNKNOWN, "nothing established")
    status, caveats = policy.decide(
        final_score=0.9, evidence=unknown, trust=unknown,
        mode=ResponseMode.RECOMMEND, evidence_need=NeedLevel.NORMAL, trust_need=NeedLevel.NORMAL,
    )
    assert status == RecommendationStatus.RECOMMENDED_WITH_CAVEAT
    assert caveats


def test_negative_signal_always_carries_a_caveat_even_with_high_score() -> None:
    """A high score must never silently launder a rejected claim."""
    negative = policy.SignalResult(0.1, SignalState.NEGATIVE, "rejected")
    established = policy.SignalResult(0.9, SignalState.ESTABLISHED, "ok")
    status, caveats = policy.decide(
        final_score=0.95, evidence=negative, trust=established,
        mode=ResponseMode.RECOMMEND, evidence_need=NeedLevel.NORMAL, trust_need=NeedLevel.NORMAL,
    )
    assert status == RecommendationStatus.RECOMMENDED_WITH_CAVEAT
    assert any("rejected" in c.lower() for c in caveats)


def test_fully_established_signals_produce_a_clean_recommendation() -> None:
    established = policy.SignalResult(0.9, SignalState.ESTABLISHED, "ok")
    status, caveats = policy.decide(
        final_score=0.85, evidence=established, trust=established,
        mode=ResponseMode.RECOMMEND, evidence_need=NeedLevel.NORMAL, trust_need=NeedLevel.NORMAL,
    )
    assert status == RecommendationStatus.RECOMMENDED
    assert caveats == []


def test_high_evidence_need_downgrades_a_partially_evidenced_product() -> None:
    partial = policy.SignalResult(0.7, SignalState.PARTIAL, "one verified claim")
    established = policy.SignalResult(0.9, SignalState.ESTABLISHED, "ok")
    status, caveats = policy.decide(
        final_score=0.8, evidence=partial, trust=established,
        mode=ResponseMode.RECOMMEND, evidence_need=NeedLevel.HIGH, trust_need=NeedLevel.NORMAL,
    )
    assert status == RecommendationStatus.RECOMMENDED_WITH_CAVEAT


def test_aggregate_is_deterministic_and_bounded() -> None:
    s = policy.SignalResult(1.0, SignalState.ESTABLISHED, "")
    assert policy.aggregate(s, s, s, s) == 1.0
    zero = policy.SignalResult(0.0, SignalState.NEGATIVE, "")
    assert policy.aggregate(zero, zero, zero, zero) == 0.0
    # same inputs, same output, every time
    assert policy.aggregate(s, zero, s, zero) == policy.aggregate(s, zero, s, zero)


def test_weights_sum_to_one() -> None:
    assert round(sum(policy._WEIGHTS.values()), 6) == 1.0


def test_policy_version_matches_weights(monkeypatch) -> None:
    """B3: POLICY_VERSION bumping was manual, so a weight change could
    silently mislabel historical decisions. This pins the current
    weights to the current version — changing one without the other
    fails here, which is the point."""
    assert policy.POLICY_VERSION == "2026.01-deterministic-v1"
    assert policy._WEIGHTS == {
        "relevance": 0.35, "evidence": 0.25, "trust": 0.25, "availability": 0.15,
    }
    assert policy._NEUTRAL == 0.5
    assert policy._CONFIDENT_THRESHOLD == 0.6
