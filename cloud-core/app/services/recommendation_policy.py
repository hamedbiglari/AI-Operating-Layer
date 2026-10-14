"""
Recommendation policy — the deterministic decision core (master spec
sections 33/34).

**Pure functions. No database, no session, no I/O.** Everything here
takes read-contract dataclasses in and returns decisions out, which is
what makes the policy independently testable, trivially reproducible,
and replaceable without touching orchestration.

The pipeline is deliberately two-stage and the stages are NOT
interchangeable:

    HARD GATES  ->  eligible?  ->  SOFT SIGNALS  ->  score  ->  policy

A hard gate is a fact about permission: wrong tenant, unpublished
product, withdrawn consent, nothing purchasable. **No score can
overturn one.** This is the structural answer to the Phase 8 brief's
commercial-bias requirement: an irrelevant or unpublished product
cannot become recommendable by being profitable, because profitability
is a soft signal and soft signals are only consulted after the gates
have already passed.

Soft signals are matters of degree: relevance, evidence, trust,
availability. They order eligible products; they never admit
ineligible ones.

Three semantics that this module exists to protect, each of which a
naive scorer gets wrong:

1. **UNKNOWN is not NEGATIVE.** A product with no evidence scores
   NEUTRAL (0.5), not 0.0, and carries `SignalState.UNKNOWN`. Scoring
   it 0.0 would mean a brand-new honest product ranks below one whose
   merchant uploaded paperwork nobody verified. Rejected evidence, by
   contrast, genuinely does score low and carries NEGATIVE.
2. **Missing price is not free.** `price is None` means "on request";
   it never contributes a bargain signal.
3. **Response mode gates product push.** Section 34: "Do not push
   products when the user's intent does not justify it." EDUCATE
   produces NO_RECOMMENDATION by design, no matter how good the
   catalogue is.

POLICY_VERSION is stamped onto every persisted Recommendation. When
these weights change, that constant MUST change with them - otherwise
historical decisions become unexplainable, which the reproducibility
requirement forbids.
"""

from dataclasses import dataclass, field

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
    RecommendationStatus,
    ResponseMode,
    SignalState,
)

POLICY_VERSION = "2026.01-deterministic-v1"

# Weights are documented, deterministic, and sum to 1.0. They are a
# first-pass judgment about what should matter, not a tuned result -
# there is no recommendation data to tune against yet, and inventing
# precision would be dishonest. Relevance leads because an irrelevant
# product is useless however well-evidenced; evidence and trust
# together outweigh it, because this system's whole premise is that
# a well-supported product should beat a merely well-matched one.
_WEIGHTS = {
    "relevance": 0.35,
    "evidence": 0.25,
    "trust": 0.25,
    "availability": 0.15,
}

# The neutral score for "nothing established". Deliberately mid-scale,
# never 0.0 - see point 1 in the module docstring.
_NEUTRAL = 0.5

# Response modes where recommending a product is appropriate at all.
# EDUCATE and REASSURE answer a question; they do not sell.
_PRODUCT_PUSH_MODES = frozenset(
    {ResponseMode.COMPARE, ResponseMode.RECOMMEND, ResponseMode.TRANSACT}
)

# Below this, a product is eligible but not confidently recommendable -
# it comes back RECOMMENDED_WITH_CAVEAT so a caller can show it
# honestly rather than either hiding it or overselling it.
_CONFIDENT_THRESHOLD = 0.6


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failed_gate: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class SignalResult:
    score: float
    state: SignalState
    detail: str


@dataclass
class ProductDecision:
    product: ProductReadModel
    offer: OfferReadModel | None
    status: RecommendationStatus
    relevance: SignalResult
    evidence: SignalResult
    trust: SignalResult
    availability: SignalResult
    final_score: float
    caveats: list[str] = field(default_factory=list)
    rejection: GateResult | None = None


# --- Hard gates -----------------------------------------------------------


def check_consent(consent_status: ConsentStatus | None) -> GateResult:
    """A withdrawn consent is a permission fact, not a ranking penalty:
    it stops the whole request, for every product."""
    if consent_status == ConsentStatus.WITHDRAWN:
        return GateResult(
            passed=False,
            failed_gate="consent_withdrawn",
            detail="The customer context has withdrawn consent; no recommendations are produced.",
        )
    return GateResult(passed=True)


def check_response_mode(mode: ResponseMode) -> GateResult:
    if mode not in _PRODUCT_PUSH_MODES:
        return GateResult(
            passed=False,
            failed_gate="response_mode_not_commercial",
            detail=(
                f"Response mode '{mode.value}' is informational; recommending a product "
                "is not justified by the user's intent."
            ),
        )
    return GateResult(passed=True)


def check_product_eligible(product: ProductReadModel, offers: list[OfferReadModel]) -> GateResult:
    """Per-product gates. Note the ORDER of checks is the order a human
    would explain them in - status first (is this even publishable),
    then purchasability."""
    if not product.is_recommendable:
        return GateResult(
            passed=False,
            failed_gate="product_not_published",
            detail=f"Product status is '{product.status.value}', not published.",
        )
    if not offers:
        return GateResult(
            passed=False, failed_gate="no_offer", detail="Product has no offer at all."
        )
    if not any(o.is_purchasable() for o in offers):
        reasons = sorted({o.availability.value for o in offers})
        return GateResult(
            passed=False,
            failed_gate="no_purchasable_offer",
            detail=f"No currently purchasable offer (availability: {', '.join(reasons)}).",
        )
    return GateResult(passed=True)


# --- Soft signals ---------------------------------------------------------


def score_relevance(
    product: ProductReadModel,
    *,
    requested_category: str | None,
    requested_brand: str | None,
    knowledge_object_id=None,
    product_interest: str | None = None,
) -> SignalResult:
    """Deterministic, additive, and explainable. No embeddings, no
    learned weights - the Phase 8 brief requires the MVP be
    deterministic and auditable, and a semantic matcher would be
    neither until a real embedding provider exists."""
    matches: list[str] = []
    score = _NEUTRAL

    if knowledge_object_id and product.knowledge_object_id == knowledge_object_id:
        score += 0.25
        matches.append("linked to the same knowledge object as the request")
    if requested_category and product.category == requested_category:
        score += 0.15
        matches.append(f"category matches '{requested_category}'")
    if requested_brand and product.brand == requested_brand:
        score += 0.10
        matches.append(f"brand matches '{requested_brand}'")
    if product_interest:
        haystack = " ".join(filter(None, [product.name, product.brand, product.category])).lower()
        if product_interest.lower() in haystack:
            score += 0.10
            matches.append(f"matches stated interest '{product_interest}'")

    score = min(score, 1.0)
    if not matches:
        return SignalResult(
            score=_NEUTRAL,
            state=SignalState.UNKNOWN,
            detail="No explicit relevance signal matched; treated as neutral, not negative.",
        )
    return SignalResult(
        score=score, state=SignalState.ESTABLISHED, detail="; ".join(matches)
    )


def score_evidence(summary: ProductEvidenceSummary | None, *, need: NeedLevel) -> SignalResult:
    """The distinction this function exists for: no evidence is
    UNKNOWN and scores neutral; rejected evidence is NEGATIVE and
    scores low. A system that conflated them would punish honesty."""
    if summary is None or not summary.has_any_record:
        return SignalResult(
            score=_NEUTRAL,
            state=SignalState.UNKNOWN,
            detail="No product evidence recorded yet - evidence not established (this is not negative evidence).",
        )

    if summary.rejected and not summary.verified:
        return SignalResult(
            score=0.1,
            state=SignalState.NEGATIVE,
            detail=f"{summary.rejected} product claim(s) were reviewed and rejected; none verified.",
        )
    if summary.rejected and summary.verified:
        return SignalResult(
            score=0.4,
            state=SignalState.CONFLICTING,
            detail=(
                f"{summary.verified} verified claim(s) but also {summary.rejected} rejected - "
                "the record is internally inconsistent."
            ),
        )
    if not summary.verified:
        unreviewed = summary.pending_review + summary.unverified
        return SignalResult(
            score=_NEUTRAL,
            state=SignalState.UNKNOWN,
            detail=(
                f"{unreviewed} product claim(s) exist but none are verified - "
                "unverified claims are never counted as evidence."
            ),
        )

    # Verified evidence present. Diminishing returns: the first
    # verified claim matters most, the fifth adds little.
    score = min(0.6 + 0.1 * summary.verified, 1.0)
    state = SignalState.ESTABLISHED if summary.verified >= 2 else SignalState.PARTIAL
    if need == NeedLevel.HIGH and summary.verified < 2:
        state = SignalState.PARTIAL
    return SignalResult(
        score=score,
        state=state,
        detail=f"{summary.verified} verified product claim(s): {', '.join(summary.verified_claims[:3])}",
    )


def score_trust(summary: TrustSummary | None, *, need: NeedLevel) -> SignalResult:
    """Same tri-state discipline as evidence: no trust record means
    trust is NOT ESTABLISHED, which is different from untrustworthy."""
    if summary is None or not summary.has_any_record:
        return SignalResult(
            score=_NEUTRAL,
            state=SignalState.UNKNOWN,
            detail="No trust record yet - trust not established (this does not mean untrustworthy).",
        )
    if summary.rejected and not summary.verified:
        return SignalResult(
            score=0.1,
            state=SignalState.NEGATIVE,
            detail=f"{summary.rejected} trust assertion(s) were reviewed and rejected.",
        )
    if summary.rejected and summary.verified:
        return SignalResult(
            score=0.4,
            state=SignalState.CONFLICTING,
            detail=f"{summary.verified} verified and {summary.rejected} rejected trust record(s).",
        )
    if not summary.verified:
        return SignalResult(
            score=_NEUTRAL,
            state=SignalState.UNKNOWN,
            detail="Trust records exist but none are verified yet.",
        )

    score = min(0.6 + 0.1 * summary.verified, 1.0)
    state = SignalState.ESTABLISHED if summary.verified >= 2 else SignalState.PARTIAL
    if need == NeedLevel.HIGH and summary.verified < 2:
        state = SignalState.PARTIAL
    types = ", ".join(sorted({t.value for t in summary.verified_trust_types})[:3])
    return SignalResult(
        score=score, state=state, detail=f"{summary.verified} verified trust record(s): {types}"
    )


def score_availability(offers: list[OfferReadModel], *, mode: ResponseMode) -> tuple[SignalResult, OfferReadModel | None]:
    """Returns the chosen offer alongside the signal, because an
    availability explanation is meaningless without saying WHICH offer
    it describes."""
    purchasable = [o for o in offers if o.is_purchasable()]
    if not purchasable:
        return (
            SignalResult(score=0.0, state=SignalState.NEGATIVE, detail="No purchasable offer."),
            None,
        )

    in_stock = [o for o in purchasable if o.availability == OfferAvailability.IN_STOCK]
    chosen_pool = in_stock or purchasable
    # Prefer a known price; among those, the lowest. An offer with no
    # price is NOT treated as cheapest - see module docstring point 2.
    priced = [o for o in chosen_pool if o.has_known_price]
    chosen = min(priced, key=lambda o: o.price) if priced else chosen_pool[0]

    if in_stock:
        score = 1.0
        detail = "In stock now."
    else:
        # PREORDER/BACKORDER are purchasable but not immediate. Under
        # TRANSACT the user wants it now, so this matters more.
        score = 0.4 if mode == ResponseMode.TRANSACT else 0.6
        detail = f"Available as {chosen.availability.value} (not immediate)."

    if not chosen.has_known_price:
        detail += " Price on request (not free)."
    return SignalResult(score=score, state=SignalState.ESTABLISHED, detail=detail), chosen


# --- Aggregation & decision ------------------------------------------------


def aggregate(relevance: SignalResult, evidence: SignalResult, trust: SignalResult, availability: SignalResult) -> float:
    total = (
        relevance.score * _WEIGHTS["relevance"]
        + evidence.score * _WEIGHTS["evidence"]
        + trust.score * _WEIGHTS["trust"]
        + availability.score * _WEIGHTS["availability"]
    )
    return round(min(max(total, 0.0), 1.0), 3)


def decide(
    *,
    final_score: float,
    evidence: SignalResult,
    trust: SignalResult,
    mode: ResponseMode,
    evidence_need: NeedLevel,
    trust_need: NeedLevel,
) -> tuple[RecommendationStatus, list[str]]:
    """Turns signals into a status plus the caveats a caller must show
    alongside it. Caveats are not decoration - they are how the system
    stays honest about a recommendation it is only partly confident in,
    instead of silently rounding up to RECOMMENDED."""
    caveats: list[str] = []

    if evidence.state == SignalState.NEGATIVE:
        caveats.append("Product claims for this item were reviewed and rejected.")
    if trust.state == SignalState.NEGATIVE:
        caveats.append("Trust assertions for this item were reviewed and rejected.")
    if evidence.state == SignalState.CONFLICTING:
        caveats.append("Evidence for this product is internally conflicting.")
    if trust.state == SignalState.CONFLICTING:
        caveats.append("Trust records for this product are internally conflicting.")
    if evidence.state == SignalState.UNKNOWN:
        caveats.append("No verified evidence has been established for this product yet.")
    if trust.state == SignalState.UNKNOWN:
        caveats.append("Trust has not been established for this product yet.")
    if evidence_need == NeedLevel.HIGH and evidence.state not in (SignalState.ESTABLISHED,):
        caveats.append("This request needs strong evidence, which is not fully established here.")
    if trust_need == NeedLevel.HIGH and trust.state not in (SignalState.ESTABLISHED,):
        caveats.append("This request needs strong trust signals, which are not fully established here.")

    # A rejected signal is never silently ranked - it always carries a
    # caveat at minimum, regardless of how good the other signals are.
    negative = SignalState.NEGATIVE in (evidence.state, trust.state)
    if negative or final_score < _CONFIDENT_THRESHOLD or caveats:
        return RecommendationStatus.RECOMMENDED_WITH_CAVEAT, caveats
    return RecommendationStatus.RECOMMENDED, caveats
