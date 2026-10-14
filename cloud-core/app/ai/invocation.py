"""
The shared AI invocation wrapper (Phase 17, P17-04) — the ONLY path from a
business domain to a model provider.

    Business task
        -> invoke_with_policy / invoke_once
            -> validate context (tenant, parent, actor, budget gate)
            -> resolve adapter; not configured => NO execution, nothing ran
            -> start_execution(status=running)  COMMITTED before the call
            -> adapter.invoke(...)              (refuses without that row)
            -> finalize_success / finalize_failure (terminal, immutable)
        -> structured outcome back to the domain

Retry, provider fallback, model fallback and manual retry each create a
NEW execution chained by previous_execution_id; nothing earlier is ever
rewritten.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.pricing import ConfiguredPricing, PricingResolver
from app.integrations.llm.base import AdapterError, AdapterResult, LLMAdapter, ModelRequest, get_adapter
from app.models.ai_execution import AIExecution
from app.models.enums import AIAttemptReason, AIExecutionStatus, AIParentType
from app.services import ai_execution_service as executions

logger = logging.getLogger("app.ai_invocation")


class BudgetGateNotCleared(RuntimeError):
    """The caller did not assert that its budget gate passed. No provider
    money may be spent before a budget decision (Phase 17 §32)."""


class ProviderNotConfigured(RuntimeError):
    """No usable adapter/credential. No execution is recorded."""


@dataclass(frozen=True)
class InvocationContext:
    organization_id: UUID
    parent_type: AIParentType
    parent_id: UUID
    user_id: UUID | None = None
    installation_id: UUID | None = None
    knowledge_object_id: UUID | None = None
    stage: str | None = None
    request_id: str | None = None
    prompt_reference: str | None = None
    # Must be True: set by the caller only AFTER its budget reservation
    # succeeded.
    budget_cleared: bool = False


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> "ModelTarget":
        provider, _, model = value.strip().partition("/")
        if not provider or not model:
            raise ValueError(f"target must be 'provider/model', got {value!r}")
        return cls(provider, model)


@dataclass
class InvocationOutcome:
    execution: AIExecution
    result: AdapterResult | None = None
    error: AdapterError | None = None

    @property
    def succeeded(self) -> bool:
        return self.execution.status == AIExecutionStatus.SUCCEEDED.value


@dataclass
class PolicyOutcome:
    executions: list[AIExecution] = field(default_factory=list)
    final: InvocationOutcome | None = None
    not_configured: bool = False

    @property
    def succeeded(self) -> bool:
        return self.final is not None and self.final.succeeded


def _validate(ctx: InvocationContext) -> None:
    if ctx.organization_id is None or ctx.parent_id is None:
        raise ValueError("invocation context requires organization and business parent")
    if not ctx.budget_cleared:
        raise BudgetGateNotCleared("budget gate not cleared before AI invocation")


def invoke_once(
    db: Session, ctx: InvocationContext, target: ModelTarget, request: ModelRequest, *,
    adapter: LLMAdapter | None = None, pricing: PricingResolver | None = None,
    previous: AIExecution | None = None, attempt_reason: AIAttemptReason | None = None,
    provider_account_id: UUID | None = None,
) -> InvocationOutcome:
    _validate(ctx)
    adapter = adapter or get_adapter(target.provider)
    if adapter is None or not adapter.is_configured():
        raise ProviderNotConfigured(f"provider '{target.provider}' is not configured")
    pricing = pricing or ConfiguredPricing()
    price = pricing.price(target.provider, target.model)

    execution = executions.start_execution(
        db, organization_id=ctx.organization_id, parent_type=ctx.parent_type, parent_id=ctx.parent_id,
        operation_type=request.operation_type, provider=target.provider, model=target.model,
        user_id=ctx.user_id, installation_id=ctx.installation_id,
        knowledge_object_id=ctx.knowledge_object_id, stage=ctx.stage,
        prompt_reference=ctx.prompt_reference,
        input_hash_value=executions.input_hash(request.prompt), request_id=ctx.request_id,
        previous=previous, attempt_reason=attempt_reason, provider_account_id=provider_account_id,
    )
    try:
        result = adapter.invoke(request, model=target.model, execution=execution)
    except AdapterError as err:
        return _finalize_or_yield(db, execution, err, lambda: executions.finalize_failure(
            db, execution, status=err.status, error_code=err.error_code, error_message=err.safe_message,
            input_tokens=err.input_tokens, output_tokens=err.output_tokens, price=price,
            provider_request_id=err.provider_request_id,
        ))
    except Exception as exc:  # noqa: BLE001 — an execution must never stay RUNNING
        logger.exception("unexpected error during AI invocation %s", execution.id)
        err = AdapterError(error_code="internal_error", status=AIExecutionStatus.FAILED, retryable=False,
                           safe_message=f"Internal error during invocation ({type(exc).__name__})")
        return _finalize_or_yield(db, execution, err, lambda: executions.finalize_failure(
            db, execution, status=err.status, error_code=err.error_code, error_message=err.safe_message))

    outcome = _finalize_or_yield(db, execution, None, lambda: executions.finalize_success(
        db, execution, input_tokens=result.input_tokens, output_tokens=result.output_tokens,
        price=price, actual_cost=result.actual_cost, actual_currency=result.currency,
        provider_request_id=result.provider_request_id, model_version=result.model_version,
        stop_reason=result.stop_reason,
    ))
    if outcome.error is None:
        outcome.result = result
    return outcome


def _finalize_or_yield(db: Session, execution: AIExecution, err: AdapterError | None, finalize) -> InvocationOutcome:
    """Finalize exactly once. If another actor (the stale-execution
    reclaimer) already made the row terminal, its verdict stands: the
    recorded fact is never overwritten, and the provider's late answer is
    NOT handed to the domain as a success — the domain gets a failure
    outcome pointing at the row as it actually is."""
    try:
        finalize()
    except executions.ExecutionAlreadyTerminal:
        db.refresh(execution)
        logger.warning("ai_execution %s was finalized elsewhere (%s); late provider outcome discarded",
                       execution.id, execution.status)
        return InvocationOutcome(execution=execution, error=AdapterError(
            error_code="finalized_elsewhere", status=AIExecutionStatus(execution.status), retryable=False,
            safe_message=f"Execution was already {execution.status}; late provider outcome discarded"))
    return InvocationOutcome(execution=execution, error=err)


def invoke_with_policy(
    db: Session, ctx: InvocationContext, targets: list[ModelTarget], request: ModelRequest, *,
    attempts_per_target: int = 2, adapters: dict[str, LLMAdapter] | None = None,
    pricing: PricingResolver | None = None, manual_retry_of: AIExecution | None = None,
) -> PolicyOutcome:
    """Try each target in order; retry retryable failures up to
    `attempts_per_target`; stop at the first success or a non-retryable
    error on the last target. Unconfigured targets are skipped WITHOUT an
    execution row."""
    outcome = PolicyOutcome()
    previous = manual_retry_of
    for index, target in enumerate(targets):
        adapter = (adapters or {}).get(target.provider) or get_adapter(target.provider)
        if adapter is None or not adapter.is_configured():
            continue
        for attempt in range(max(attempts_per_target, 1)):
            if previous is None:
                reason = None
            elif previous is manual_retry_of and not outcome.executions:
                reason = AIAttemptReason.MANUAL_RETRY
            elif attempt > 0:
                reason = AIAttemptReason.RETRY
            elif previous.provider != target.provider:
                reason = AIAttemptReason.PROVIDER_FALLBACK
            else:
                reason = AIAttemptReason.MODEL_FALLBACK
            result = invoke_once(db, ctx, target, request, adapter=adapter, pricing=pricing,
                                 previous=previous, attempt_reason=reason)
            outcome.executions.append(result.execution)
            outcome.final = result
            previous = result.execution
            if result.succeeded:
                return outcome
            if result.error is not None and not result.error.retryable:
                break
    if not outcome.executions:
        outcome.not_configured = True
    return outcome
