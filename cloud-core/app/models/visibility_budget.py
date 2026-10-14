"""
VisibilityBudget — the spend ceiling for platform probing (ADR-063).

WHY THIS EXISTS AT ALL

Phase 12 forensic reconciliation found (F7) that no budget or cost guard
existed anywhere in the codebase. Until now that was fine: every phase's
work was database and CPU, whose cost is bounded by the merchant's own
hosting. Phase 12 is the first phase that can spend **external money** —
each platform probe may be a paid API call — and a monitoring loop with a
bug is exactly the shape of thing that generates a large bill overnight.

So the ceiling is checked BEFORE a probe runs, not reconciled after. A
budget that is only discovered to be exceeded afterwards is an invoice, not
a guard.

`period_spent` is incremented as probes are recorded. It is deliberately
NOT computed by summing `visibility_tests.estimated_cost` on every check:
that sum grows without bound and would make the guard slower precisely as
usage grows. The trade-off is that the counter can drift from the row sum
if a probe fails midway; `reconcile()` exists for that, and the drift is
bounded by one probe.
"""

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class VisibilityBudget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "visibility_budgets"
    __table_args__ = (
        # One active budget per organization per period key.
        UniqueConstraint("organization_id", "period_key", name="uq_visibility_budgets_org_period"),
        CheckConstraint("period_limit >= 0", name="ck_visibility_budgets_limit_non_negative"),
        CheckConstraint("period_spent >= 0", name="ck_visibility_budgets_spent_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # e.g. "2026-09". A calendar-month key rather than a rolling window:
    # a merchant reasons about spend in months, and a rolling window makes
    # "how much is left this month" unanswerable.
    period_key: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")

    period_limit: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    period_spent: Mapped[float] = mapped_column(
        Numeric(10, 4), nullable=False, default=0, server_default="0"
    )
    last_reconciled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    @property
    def remaining(self) -> float:
        return float(self.period_limit) - float(self.period_spent)

    def would_exceed(self, estimated_cost: float) -> bool:
        """Checked BEFORE the probe. A zero limit means probing is disabled
        entirely, which is a legitimate configuration and must not be
        confused with 'no budget configured'."""
        return (float(self.period_spent) + float(estimated_cost)) > float(self.period_limit)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VisibilityBudget {self.period_key} {self.period_spent}/{self.period_limit} "
            f"{self.currency}>"
        )
