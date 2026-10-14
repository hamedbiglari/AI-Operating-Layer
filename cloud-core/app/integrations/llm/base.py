"""
LLM provider adapter boundary (Phase 17, P17-05).

Same convention as app/integrations/{research,visibility,embeddings}: a
Protocol plus honest failure. Provider-specific HTTP lives ONLY in adapter
modules under this package; business services never call a provider.

THE NON-BYPASS RULE
    `LLMAdapter.invoke()` demands a persisted AIExecution in RUNNING state
    and refuses otherwise (`require_invocation_permit`). Only the shared
    invocation wrapper (app/ai/invocation.py) creates such a row
    immediately before calling, so calling an adapter directly — without
    first recording the execution — fails loudly instead of spending
    money invisibly.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from sqlalchemy import inspect as sa_inspect

from app.models.enums import AIExecutionStatus, AIOperationType


@dataclass(frozen=True)
class ModelRequest:
    prompt: str
    max_output_tokens: int
    operation_type: AIOperationType = AIOperationType.CHAT


@dataclass(frozen=True)
class AdapterResult:
    text: str
    # None = the provider did not report it. Never estimated.
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str | None = None
    model_version: str | None = None
    # Only if the provider itself reports what it billed.
    actual_cost: Decimal | None = None
    currency: str | None = None
    # Normalised (REQ-AIC-007): COMPLETED | TOKEN_LIMIT | SAFETY_BLOCKED | …
    stop_reason: str = "COMPLETED"


class AdapterError(Exception):
    """A provider failure the adapter understood. `safe_message` must never
    contain the prompt, the response body, or any credential."""

    def __init__(
        self, *, error_code: str, status: AIExecutionStatus, retryable: bool, safe_message: str,
        provider_request_id: str | None = None,
        input_tokens: int | None = None, output_tokens: int | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.error_code = error_code
        self.status = status
        self.retryable = retryable
        self.safe_message = safe_message[:500]
        self.provider_request_id = provider_request_id
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class InvocationPermitError(RuntimeError):
    """An adapter was called without a persisted RUNNING AIExecution."""


def require_invocation_permit(execution) -> None:  # noqa: ANN001
    from app.models.ai_execution import AIExecution

    if not isinstance(execution, AIExecution):
        raise InvocationPermitError("provider call attempted without an AIExecution record")
    state = sa_inspect(execution)
    if execution.id is None or not state.persistent:
        raise InvocationPermitError("provider call attempted before its AIExecution was persisted")
    if execution.status != AIExecutionStatus.RUNNING.value:
        raise InvocationPermitError("provider call attempted against a non-RUNNING AIExecution")


class LLMAdapter(Protocol):
    provider: str

    def is_configured(self) -> bool:
        """False when credentials are absent. The wrapper then records NO
        execution: nothing is invoked, so nothing happened."""
        ...

    def invoke(self, request: ModelRequest, *, model: str, execution) -> AdapterResult:  # noqa: ANN001
        """Must call require_invocation_permit(execution) first. Raises
        AdapterError for every understood failure."""
        ...


_REGISTRY: dict[str, LLMAdapter] = {}


def register_adapter(adapter: LLMAdapter) -> None:
    _REGISTRY[adapter.provider] = adapter


def get_adapter(provider: str) -> LLMAdapter | None:
    if not _REGISTRY:
        from app.integrations.llm import anthropic, openai  # noqa: F401  (each self-registers)
    return _REGISTRY.get(provider)
