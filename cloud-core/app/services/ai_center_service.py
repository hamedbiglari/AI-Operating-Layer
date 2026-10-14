"""AI Resource Registry services (REQ-AIC-001/002/008/009/010)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.llm.anthropic import AnthropicAdapter
from app.models.ai_center import AIHealthEvent, AIModel, AIProvider, AIProviderAccount
from app.models.ai_execution import AIExecution
from app.security import credential_crypto

# Adapters actually implemented in app/integrations/llm/. A provider whose
# adapter_key is not here can be registered and routed to, but routing will
# skip it with the reason "no adapter implemented" — never a fake call.
IMPLEMENTED_ADAPTERS = {"anthropic": AnthropicAdapter}


def adapter_class(adapter_key: str | None):  # noqa: ANN201
    """The adapter class for a provider's adapter key. The non-commercial
    TEST_PROVIDER exists only when TEST_PROVIDER_ENABLED=1."""
    from app.integrations.llm import test_provider
    if adapter_key == test_provider.PROVIDER_KEY:
        return test_provider.TestProviderAdapter if test_provider.enabled() else None
    return IMPLEMENTED_ADAPTERS.get(adapter_key or "")

# Execution stop reason -> account health + how long to avoid the account.
HEALTH_FOR_STOP = {
    "RATE_LIMIT": ("rate_limited", 60), "QUOTA_EXHAUSTED": ("quota_exhausted", 3600),
    "AUTHENTICATION_FAILED": ("auth_failed", None), "PROVIDER_UNAVAILABLE": ("unavailable", 120),
    "PROVIDER_TIMEOUT": ("timeout", 60), "PROVIDER_INTERNAL_ERROR": ("degraded", 60),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_404(db: Session, model, obj_id: UUID, organization_id: UUID):  # noqa: ANN001
    row = db.execute(select(model).where(model.id == obj_id, model.organization_id == organization_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return row


def canonical(name: str) -> str:
    return " ".join(name.strip().lower().split())


def set_credential(db: Session, account: AIProviderAccount, secret: str) -> AIProviderAccount:
    try:
        account.credential_ciphertext = credential_crypto.encrypt(secret)
    except credential_crypto.CredentialKeyMissing:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Credential encryption is not configured on this server; the credential was not stored.") from None
    account.credential_last4 = secret[-4:] if len(secret) >= 8 else None
    account.credential_set_at = _now()
    account.health_status = "unknown"
    account.failure_count = 0
    account.unavailable_until = None
    db.commit()
    db.refresh(account)
    return account


def adapter_for(db: Session, account: AIProviderAccount):  # noqa: ANN201
    """The adapter bound to THIS account's credential, or (None, reason)."""
    provider = db.get(AIProvider, account.provider_id)
    cls = adapter_class(provider.adapter_key)
    if cls is None:
        return None, f"no adapter implemented for provider '{provider.name}'"
    if not account.credential_ciphertext:
        return None, "no credential stored for this account"
    try:
        key = credential_crypto.decrypt(account.credential_ciphertext)
    except credential_crypto.CredentialKeyMissing as exc:
        return None, str(exc)
    return cls(api_key=key), None


def record_health(db: Session, account: AIProviderAccount, *, health: str, source: str, http_status: int | None = None,
                  code: str | None = None, message: str | None = None, retry_after: int | None = None,
                  execution_id: UUID | None = None, avoid_seconds: int | None = None) -> None:
    now = _now()
    account.health_status = health
    account.health_checked_at = now
    if health == "healthy":
        account.failure_count = 0
        account.unavailable_until = None
    else:
        account.failure_count += 1
        wait = retry_after or avoid_seconds
        account.unavailable_until = now + timedelta(seconds=wait) if wait else account.unavailable_until
    db.add(AIHealthEvent(organization_id=account.organization_id, account_id=account.id, status=health, source=source,
                         http_status=http_status, provider_code=code, message=(message or "")[:500] or None,
                         retry_after_seconds=retry_after, execution_id=execution_id, observed_at=now))
    db.commit()


def test_connection(db: Session, account: AIProviderAccount) -> dict:
    adapter, reason = adapter_for(db, account)
    if adapter is None:
        return {"result": "BLOCKED_EXTERNAL_DEPENDENCY", "message": reason, "http_status": None}
    result, http_status, message = adapter.test_connection()
    health = {"PASS": "healthy", "PARTIAL": "degraded"}.get(result)
    if health is None and http_status in (401, 403):
        health = "auth_failed"
    elif health is None and http_status == 429:
        health = "rate_limited"
    elif health is None:
        health = "unavailable"
    account.credential_last_tested_at = _now()
    record_health(db, account, health=health, source="connection_test", http_status=http_status, message=message)
    return {"result": result, "message": message, "http_status": http_status}


def usage(db: Session, account: AIProviderAccount, *, since: datetime | None) -> dict:
    """Aggregated from canonical AIExecution rows. Unknown stays unknown: sums
    only over rows that reported a value, plus a count of rows that did not."""
    q = [AIExecution.organization_id == account.organization_id, AIExecution.provider_account_id == account.id]
    if since:
        q.append(AIExecution.started_at >= since)
    row = db.execute(select(
        func.count(), func.count(AIExecution.input_tokens), func.sum(AIExecution.input_tokens),
        func.sum(AIExecution.output_tokens), func.count(AIExecution.estimated_provider_cost),
        func.sum(AIExecution.estimated_provider_cost), func.count().filter(AIExecution.status == "succeeded"),
        func.count().filter(AIExecution.stop_reason == "RATE_LIMIT"), func.count().filter(AIExecution.stop_reason == "QUOTA_EXHAUSTED"),
    ).where(*q)).one()
    n, n_tok, tin, tout, n_cost, cost, ok, rl, qe = row
    return {"requests": n, "succeeded": ok, "rate_limit_events": rl, "quota_events": qe,
            "input_tokens": int(tin) if n_tok else None, "output_tokens": int(tout) if n_tok else None,
            "executions_without_token_report": n - n_tok,
            "estimated_cost": float(cost) if n_cost else None, "executions_without_cost": n - n_cost,
            "success_rate": (ok / n) if n else None}
