"""
AIExecution persistence (Phase 17, P17-03).

Rows are created only by the shared invocation wrapper, immediately before
a provider call, and finalized exactly once. After that they are immutable
accounting facts: app-level (`ExecutionAlreadyTerminal`) and DB-level
(trg_ai_executions_immutable_terminal). A retry is a NEW row.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.ai.pricing import ModelPrice, estimate_from_usage
from app.models.ai_execution import PARENT_COLUMN_FOR_TYPE, AIExecution
from app.models.enums import (
    AI_EXECUTION_TERMINAL_STATUSES,
    AIAttemptReason,
    AIExecutionStatus,
    AIOperationType,
    AIParentType,
)

logger = logging.getLogger("app.ai_execution")


# Adapter error code -> normalised stop reason (REQ-AIC-007).
STOP_REASON_FOR_ERROR = {
    "auth_failed": "AUTHENTICATION_FAILED", "rate_limited": "RATE_LIMIT", "quota_exhausted": "QUOTA_EXHAUSTED",
    "timeout": "PROVIDER_TIMEOUT", "network_error": "PROVIDER_UNAVAILABLE", "provider_error": "PROVIDER_INTERNAL_ERROR",
    "invalid_response": "PROVIDER_INTERNAL_ERROR", "response_too_large": "PROVIDER_INTERNAL_ERROR",
    "invalid_request": "UNKNOWN", "internal_error": "UNKNOWN", "finalized_elsewhere": "SYSTEM_CANCELLED",
    "stale_running_reclaimed": "UNKNOWN", "not_configured": "AUTHENTICATION_FAILED",
}


class ExecutionAlreadyTerminal(RuntimeError):
    pass


class InvalidExecutionChain(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def input_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def start_execution(
    db: Session, *, organization_id: UUID, parent_type: AIParentType, parent_id: UUID,
    operation_type: AIOperationType, provider: str, model: str,
    user_id: UUID | None = None, installation_id: UUID | None = None,
    knowledge_object_id: UUID | None = None, stage: str | None = None,
    prompt_reference: str | None = None, input_hash_value: str | None = None,
    request_id: str | None = None,
    previous: AIExecution | None = None, attempt_reason: AIAttemptReason | None = None,
    provider_account_id: UUID | None = None,
) -> AIExecution:
    """Persist a RUNNING row and COMMIT it — before any provider call."""
    if (previous is None) != (attempt_reason is None):
        raise InvalidExecutionChain("previous execution and attempt_reason must be given together")
    if previous is not None:
        if previous.organization_id != organization_id:
            raise InvalidExecutionChain("a retry cannot cross tenants")
        if previous.status not in {s.value for s in AI_EXECUTION_TERMINAL_STATUSES}:
            raise InvalidExecutionChain("only a terminal execution can be retried")
        if previous.parent_type != parent_type.value or \
                getattr(previous, PARENT_COLUMN_FOR_TYPE[parent_type]) != parent_id:
            raise InvalidExecutionChain("a retry must stay under the same business parent")

    execution = AIExecution(
        organization_id=organization_id, user_id=user_id, installation_id=installation_id,
        parent_type=parent_type.value, knowledge_object_id=knowledge_object_id, stage=stage,
        operation_type=operation_type.value, provider=provider, model=model,
        started_at=_now(), status=AIExecutionStatus.RUNNING.value,
        prompt_reference=prompt_reference, input_hash=input_hash_value, request_id=request_id,
        previous_execution_id=previous.id if previous is not None else None,
        attempt_reason=attempt_reason.value if attempt_reason is not None else None,
        provider_account_id=provider_account_id,
    )
    setattr(execution, PARENT_COLUMN_FOR_TYPE[parent_type], parent_id)
    db.add(execution)
    db.commit()
    db.refresh(execution)
    logger.info("ai_execution started id=%s provider=%s model=%s parent=%s",
                execution.id, provider, model, parent_type.value)
    return execution


def _finalize(db: Session, execution: AIExecution, *, status: AIExecutionStatus,
              input_tokens: int | None, output_tokens: int | None,
              price: ModelPrice | None, actual_cost: Decimal | None, actual_currency: str | None,
              provider_request_id: str | None, model_version: str | None,
              error_code: str | None, error_message: str | None,
              stop_reason: str | None = None) -> AIExecution:
    # Lock the row and re-read it: an in-memory object may be stale (another
    # worker, or the stale-execution reclaimer, may already have finalized
    # it). Deciding on the fresh, locked state closes the lost-update race;
    # the DB trigger is the second line of defence.
    db.refresh(execution, with_for_update=True)
    if execution.status != AIExecutionStatus.RUNNING.value:
        raise ExecutionAlreadyTerminal(f"execution {execution.id} is already {execution.status}")
    completed = _now()
    execution.status = status.value
    execution.completed_at = completed
    execution.duration_ms = max(0, int((completed - execution.started_at).total_seconds() * 1000))
    execution.input_tokens = input_tokens
    execution.output_tokens = output_tokens
    execution.total_tokens = (input_tokens + output_tokens
                              if input_tokens is not None and output_tokens is not None else None)
    estimated = estimate_from_usage(price, input_tokens, output_tokens)
    execution.estimated_provider_cost = estimated
    # Never copied from the estimate: only a provider-reported figure.
    execution.actual_provider_cost = actual_cost
    currency = actual_currency if actual_cost is not None else (price.currency if estimated is not None else None)
    execution.currency = currency
    execution.provider_request_id = provider_request_id
    execution.model_version = model_version
    execution.error_code = error_code
    execution.error_message = error_message[:500] if error_message else None
    execution.stop_reason = stop_reason
    db.commit()
    db.refresh(execution)
    logger.info("ai_execution finished id=%s status=%s error_code=%s duration_ms=%s",
                execution.id, execution.status, error_code, execution.duration_ms)
    return execution


def finalize_success(db: Session, execution: AIExecution, *, input_tokens, output_tokens, price,
                     actual_cost=None, actual_currency=None, provider_request_id=None,
                     model_version=None, stop_reason: str = "COMPLETED") -> AIExecution:
    return _finalize(db, execution, status=AIExecutionStatus.SUCCEEDED, input_tokens=input_tokens,
                     output_tokens=output_tokens, price=price, actual_cost=actual_cost,
                     actual_currency=actual_currency, provider_request_id=provider_request_id,
                     model_version=model_version, error_code=None, error_message=None,
                     stop_reason=stop_reason)


def finalize_failure(db: Session, execution: AIExecution, *, status: AIExecutionStatus, error_code: str,
                     error_message: str, input_tokens=None, output_tokens=None, price=None,
                     provider_request_id=None) -> AIExecution:
    stop_reason = STOP_REASON_FOR_ERROR.get(error_code, "UNKNOWN")
    if status in (AIExecutionStatus.RUNNING, AIExecutionStatus.SUCCEEDED):
        raise ValueError("a failure must have a failure status")
    # A failed call can still have consumed (and billed) tokens.
    return _finalize(db, execution, status=status, input_tokens=input_tokens, output_tokens=output_tokens,
                     price=price, actual_cost=None, actual_currency=None,
                     provider_request_id=provider_request_id, model_version=None,
                     error_code=error_code, error_message=error_message, stop_reason=stop_reason)


def get_execution(db: Session, *, execution_id: UUID, organization_id: UUID) -> AIExecution | None:
    return db.execute(select(AIExecution).where(
        AIExecution.id == execution_id, AIExecution.organization_id == organization_id,
    )).scalar_one_or_none()


def list_executions(db: Session, *, organization_id: UUID, limit: int, offset: int,
                    status: str | None = None, provider: str | None = None, model: str | None = None,
                    parent_type: str | None = None, visibility_run_id: UUID | None = None,
                    sort=None) -> tuple[list[AIExecution], int]:
    conditions = [AIExecution.organization_id == organization_id]
    if status:
        conditions.append(AIExecution.status == status)
    if provider:
        conditions.append(AIExecution.provider == provider)
    if model:
        conditions.append(AIExecution.model == model)
    if parent_type:
        conditions.append(AIExecution.parent_type == parent_type)
    if visibility_run_id:
        conditions.append(AIExecution.visibility_run_id == visibility_run_id)
    total = db.execute(select(func.count()).select_from(AIExecution).where(*conditions)).scalar_one()
    from app.schemas.common import apply_sort

    stmt = apply_sort(select(AIExecution).where(*conditions), AIExecution, sort, default_field="started_at")
    items = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return list(items), total


def counts_by_status(db: Session, *, organization_id: UUID, provider: str | None = None, model: str | None = None,
                     parent_type: str | None = None, visibility_run_id: UUID | None = None) -> dict[str, int]:
    """Executions per status in one grouped query (Rule 17), with the list's
    other filters but NOT its status filter, so the header can show every
    status while the table shows one. Every status is present, 0 if none."""
    conditions = [AIExecution.organization_id == organization_id]
    if provider:
        conditions.append(AIExecution.provider == provider)
    if model:
        conditions.append(AIExecution.model == model)
    if parent_type:
        conditions.append(AIExecution.parent_type == parent_type)
    if visibility_run_id:
        conditions.append(AIExecution.visibility_run_id == visibility_run_id)
    found = dict(db.execute(
        select(AIExecution.status, func.count()).where(*conditions).group_by(AIExecution.status)
    ).all())
    return {s.value: found.get(s.value, 0) for s in AIExecutionStatus}


def execution_chain(db: Session, *, execution_id: UUID, organization_id: UUID) -> list[AIExecution]:
    """Every attempt leading to `execution_id`, oldest first (recursive,
    tenant-scoped at every step)."""
    rows = db.execute(text("""
        WITH RECURSIVE chain AS (
            SELECT id, previous_execution_id, 0 AS depth FROM ai_executions
             WHERE id = :eid AND organization_id = :org
            UNION ALL
            SELECT e.id, e.previous_execution_id, c.depth + 1 FROM ai_executions e
              JOIN chain c ON e.id = c.previous_execution_id
             WHERE e.organization_id = :org AND c.depth < 100
        )
        SELECT id FROM chain ORDER BY depth DESC
    """), {"eid": execution_id, "org": organization_id}).scalars().all()
    if not rows:
        return []
    by_id = {e.id: e for e in db.execute(select(AIExecution).where(AIExecution.id.in_(rows))).scalars()}
    return [by_id[i] for i in rows]


def reclaim_stale_executions(db: Session, *, older_than_seconds: int) -> int:
    """RUNNING rows older than the threshold lost their worker. The
    provider may or may not have executed (and billed) the call, so the
    outcome is ABANDONED — never SUCCEEDED, never a fabricated result —
    and cost stays NULL. Rows younger than the threshold are left alone:
    they may genuinely still be running."""
    from app.core.config import settings

    floor = int(settings.AI_PROVIDER_TIMEOUT_SECONDS * 2)
    if older_than_seconds < floor:
        raise ValueError(f"threshold must be at least {floor}s (2x the provider timeout)")
    cutoff = _now() - timedelta(seconds=older_than_seconds)
    now = _now()
    result = db.execute(
        update(AIExecution)
        .where(AIExecution.status == AIExecutionStatus.RUNNING.value, AIExecution.started_at < cutoff)
        .values(status=AIExecutionStatus.ABANDONED.value, completed_at=now,
                duration_ms=None, error_code="stale_running_reclaimed",
                error_message="Worker lost the invocation; provider outcome and cost are unknown")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount or 0
