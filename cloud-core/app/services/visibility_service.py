"""
AI Visibility service (master spec §31).

THE CENTRAL DISCIPLINE OF THIS MODULE

Everything here records or summarises **observations**. Nothing here
produces a claim about the merchant's standing on a platform, because this
system cannot know that. It can know "on 3 September, this prompt to
Perplexity produced an answer that mentioned the brand and did not cite
it". It cannot know "the brand is 40% visible on Perplexity" — that would
require a representative sample of a population nobody has defined.

So `summarise()` returns counts and explicit coverage, never a percentage
presented as a rating and never a composite "visibility score". This is the
same refusal as ADR-047 (no readiness score) and ADR-059 (no score leaves
the building), for the same reason: a single number invites being quoted as
an authority it does not have. See ADR-064.

BUDGET IS CHECKED BEFORE THE PROBE, NOT AFTER

`check_budget()` runs before any paid platform call. A budget discovered to
be exceeded afterwards is an invoice, not a guard (ADR-063).
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import SignalPresence, VisibilityPlatform
from app.models.product import Product
from app.models.query import Query
from app.models.visibility import VisibilityTest
from app.models.visibility_budget import VisibilityBudget
from app.schemas.common import SortParams, apply_sort
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log

# The five signals §31 names as columns. Click and Purchase are absent by
# design — see the VisibilityTest class docstring and ADR-062.
SIGNAL_FIELDS = ("mentioned", "cited", "recommended", "product_present", "url_present")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def current_period_key(at: datetime | None = None) -> str:
    return (at or _now()).strftime("%Y-%m")


# --- Budget ----------------------------------------------------------------


def get_or_create_budget(
    db: Session, *, organization_id: UUID, period_key: str | None = None,
    default_limit: float = 0.0, currency: str = "USD",
) -> VisibilityBudget:
    """A missing budget is created with a limit of ZERO, not unlimited.

    That is the safe default and a deliberate one: an organization that has
    never configured a budget should not be able to spend. "No budget
    configured" and "unlimited budget" must never be the same state."""
    key = period_key or current_period_key()
    budget = db.execute(
        select(VisibilityBudget).where(
            VisibilityBudget.organization_id == organization_id,
            VisibilityBudget.period_key == key,
        )
    ).scalar_one_or_none()
    if budget is not None:
        return budget

    budget = VisibilityBudget(
        organization_id=organization_id, period_key=key,
        period_limit=default_limit, period_spent=0, currency=currency,
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


def set_budget(
    db: Session, *, organization_id: UUID, period_limit: float, currency: str,
    actor_user_id: UUID, period_key: str | None = None,
) -> VisibilityBudget:
    budget = get_or_create_budget(db, organization_id=organization_id, period_key=period_key)
    old = float(budget.period_limit)
    budget.period_limit = period_limit
    budget.currency = currency
    db.flush()
    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="visibility_budget.updated", resource_type="visibility_budget",
        resource_id=budget.id,
        old_value={"period_limit": old},
        new_value={"period_limit": period_limit, "currency": currency},
    )
    db.commit()
    db.refresh(budget)
    return budget


def reserve_budget(
    db: Session, *, organization_id: UUID, estimated_cost: float
) -> VisibilityBudget:
    """ATOMIC reservation (P12-16, ADR-069). Replaces read -> decide -> write.

    THE RACE THIS FIXES

    The previous implementation read `period_spent`, decided in Python, then
    wrote. Two concurrent probes each reading 0.08 against a 0.10 limit both
    concluded they fit, and both proceeded - spending 0.12. The window is
    small and the failure is silent, which is the worst combination: it only
    appears as an unexplained overspend.

    The fix is a single conditional UPDATE. The database evaluates the
    limit and applies the increment in one statement, so the second
    concurrent writer sees the first one's increment and matches zero rows.
    `rowcount == 0` therefore means "budget exhausted", not "error".

    Reservation happens BEFORE execution. A probe that fails afterwards
    releases its reservation via `release_reservation()`; the alternative -
    settling after the fact - is how a crashed worker leaks budget
    permanently.
    """
    # Ensure a row exists (limit 0 by default - never unlimited).
    get_or_create_budget(db, organization_id=organization_id)
    period_key = current_period_key()

    if estimated_cost <= 0:
        return _load_budget(db, organization_id=organization_id, period_key=period_key)

    # One statement: check and increment together. The WHERE clause is the
    # guard; Postgres evaluates it against the committed row, so concurrent
    # callers serialise on the row lock rather than on application logic.
    result = db.execute(
        update(VisibilityBudget)
        .where(
            VisibilityBudget.organization_id == organization_id,
            VisibilityBudget.period_key == period_key,
            (VisibilityBudget.period_spent + estimated_cost) <= VisibilityBudget.period_limit,
        )
        .values(period_spent=VisibilityBudget.period_spent + estimated_cost)
    )

    if result.rowcount == 0:
        db.rollback()
        current = _load_budget(db, organization_id=organization_id, period_key=period_key)
        raise HTTPException(
            status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Visibility budget for {period_key} would be exceeded "
                f"({current.period_spent} + {estimated_cost} > {current.period_limit} "
                f"{current.currency}). No probe was performed and nothing was reserved."
            ),
        )

    db.flush()
    return _load_budget(db, organization_id=organization_id, period_key=period_key)


def release_reservation(
    db: Session, *, organization_id: UUID, amount: float, period_key: str | None = None
) -> None:
    """Returns an unspent reservation after a failed probe.

    `GREATEST(0, ...)` guards the floor: a double release must not drive
    `period_spent` negative, which would silently grant free budget."""
    if amount <= 0:
        return
    key = period_key or current_period_key()
    db.execute(
        update(VisibilityBudget)
        .where(
            VisibilityBudget.organization_id == organization_id,
            VisibilityBudget.period_key == key,
        )
        .values(period_spent=func.greatest(0, VisibilityBudget.period_spent - amount))
    )
    db.flush()


def settle_reservation(
    db: Session, *, organization_id: UUID, reserved: float, actual: float,
    period_key: str | None = None,
) -> None:
    """Adjusts a reservation to the real cost once known.

    `estimated_cost == actual_cost` is NOT assumed (P12-16). A provider that
    charges less than estimated must return the difference; one that charges
    more must consume it, even past the limit - the money is already spent,
    and hiding it would make the ledger disagree with the invoice."""
    delta = float(actual) - float(reserved)
    if delta == 0:
        return
    key = period_key or current_period_key()
    db.execute(
        update(VisibilityBudget)
        .where(
            VisibilityBudget.organization_id == organization_id,
            VisibilityBudget.period_key == key,
        )
        .values(period_spent=func.greatest(0, VisibilityBudget.period_spent + delta))
    )
    db.flush()


def _load_budget(db: Session, *, organization_id: UUID, period_key: str) -> VisibilityBudget:
    budget = db.execute(
        select(VisibilityBudget).where(
            VisibilityBudget.organization_id == organization_id,
            VisibilityBudget.period_key == period_key,
        )
    ).scalar_one()
    db.refresh(budget)
    return budget


def check_budget(db: Session, *, organization_id: UUID, estimated_cost: float) -> VisibilityBudget:
    """Backwards-compatible alias. Reserves atomically (ADR-069)."""
    return reserve_budget(
        db, organization_id=organization_id, estimated_cost=estimated_cost
    )


# --- Observations ------------------------------------------------------------


def _assert_reference_belongs_to_tenant(
    db: Session, *, model, object_id: UUID | None, organization_id: UUID, label: str
) -> None:
    """Validates a referenced object's tenant BEFORE insert.

    The composite FK (ADR-037) already makes a cross-tenant reference
    impossible at the database level — it fires correctly and is the real
    guarantee. But letting it fire produces an unhandled `IntegrityError`
    escaping as a 500, which tells an API caller nothing and looks like a
    server fault rather than their mistake.

    So this is defence in depth in the useful direction: the service
    produces a clean, specific 404, and the constraint remains underneath as
    the thing that is actually load-bearing. A 404 rather than a 403,
    matching the project's convention of not confirming that another
    tenant's object exists."""
    if object_id is None:
        return
    exists = db.execute(
        select(model.id).where(model.id == object_id, model.organization_id == organization_id)
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"{label} not found",
        )


def record_observation(
    db: Session, *, organization_id: UUID, actor_user_id: UUID | None, **fields
) -> VisibilityTest:
    """Records one observation, after a budget check.

    Note `tested_at` is required from the caller rather than defaulted to
    now(): an observation pasted from a session yesterday happened
    yesterday, and silently stamping it with the import time would corrupt
    every time series built on this table."""
    _assert_reference_belongs_to_tenant(
        db, model=Query, object_id=fields.get("query_id"),
        organization_id=organization_id, label="Query",
    )
    _assert_reference_belongs_to_tenant(
        db, model=Product, object_id=fields.get("product_id"),
        organization_id=organization_id, label="Product",
    )

    estimated_cost = float(fields.get("estimated_cost") or 0)
    # Reservation increments spend atomically; there is no second write.
    reserve_budget(db, organization_id=organization_id, estimated_cost=estimated_cost)

    observation = VisibilityTest(organization_id=organization_id, **fields)
    db.add(observation)
    try:
        db.flush()
    except IntegrityError:
        # The composite FK caught something the service check did not.
        # Roll back and report it rather than letting a 500 escape.
        db.rollback()
        # The reservation is released: the probe did not happen, so the
        # budget must not be consumed by a rejected write.
        release_reservation(db, organization_id=organization_id, amount=estimated_cost)
        db.commit()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Observation references an object that does not belong to this organization.",
        ) from None

    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="visibility_observation.recorded", resource_type="visibility_test",
        resource_id=observation.id,
        new_value={
            "platform": observation.platform.value,
            "collection_method": observation.collection_method.value,
            "estimated_cost": estimated_cost or None,
        },
    )
    db.commit()
    db.refresh(observation)
    return observation


def list_observations(
    db: Session, *, organization_id: UUID, platform: VisibilityPlatform | None,
    query_id: UUID | None, product_id: UUID | None,
    limit: int, offset: int, sort: SortParams | None = None,
) -> tuple[list[VisibilityTest], int]:
    base = select(VisibilityTest).where(VisibilityTest.organization_id == organization_id)
    if platform:
        base = base.where(VisibilityTest.platform == platform)
    if query_id:
        base = base.where(VisibilityTest.query_id == query_id)
    if product_id:
        base = base.where(VisibilityTest.product_id == product_id)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    from app.schemas.common import SortDirection

    rows = db.execute(
        apply_sort(base, VisibilityTest, sort, "tested_at", SortDirection.DESC)
        .limit(limit).offset(offset)
    ).scalars().all()
    return list(rows), total


def get_observation_or_404(db: Session, *, observation_id: UUID, organization_id: UUID) -> VisibilityTest:
    return get_tenant_scoped_or_404(
        db, VisibilityTest, observation_id, organization_id=organization_id,
        not_found_message="Visibility observation not found",
    )


# --- Summary (counts, never a score) --------------------------------------------


def summarise(
    db: Session, *, organization_id: UUID, platform: VisibilityPlatform | None = None,
    since: datetime | None = None,
) -> dict:
    """Counts per signal, split three ways, plus explicit coverage.

    The three-way split is the whole point. A signal reported as
    `present: 3, absent: 1` out of 10 observations is NOT 30% — seven
    observations never examined that signal, and folding them into a
    denominator would invent a number. So the caller receives all three
    counts and the checked total, and any ratio it forms is its own
    decision made with full information.

    There is deliberately NO overall score, NO percentage, and NO ranking.
    """
    base = select(VisibilityTest).where(VisibilityTest.organization_id == organization_id)
    if platform:
        base = base.where(VisibilityTest.platform == platform)
    if since:
        base = base.where(VisibilityTest.tested_at >= since)

    observations = db.execute(base).scalars().all()
    total = len(observations)

    signals: dict[str, dict] = {}
    for field in SIGNAL_FIELDS:
        present = sum(1 for o in observations if getattr(o, field) == SignalPresence.PRESENT)
        absent = sum(1 for o in observations if getattr(o, field) == SignalPresence.ABSENT)
        not_checked = sum(1 for o in observations if getattr(o, field) == SignalPresence.NOT_CHECKED)
        signals[field] = {
            "present": present,
            "absent": absent,
            "not_checked": not_checked,
            # The honest denominator: only observations that actually
            # examined this signal.
            "checked": present + absent,
        }

    by_method: dict[str, int] = {}
    for o in observations:
        by_method[o.collection_method.value] = by_method.get(o.collection_method.value, 0) + 1

    caveats: list[str] = []
    if total == 0:
        caveats.append("No observations recorded for this period. This is not evidence of absence.")
    else:
        caveats.append(
            "These are counts of individual observations, not a measure of overall visibility. "
            "They describe the prompts that were run, not the platform as a whole."
        )
        unchecked = [f for f in SIGNAL_FIELDS if signals[f]["checked"] == 0]
        if unchecked:
            caveats.append(
                f"No observation examined: {', '.join(unchecked)}. Nothing is known about "
                "these signals either way."
            )
        if by_method.get("manual_paste", 0) == total and total > 0:
            caveats.append(
                "All observations were entered manually, so coverage reflects what a human "
                "happened to check rather than a systematic sample."
            )

    return {
        "observation_count": total,
        "signals": signals,
        "by_collection_method": by_method,
        "caveats": caveats,
        "as_of": _now(),
    }
