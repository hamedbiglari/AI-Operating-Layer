"""
Budget reservation concurrency (P12-16, ADR-069).

The defect: `check_budget` read `period_spent`, decided in Python, then
wrote. Two concurrent probes each reading 0.08 against a 0.10 limit both
concluded they fit, and both proceeded — spending 0.12.

WHY THESE TESTS DO NOT USE THE `client` FIXTURE

The shared `db_session` fixture wraps everything in an outer transaction
that is rolled back and never committed. Separate threads cannot see
uncommitted rows, and they block on the locks that transaction holds — the
first version of this file deadlocked for exactly that reason.

Real concurrency needs really committed data, so these tests manage their
own engine, commit their own fixtures, and clean up after themselves. A
test that serialised the two callers instead would pass against the broken
implementation and prove nothing.
"""

import threading
import uuid as uuid_module

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.organization import Organization
from app.models.visibility_budget import VisibilityBudget
from app.services import visibility_service

TIMEOUT = 20


@pytest.fixture()
def committed_org():
    """A real, committed organization plus budget row, removed afterwards."""
    engine = create_engine(get_settings().DATABASE_URL, future=True, pool_size=15, max_overflow=15)
    Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    organization_id = uuid_module.uuid4()

    with Session() as session:
        session.add(Organization(
            id=organization_id,
            name=f"concurrency-{organization_id.hex[:8]}",
            slug=f"concurrency-{organization_id.hex[:8]}",
        ))
        session.commit()

    yield organization_id, Session

    with Session() as cleanup:
        cleanup.execute(
            text("DELETE FROM organizations WHERE id = :oid"), {"oid": str(organization_id)}
        )
        cleanup.commit()
    engine.dispose()


def _set_limit(Session, organization_id, limit: float) -> None:
    with Session() as session:
        visibility_service.get_or_create_budget(session, organization_id=organization_id)
        session.query(VisibilityBudget).filter(
            VisibilityBudget.organization_id == organization_id
        ).update({"period_limit": limit})
        session.commit()


def _spent(Session, organization_id) -> float:
    with Session() as session:
        return float(
            visibility_service.get_or_create_budget(
                session, organization_id=organization_id
            ).period_spent
        )


def _run_concurrently(Session, organization_id, amount: float, workers: int) -> list[str]:
    outcomes: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(workers)

    def attempt() -> None:
        try:
            barrier.wait(timeout=TIMEOUT)
        except threading.BrokenBarrierError:  # pragma: no cover
            return
        with Session() as session:
            try:
                visibility_service.reserve_budget(
                    session, organization_id=organization_id, estimated_cost=amount
                )
                session.commit()
                with lock:
                    outcomes.append("granted")
            except Exception:
                session.rollback()
                with lock:
                    outcomes.append("refused")

    threads = [threading.Thread(target=attempt, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=TIMEOUT)
    return outcomes


@pytest.mark.timeout(60) if hasattr(pytest.mark, "timeout") else (lambda f: f)
def test_two_concurrent_reservations_cannot_both_win(committed_org) -> None:
    """THE race test.

    Arithmetic chosen so that exactly one reservation can fit:
        limit 0.10, already spent 0.04, two concurrent 0.04 reservations
        one  -> 0.04 + 0.04 = 0.08 <= 0.10   fits
        both -> 0.04 + 0.08 = 0.12 >  0.10   does not

    (The first draft used 0.08 spent, leaving only 0.02 — under which
    *neither* 0.04 reservation fits, and the correct implementation refused
    both. The test was wrong, not the code.)

    The broken read->decide->write implementation granted both."""
    organization_id, Session = committed_org
    _set_limit(Session, organization_id, 0.10)

    with Session() as session:
        visibility_service.reserve_budget(
            session, organization_id=organization_id, estimated_cost=0.04
        )
        session.commit()

    outcomes = _run_concurrently(Session, organization_id, 0.04, workers=2)
    assert outcomes.count("granted") == 1, f"exactly one may win: {outcomes}"
    assert _spent(Session, organization_id) <= 0.10 + 1e-9, "spend exceeded the limit"


def test_many_concurrent_reservations_never_exceed_the_limit(committed_org) -> None:
    organization_id, Session = committed_org
    _set_limit(Session, organization_id, 0.10)

    outcomes = _run_concurrently(Session, organization_id, 0.02, workers=8)
    assert outcomes.count("granted") <= 5, f"more grants than the limit allows: {outcomes}"
    assert _spent(Session, organization_id) <= 0.10 + 1e-9


def test_exact_budget_is_allowed(committed_org) -> None:
    """An off-by-one here would silently deny the last legitimate probe of
    every period."""
    organization_id, Session = committed_org
    _set_limit(Session, organization_id, 0.10)
    with Session() as session:
        budget = visibility_service.reserve_budget(
            session, organization_id=organization_id, estimated_cost=0.10
        )
        session.commit()
        assert float(budget.period_spent) == pytest.approx(0.10)


def test_one_over_budget_is_refused(committed_org) -> None:
    organization_id, Session = committed_org
    _set_limit(Session, organization_id, 0.10)
    with Session() as session:
        with pytest.raises(Exception):
            visibility_service.reserve_budget(
                session, organization_id=organization_id, estimated_cost=0.11
            )
        session.rollback()
    assert _spent(Session, organization_id) == 0.0, "a refusal must reserve nothing"


def test_release_returns_unspent_reservation(committed_org) -> None:
    organization_id, Session = committed_org
    _set_limit(Session, organization_id, 1.0)
    with Session() as session:
        visibility_service.reserve_budget(
            session, organization_id=organization_id, estimated_cost=0.30
        )
        visibility_service.release_reservation(
            session, organization_id=organization_id, amount=0.30
        )
        session.commit()
    assert _spent(Session, organization_id) == pytest.approx(0.0)


def test_double_release_cannot_drive_spend_negative(committed_org) -> None:
    """A negative balance would silently grant free budget."""
    organization_id, Session = committed_org
    _set_limit(Session, organization_id, 1.0)
    with Session() as session:
        visibility_service.reserve_budget(
            session, organization_id=organization_id, estimated_cost=0.10
        )
        for _ in range(3):
            visibility_service.release_reservation(
                session, organization_id=organization_id, amount=0.10
            )
        session.commit()
    assert _spent(Session, organization_id) >= 0.0


def test_settlement_refunds_when_actual_is_lower(committed_org) -> None:
    """estimated_cost is NOT assumed to equal actual_cost (P12-16)."""
    organization_id, Session = committed_org
    _set_limit(Session, organization_id, 1.0)
    with Session() as session:
        visibility_service.reserve_budget(
            session, organization_id=organization_id, estimated_cost=0.50
        )
        visibility_service.settle_reservation(
            session, organization_id=organization_id, reserved=0.50, actual=0.20
        )
        session.commit()
    assert _spent(Session, organization_id) == pytest.approx(0.20)


def test_settlement_charges_when_actual_is_higher(committed_org) -> None:
    """The money is already spent; the ledger must match the invoice even if
    that pushes past the limit."""
    organization_id, Session = committed_org
    _set_limit(Session, organization_id, 1.0)
    with Session() as session:
        visibility_service.reserve_budget(
            session, organization_id=organization_id, estimated_cost=0.50
        )
        visibility_service.settle_reservation(
            session, organization_id=organization_id, reserved=0.50, actual=0.90
        )
        session.commit()
    assert _spent(Session, organization_id) == pytest.approx(0.90)


def test_zero_cost_reservation_is_not_gated_by_an_empty_budget(committed_org) -> None:
    """A manually pasted observation costs nothing and must not be blocked
    by a budget meant for paid API probes."""
    organization_id, Session = committed_org
    with Session() as session:
        budget = visibility_service.reserve_budget(
            session, organization_id=organization_id, estimated_cost=0.0
        )
        session.commit()
        assert float(budget.period_spent) == 0.0


def test_reservations_are_tenant_isolated(committed_org) -> None:
    """Both tenants must have an EXISTING budget row for the same period
    before this can detect anything.

    Mutation testing showed the first version could not: it created org B
    but never materialised B's budget row, so removing the
    `organization_id` filter from the reservation UPDATE had no row to
    corrupt and the test still passed. The row must exist for the leak to
    be observable."""
    organization_id, Session = committed_org
    _set_limit(Session, organization_id, 1.0)

    other = uuid_module.uuid4()
    with Session() as session:
        session.add(Organization(id=other, name=f"other-{other.hex[:6]}", slug=f"other-{other.hex[:6]}"))
        session.commit()
    try:
        # Materialise B's budget for the SAME period_key, with headroom, so
        # an unfiltered UPDATE would visibly increment it.
        _set_limit(Session, other, 1.0)
        assert _spent(Session, other) == 0.0

        with Session() as session:
            visibility_service.reserve_budget(
                session, organization_id=organization_id, estimated_cost=0.75
            )
            session.commit()

        assert _spent(Session, organization_id) == pytest.approx(0.75)
        assert _spent(Session, other) == 0.0, (
            "one tenant's reservation incremented another tenant's budget"
        )
    finally:
        with Session() as cleanup:
            cleanup.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": str(other)})
            cleanup.commit()
