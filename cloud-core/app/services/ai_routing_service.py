"""
Routing engine (REQ-AIC-003, ADR-089). Six modes, one explainable decision.

    manual_single   exactly one step; never falls back.
    manual_chain    user order; advances only when the current resource STOPS
                    (runtime exclusion) — no proactive skipping on health.
    stage_manual    the steps configured for the requested stage, in order.
    auto_pool       system picks among eligible steps: healthiest, fewest
                    recent failures, cheapest configured price, least recently used.
    priority_pool   user order, but ineligible resources (unhealthy, quota,
                    rate-limited, spend limit, capability mismatch) are skipped
                    up front.
    hybrid          stage-specific manual rules first (eligibility-filtered),
                    then the rest of the pool ranked as auto_pool.

Every candidate appears in the explanation with a verdict and reason, and the
decision is persisted (ai_routing_decisions) — never opaque.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.pricing import ConfiguredPricing
from app.models.ai_center import AIModel, AIProvider, AIProviderAccount, AIRoutingDecision, AIRoutingPolicy, AIRoutingStep
from app.models.ai_execution import AIExecution
from app.services.ai_center_service import adapter_class

HEALTH_RANK = {"healthy": 0, "unknown": 1, "degraded": 2}


@dataclass
class Candidate:
    step: AIRoutingStep
    account: AIProviderAccount
    provider: AIProvider
    verdict: str = "eligible"
    reason: str = ""


@dataclass
class Decision:
    chosen: Candidate | None
    explanation: list[dict] = field(default_factory=list)
    stop_reason: str | None = None     # set when nothing can run
    decision_id: UUID | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _month_spend(db: Session, account: AIProviderAccount) -> Decimal:
    start = _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    v = db.execute(select(func.sum(AIExecution.estimated_provider_cost)).where(
        AIExecution.organization_id == account.organization_id, AIExecution.provider_account_id == account.id,
        AIExecution.started_at >= start)).scalar_one()
    return Decimal(v or 0)


def _hard_blocks(c: Candidate, excluded: set, forbidden: set | None = None) -> str | None:
    """Reasons no mode may ignore."""
    if forbidden and c.account.id in forbidden:
        return "not allowed for background processing by the tenant's policy (connected is not enabled)"
    if c.account.id in excluded:
        return "stopped earlier in this job"
    if not c.account.enabled:
        return "account disabled"
    if not c.account.credential_ciphertext:
        return "no credential stored"
    if adapter_class(c.provider.adapter_key) is None:
        return f"no adapter implemented for provider '{c.provider.name}'"
    return None


def _soft_blocks(db: Session, c: Candidate, capability: str | None) -> str | None:
    """Eligibility filters used by the automatic / priority / hybrid modes."""
    a = c.account
    if a.health_status in ("auth_failed", "disconnected"):
        return f"health is {a.health_status}"
    if a.unavailable_until and a.unavailable_until > _now():
        return f"{a.health_status} until {a.unavailable_until.isoformat(timespec='seconds')}"
    need = capability or c.step.required_capability
    if need:
        model = db.execute(select(AIModel).where(AIModel.organization_id == a.organization_id,
                                                 AIModel.provider_id == c.provider.id, AIModel.name == c.step.model)).scalar_one_or_none()
        if model is None:
            return f"capability '{need}' unknown: model '{c.step.model}' is not registered"
        if need not in (model.capabilities or []):
            return f"model '{c.step.model}' lacks capability '{need}'"
    if a.spend_limit is not None and _month_spend(db, a) >= Decimal(str(a.spend_limit)):
        return "monthly spend limit reached"
    return None


def _price_key(c: Candidate) -> Decimal:
    price = ConfiguredPricing().price(c.provider.adapter_key or c.provider.canonical_name, c.step.model)
    return (price.input_per_mtok + price.output_per_mtok) if price else Decimal("Infinity")


def _pool_rank(c: Candidate):  # noqa: ANN202
    last = c.account.last_used_at.timestamp() if c.account.last_used_at else 0
    return (HEALTH_RANK.get(c.account.health_status, 3), c.account.failure_count, _price_key(c), last, c.step.position)


def decide(db: Session, *, organization_id: UUID, policy: AIRoutingPolicy, stage: str | None = None,
           capability: str | None = None, excluded: set | None = None, job_key: str | None = None,
           job_cost_so_far: Decimal | None = None, trigger: str = "initial", persist: bool = True,
           forbidden: set | None = None) -> Decision:
    excluded = excluded or set()
    steps = db.execute(select(AIRoutingStep).where(AIRoutingStep.organization_id == organization_id,
                                                   AIRoutingStep.policy_id == policy.id).order_by(AIRoutingStep.position)).scalars().all()
    cands = []
    for s in steps:
        a = db.get(AIProviderAccount, s.account_id)
        cands.append(Candidate(step=s, account=a, provider=db.get(AIProvider, a.provider_id)))
    mode = policy.mode
    decision = Decision(chosen=None)

    if policy.max_cost_per_job is not None and job_cost_so_far is not None and job_cost_so_far >= Decimal(str(policy.max_cost_per_job)):
        decision.stop_reason = "SPEND_LIMIT"
        for c in cands:
            c.verdict, c.reason = "skipped", "job cost limit reached"
    else:
        if mode == "manual_single":
            pool = cands[:1]
            for c in cands[1:]:
                c.verdict, c.reason = "not_considered", "manual single uses only the first step"
        elif mode == "stage_manual":
            pool = [c for c in cands if c.step.stage == stage]
            for c in cands:
                if c.step.stage != stage:
                    c.verdict, c.reason = "not_considered", f"configured for stage '{c.step.stage}'"
        else:
            pool = list(cands)

        use_soft = mode in ("auto_pool", "priority_pool", "hybrid")
        eligible = []
        for c in pool:
            reason = _hard_blocks(c, excluded, forbidden) or (_soft_blocks(db, c, capability) if use_soft else None)
            if reason:
                c.verdict, c.reason = "skipped", reason
            else:
                eligible.append(c)

        if mode == "auto_pool":
            eligible.sort(key=_pool_rank)
        elif mode == "hybrid":
            staged = [c for c in eligible if c.step.stage and c.step.stage == stage]
            rest = sorted([c for c in eligible if c not in staged and not (c.step.stage and c.step.stage != stage)], key=_pool_rank)
            for c in eligible:
                if c not in staged and c not in rest:
                    c.verdict, c.reason = "not_considered", f"manual rule for stage '{c.step.stage}'"
            eligible = staged + rest

        if eligible:
            decision.chosen = eligible[0]
            eligible[0].verdict = "chosen"
            eligible[0].reason = {
                "manual_single": "the single configured resource",
                "manual_chain": "first resource in your order that has not stopped",
                "stage_manual": f"configured for stage '{stage}'",
                "auto_pool": "best ranked: health, recent failures, price, least recently used",
                "priority_pool": "highest priority resource that passed every eligibility check",
                "hybrid": (f"stage rule for '{stage}'" if eligible[0].step.stage == stage else "best ranked in the pool after stage rules"),
            }[mode]
            for c in eligible[1:]:
                c.verdict, c.reason = "standby", "eligible, lower in order"
        else:
            decision.stop_reason = "PROVIDER_UNAVAILABLE" if pool else "UNKNOWN"

    decision.explanation = [{"position": c.step.position, "stage": c.step.stage, "account_id": str(c.account.id),
                             "account": c.account.label, "provider": c.provider.name, "model": c.step.model,
                             "verdict": c.verdict, "reason": c.reason} for c in cands]
    if persist:
        row = AIRoutingDecision(organization_id=organization_id, policy_id=policy.id, job_key=job_key, stage=stage, mode=mode,
                                chosen_account_id=decision.chosen.account.id if decision.chosen else None,
                                chosen_model=decision.chosen.step.model if decision.chosen else None,
                                trigger=trigger, explanation=decision.explanation)
        db.add(row)
        db.commit()
        decision.decision_id = row.id
    return decision
