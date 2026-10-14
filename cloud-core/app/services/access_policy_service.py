"""
AI access policy service (Phase 13, ADR-077).

Two jobs: keep the rule table well-formed, and evaluate it deterministically.

EVALUATION IS THE PART THAT MUST NOT BE CLEVER

`evaluate()` walks four precedence levels, most specific first, and
returns on the first hit. No scoring, no union, no "most restrictive
wins". A merchant must be able to look at the table and predict what
happens to GPTBot, and any algorithm that combines rows destroys that.

The four levels, and the `specificity` integer that materialises them:

    30  agent + purpose
    20  agent, any purpose
    10  actor_type + purpose
     5  actor_type, any purpose

`specificity` is computed by `_specificity()` and written on every save.
It is never accepted from a client — a caller that could set it could
reorder the whole policy table by sending a number.

DEFAULT IS ALLOW, AND IT SAYS SO

No match returns `NOT_CONFIGURED`, not `ALLOWED`. Both let the request
through; only one of them is honest about the fact that nobody decided.
The dashboard shows the count of not-configured agents precisely so this
state is visible and finite, rather than an invisible default that quietly
becomes policy.
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.access_policy import AccessPolicy
from app.models.ai_agent import AiAgent
from app.models.enums import AccessDecision, AccessPurpose, AccessTier, ActorType
from app.schemas.common import SortParams, apply_sort

_SPEC_AGENT_PURPOSE = 30
_SPEC_AGENT_ANY = 20
_SPEC_TYPE_PURPOSE = 10
_SPEC_TYPE_ANY = 5


@dataclass(frozen=True)
class Evaluation:
    """The answer, plus everything needed to explain it.

    `matched_policy_id` is nullable and `reason` is human text, because
    "why was I blocked?" is a question an agent operator will ask and a
    merchant will be asked. A decision with no explanation is a support
    ticket.
    """

    decision: AccessDecision
    tier: AccessTier
    matched_policy_id: UUID | None
    reason: str | None
    terms_url: str | None
    http_status: int

    @property
    def is_allowed(self) -> bool:
        return self.decision in (AccessDecision.ALLOWED, AccessDecision.NOT_CONFIGURED)


_TIER_TO_DECISION = {
    AccessTier.FREE: (AccessDecision.ALLOWED, 200),
    AccessTier.PAID: (AccessDecision.PAYMENT_REQUIRED, 402),
    AccessTier.FORBIDDEN: (AccessDecision.BLOCKED, 403),
    # A rule that exists but has not been decided must behave exactly like
    # no rule at all. Treating UNSET as FREE would let "I created the row
    # but haven't chosen yet" read as "I allowed it".
    AccessTier.UNSET: (AccessDecision.NOT_CONFIGURED, 200),
}


def _specificity(agent_id: UUID | None, purpose: AccessPurpose | None) -> int:
    if agent_id is not None:
        return _SPEC_AGENT_PURPOSE if purpose is not None else _SPEC_AGENT_ANY
    return _SPEC_TYPE_PURPOSE if purpose is not None else _SPEC_TYPE_ANY


def validate_rule(*, agent_id: UUID | None, actor_type: ActorType | None) -> None:
    """Exactly one subject. Enforced here rather than as a CHECK constraint
    because the rule is about which of two nullable columns is populated,
    and expressing it in SQL duplicates knowledge that belongs in one
    place. Tested directly, including both failure directions."""
    if agent_id is None and actor_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A policy must name either an agent_id or an actor_type.",
        )
    if agent_id is not None and actor_type is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "A policy names either a specific agent or a whole actor type, "
                "never both. Two subjects on one rule makes precedence ambiguous."
            ),
        )


def upsert_policy(
    db: Session,
    *,
    organization_id: UUID,
    agent_id: UUID | None,
    actor_type: ActorType | None,
    purpose: AccessPurpose | None,
    tier: AccessTier,
    reason: str | None = None,
    terms_url: str | None = None,
    updated_by_user_id: UUID | None = None,
) -> AccessPolicy:
    validate_rule(agent_id=agent_id, actor_type=actor_type)

    if agent_id is not None:
        # Cross-tenant guard at the service layer. The composite FK
        # enforces it at SQL level too (ADR-037 pattern); both exist so a
        # future code path that bypasses this function still cannot write
        # a cross-tenant rule.
        agent = db.get(AiAgent, agent_id)
        if agent is None or agent.organization_id != organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
            )

    existing = db.execute(
        select(AccessPolicy).where(
            AccessPolicy.organization_id == organization_id,
            AccessPolicy.agent_id.is_(agent_id) if agent_id is None else AccessPolicy.agent_id == agent_id,
            AccessPolicy.actor_type.is_(actor_type) if actor_type is None else AccessPolicy.actor_type == actor_type,
            AccessPolicy.purpose.is_(purpose) if purpose is None else AccessPolicy.purpose == purpose,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.tier = tier
        existing.reason = reason
        existing.terms_url = terms_url
        existing.updated_by_user_id = updated_by_user_id
        existing.specificity = _specificity(agent_id, purpose)
        db.flush()
        return existing

    policy = AccessPolicy(
        organization_id=organization_id,
        agent_id=agent_id,
        actor_type=actor_type,
        purpose=purpose,
        tier=tier,
        reason=reason,
        terms_url=terms_url,
        updated_by_user_id=updated_by_user_id,
        specificity=_specificity(agent_id, purpose),
    )
    db.add(policy)
    db.flush()
    return policy


def evaluate(
    db: Session,
    *,
    organization_id: UUID,
    agent_id: UUID | None,
    actor_type: ActorType,
    purpose: AccessPurpose,
) -> Evaluation:
    """Resolve one request against the policy table.

    Humans are never subject to an access policy. That is not a special
    case bolted on: the whole table is about machine access, and a rule
    that could accidentally 403 a customer's browser is a foot-gun with no
    upside. A merchant who wants to block human traffic has a firewall.
    """
    if actor_type == ActorType.HUMAN:
        return Evaluation(
            decision=AccessDecision.ALLOWED,
            tier=AccessTier.FREE,
            matched_policy_id=None,
            reason=None,
            terms_url=None,
            http_status=200,
        )

    # (is_agent_rule, subject clause, purpose clause), most specific first.
    # DEFECT FIXED (final existing-owner closure pass, owner Phase 13): this
    # used to test `subject_clause.left is AccessPolicy.agent_id`, but a SQL
    # expression's `.left` is the underlying Column, never the ORM attribute,
    # so the identity test was always False and every agent-level candidate
    # also got `agent_id IS NULL` — an impossible filter. Agent-specific
    # rules therefore NEVER matched: "block all AI crawlers except X" was
    # impossible, and — worse — a rule blocking one named agent under a
    # permissive type rule silently let that agent through.
    candidates = [
        (True, AccessPolicy.agent_id == agent_id, AccessPolicy.purpose == purpose) if agent_id else None,
        (True, AccessPolicy.agent_id == agent_id, AccessPolicy.purpose.is_(None)) if agent_id else None,
        (False, AccessPolicy.actor_type == actor_type, AccessPolicy.purpose == purpose),
        (False, AccessPolicy.actor_type == actor_type, AccessPolicy.purpose.is_(None)),
    ]

    for clause in candidates:
        if clause is None:
            continue
        is_agent_rule, subject_clause, purpose_clause = clause
        stmt = select(AccessPolicy).where(
            AccessPolicy.organization_id == organization_id,
            subject_clause,
            purpose_clause,
        )
        # agent-level rules must not match a type-level row and vice versa
        if is_agent_rule:
            stmt = stmt.where(AccessPolicy.actor_type.is_(None))
        else:
            stmt = stmt.where(AccessPolicy.agent_id.is_(None))

        policy = db.execute(stmt.limit(1)).scalar_one_or_none()
        if policy is None:
            continue

        decision, http_status = _TIER_TO_DECISION[policy.tier]
        return Evaluation(
            decision=decision,
            tier=policy.tier,
            matched_policy_id=policy.id,
            reason=policy.reason,
            terms_url=policy.terms_url,
            http_status=http_status,
        )

    return Evaluation(
        decision=AccessDecision.NOT_CONFIGURED,
        tier=AccessTier.UNSET,
        matched_policy_id=None,
        reason=None,
        terms_url=None,
        http_status=200,
    )


def list_policies(
    db: Session,
    *,
    organization_id: UUID,
    limit: int = 50,
    offset: int = 0,
    sort: SortParams | None = None,
) -> tuple[list[AccessPolicy], int]:
    from sqlalchemy import func

    stmt = select(AccessPolicy).where(AccessPolicy.organization_id == organization_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, AccessPolicy, sort, default_field="specificity")
    return list(db.execute(stmt.limit(limit).offset(offset)).scalars().all()), total


def delete_policy(db: Session, *, policy: AccessPolicy) -> None:
    """Deleting a rule does not rewrite history. `page_views.matched_policy_id`
    is deliberately not a foreign key, so past decisions keep naming the
    rule that made them even after the rule is gone."""
    db.delete(policy)
