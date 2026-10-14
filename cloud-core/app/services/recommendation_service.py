"""
Recommendation service — ORCHESTRATION ONLY (master spec section 33).

This module contains no business rules of its own. Every judgment it
makes is delegated:

- **What products exist and which are recommendable** -> the Commerce
  read contract (`app/contracts/commerce.py`), owned by Phase 7. This
  module never writes a `select()` against products, offers,
  product_evidence or trust_records.
- **What is eligible and how to score it** -> `recommendation_policy`,
  a pure-function module with no database access.
- **Tenant scoping** -> the contract functions, every one of which
  requires an organization_id and has no way to disable it.

That division is the point: if Phase 7 adds a Product field, this file
does not change. If the scoring weights change, only the policy module
changes. If the ranking algorithm is replaced entirely, Phase 7 is
untouched. The Phase 8 brief's Scenarios A-E are answered by this
structure rather than by a promise.

`recommend` always returns a complete answer, including when that
answer is "nothing" - a NO_RECOMMENDATION with an explanation is a
successful response, not an error. Rejected candidates are returned
alongside accepted ones so the caller can answer "why NOT that
product", which is a question a recommendation system that discards
rejections structurally cannot answer.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.contracts import commerce as commerce_contract
from app.models.customer_context import CustomerContext
from app.models.enums import NeedLevel, RecommendationStatus, ResponseMode
from app.models.recommendation import Recommendation
from app.security.tenant import get_tenant_scoped_or_404
from app.services import recommendation_policy as policy
from app.services.audit import record_audit_log


def _signal_dict(signal: policy.SignalResult) -> dict:
    return {"score": signal.score, "state": signal.state.value, "detail": signal.detail}


def recommend(
    db: Session,
    *,
    organization_id: UUID,
    response_mode: ResponseMode,
    customer_context: CustomerContext | None,
    query_id: UUID | None,
    knowledge_object_id: UUID | None,
    category: str | None,
    brand: str | None,
    product_ids: list[UUID] | None,
    limit: int,
    persist: bool,
    actor_user_id: UUID,
) -> tuple[RecommendationStatus, str, list[Recommendation], list[dict]]:
    """Returns (overall_status, explanation, recommendations, rejected)."""

    # --- Request-level hard gates. Checked BEFORE any candidate work,
    # because if the request itself isn't eligible, evaluating products
    # would be wasted effort and - worse - would produce scores that
    # look like a real ranking.
    consent_gate = policy.check_consent(
        customer_context.consent_status if customer_context else None
    )
    if not consent_gate.passed:
        return RecommendationStatus.NO_RECOMMENDATION, consent_gate.detail, [], []

    mode_gate = policy.check_response_mode(response_mode)
    if not mode_gate.passed:
        return RecommendationStatus.NO_RECOMMENDATION, mode_gate.detail, [], []

    evidence_need = customer_context.evidence_need if customer_context else NeedLevel.NORMAL
    trust_need = customer_context.trust_need if customer_context else NeedLevel.NORMAL
    product_interest = customer_context.product_interest if customer_context else None

    # --- Candidate generation, entirely through the Commerce contract.
    # include_non_recommendable=True on purpose: unpublished products
    # are fetched so they can be REJECTED VISIBLY by a named gate,
    # rather than vanishing with no explanation.
    candidates = commerce_contract.find_candidate_products(
        db,
        organization_id=organization_id,
        category=category,
        brand=brand,
        knowledge_object_id=knowledge_object_id,
        product_ids=product_ids,
        include_non_recommendable=True,
        limit=max(limit * 5, 50),
    )
    if not candidates:
        return (
            RecommendationStatus.NO_RECOMMENDATION,
            "No products matched the request's constraints.",
            [],
            [],
        )

    candidate_ids = [c.id for c in candidates]
    offers_by_product = commerce_contract.get_offers_for_products(
        db, product_ids=candidate_ids, organization_id=organization_id
    )
    evidence_by_product = commerce_contract.get_evidence_summaries(
        db, product_ids=candidate_ids, organization_id=organization_id
    )
    trust_by_product = commerce_contract.get_trust_summaries(
        db, subject_ids=candidate_ids, organization_id=organization_id
    )

    decisions: list[policy.ProductDecision] = []
    rejected: list[dict] = []

    for product in candidates:
        offers = offers_by_product.get(product.id, [])
        gate = policy.check_product_eligible(product, offers)
        if not gate.passed:
            rejected.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "failed_gate": gate.failed_gate,
                    "detail": gate.detail,
                }
            )
            continue

        relevance = policy.score_relevance(
            product,
            requested_category=category,
            requested_brand=brand,
            knowledge_object_id=knowledge_object_id,
            product_interest=product_interest,
        )
        evidence = policy.score_evidence(evidence_by_product.get(product.id), need=evidence_need)
        trust = policy.score_trust(trust_by_product.get(product.id), need=trust_need)
        availability, chosen_offer = policy.score_availability(offers, mode=response_mode)

        final_score = policy.aggregate(relevance, evidence, trust, availability)
        status, caveats = policy.decide(
            final_score=final_score,
            evidence=evidence,
            trust=trust,
            mode=response_mode,
            evidence_need=evidence_need,
            trust_need=trust_need,
        )
        decisions.append(
            policy.ProductDecision(
                product=product,
                offer=chosen_offer,
                status=status,
                relevance=relevance,
                evidence=evidence,
                trust=trust,
                availability=availability,
                final_score=final_score,
                caveats=caveats,
            )
        )

    if not decisions:
        return (
            RecommendationStatus.NO_RECOMMENDATION,
            "Candidate products existed, but none passed eligibility (see rejected list).",
            [],
            rejected,
        )

    # Deterministic ordering: score first, then product id as a stable
    # tiebreak so identical inputs always produce identical output -
    # required for the reproducibility guarantee.
    decisions.sort(key=lambda d: (-d.final_score, str(d.product.id)))
    decisions = decisions[:limit]

    now = datetime.now(timezone.utc)
    rows: list[Recommendation] = []
    for decision in decisions:
        reason = {
            "primary_reason": decision.relevance.detail,
            "relevance": _signal_dict(decision.relevance),
            "evidence": _signal_dict(decision.evidence),
            "trust": _signal_dict(decision.trust),
            "availability": _signal_dict(decision.availability),
            "caveats": decision.caveats,
            "rejected_by_gate": None,
            "policy_version": policy.POLICY_VERSION,
        }
        # id/timestamps are assigned here rather than left to the
        # database defaults, because a `persist=False` evaluation never
        # reaches a flush and would otherwise hand back objects with a
        # null id and null created_at. Both paths now produce complete,
        # serialisable rows; persisting simply also writes them.
        row = Recommendation(
            id=uuid4(),
            created_at=now,
            updated_at=now,
            organization_id=organization_id,
            customer_context_id=customer_context.id if customer_context else None,
            product_id=decision.product.id,
            offer_id=decision.offer.id if decision.offer else None,
            query_id=query_id,
            knowledge_object_id=decision.product.knowledge_object_id or knowledge_object_id,
            response_mode=response_mode,
            relevance_score=decision.relevance.score,
            evidence_score=decision.evidence.score,
            trust_score=decision.trust.score,
            availability_score=decision.availability.score,
            final_score=decision.final_score,
            evidence_state=decision.evidence.state,
            trust_state=decision.trust.state,
            reason=reason,
            status=decision.status,
            policy_version=policy.POLICY_VERSION,
        )
        rows.append(row)

    if persist:
        for row in rows:
            db.add(row)
        db.flush()
        record_audit_log(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="recommendation.generated",
            resource_type="recommendation_batch",
            resource_id=None,
            new_value={
                "response_mode": response_mode.value,
                "policy_version": policy.POLICY_VERSION,
                "recommended": len(rows),
                "rejected": len(rejected),
            },
        )
        db.commit()
        for row in rows:
            db.refresh(row)

    overall = (
        RecommendationStatus.RECOMMENDED
        if any(r.status == RecommendationStatus.RECOMMENDED for r in rows)
        else RecommendationStatus.RECOMMENDED_WITH_CAVEAT
    )
    explanation = (
        f"{len(rows)} product(s) evaluated as recommendable under response mode "
        f"'{response_mode.value}'; {len(rejected)} rejected by eligibility gates."
    )
    return overall, explanation, rows, rejected


def list_recommendations(
    db: Session,
    *,
    organization_id: UUID,
    customer_context_id: UUID | None,
    product_id: UUID | None,
    status: RecommendationStatus | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Recommendation], int]:
    base = select(Recommendation).where(Recommendation.organization_id == organization_id)
    if customer_context_id:
        base = base.where(Recommendation.customer_context_id == customer_context_id)
    if product_id:
        base = base.where(Recommendation.product_id == product_id)
    if status:
        base = base.where(Recommendation.status == status)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, Recommendation, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_recommendation_or_404(db: Session, *, recommendation_id: UUID, organization_id: UUID) -> Recommendation:
    return get_tenant_scoped_or_404(
        db, Recommendation, recommendation_id, organization_id=organization_id,
        not_found_message="Recommendation not found",
    )
