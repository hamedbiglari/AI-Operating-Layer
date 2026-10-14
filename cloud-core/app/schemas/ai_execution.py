from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProviderCost(BaseModel):
    estimated_provider_cost: Decimal | None
    actual_provider_cost: Decimal | None
    currency: str | None


class AIExecutionRead(BaseModel):
    """Read-only operational view. No prompt/response content exists on
    the record, and no credential is ever reachable from it."""

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    organization_id: UUID
    user_id: UUID | None
    installation_id: UUID | None
    parent_type: str
    visibility_run_id: UUID | None
    knowledge_object_id: UUID | None
    stage: str | None
    operation_type: str
    provider: str
    model: str
    model_version: str | None
    provider_request_id: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    status: str
    error_code: str | None
    error_message: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    # Provider (wholesale) cost is admin-only (docs/billing/BILLING_DATA_MODEL.md).
    # `provider_cost` is null when the caller may not see it — that is a
    # permission fact, flagged by `provider_cost_visible`; it is NOT an
    # unknown cost. Inside `provider_cost`, a null amount means UNKNOWN.
    provider_cost_visible: bool = False
    provider_cost: "ProviderCost | None" = None
    previous_execution_id: UUID | None
    attempt_reason: str | None


def to_read(execution, *, can_see_cost: bool) -> AIExecutionRead:
    data = AIExecutionRead.model_validate(execution)
    if can_see_cost:
        data.provider_cost_visible = True
        data.provider_cost = ProviderCost(
            estimated_provider_cost=execution.estimated_provider_cost,
            actual_provider_cost=execution.actual_provider_cost,
            currency=execution.currency,
        )
    return data
