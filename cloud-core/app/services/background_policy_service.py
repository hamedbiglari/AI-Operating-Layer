"""
Background Processing Policy enforcement (ADR-095).

The worker MUST call `check_background_policy` before dispatching any
background task. Without a policy row for a task type the task is refused
with POLICY_MISSING — a connected account that is not explicitly opted-in
is NEVER selected.

This is the enforcement layer referenced in prompt §5-10.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.background_policy import BackgroundTaskPolicy


@dataclass
class PolicyDecision:
    allowed: bool
    allowed_account_ids: list[uuid.UUID]
    routing_mode: Optional[str]
    max_cost_per_run: Optional[float]
    auto_switch_on_failure: bool
    reason: str   # why allowed/denied


def check_background_policy(
    db: Session,
    *,
    organization_id: uuid.UUID,
    task_type: str,
) -> PolicyDecision:
    """
    Load the tenant's background processing policy for task_type.
    Returns a PolicyDecision that the worker MUST respect.

    Invariant: CONNECTED != ENABLED.
    An account not in allowed_account_ids MUST NOT be selected even if
    it is healthy and has available quota.
    """
    row = db.execute(
        select(BackgroundTaskPolicy).where(
            BackgroundTaskPolicy.organization_id == organization_id,
            BackgroundTaskPolicy.task_type == task_type,
        )
    ).scalar_one_or_none()

    if row is None:
        return PolicyDecision(
            allowed=False,
            allowed_account_ids=[],
            routing_mode=None,
            max_cost_per_run=None,
            auto_switch_on_failure=True,
            reason="POLICY_MISSING — no BackgroundTaskPolicy exists for this task type; "
                   "a connected account is never eligible without an explicit policy",
        )

    if not row.enabled:
        return PolicyDecision(
            allowed=False,
            allowed_account_ids=[],
            routing_mode=row.routing_mode,
            max_cost_per_run=row.max_cost_per_run,
            auto_switch_on_failure=row.auto_switch_on_failure,
            reason="POLICY_DISABLED — the policy exists but is disabled by the tenant",
        )

    account_ids = [uuid.UUID(a) for a in (row.allowed_account_ids or [])]
    if not account_ids:
        return PolicyDecision(
            allowed=False,
            allowed_account_ids=[],
            routing_mode=row.routing_mode,
            max_cost_per_run=row.max_cost_per_run,
            auto_switch_on_failure=row.auto_switch_on_failure,
            reason="POLICY_NO_ACCOUNTS — policy enabled but no accounts are in the allowed list",
        )

    return PolicyDecision(
        allowed=True,
        allowed_account_ids=account_ids,
        routing_mode=row.routing_mode,
        max_cost_per_run=row.max_cost_per_run,
        auto_switch_on_failure=row.auto_switch_on_failure,
        reason=f"POLICY_ALLOWED — {len(account_ids)} allowed account(s), "
               f"routing={row.routing_mode}, max_cost={row.max_cost_per_run}",
    )
