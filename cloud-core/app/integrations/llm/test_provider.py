"""
TEST_PROVIDER — deterministic, NON-COMMERCIAL adapter.

Purpose: verify routing, worker enforcement, agent orchestration, retries,
memory and execution lifecycle end-to-end through the REAL worker path
when no commercial provider credential exists. It never opens a network
connection. It is NOT a real provider and must never be reported as one.

Availability: only when the environment sets TEST_PROVIDER_ENABLED=1.
Otherwise `adapter_class("test_provider")` is None and the router treats a
test_provider account like any provider without an adapter (skipped with
reason "no adapter implemented").

Behaviour is scripted by the account's (test) credential string, so the
worker path — which decrypts the account credential and builds the adapter
itself — can exercise failures without any test-only injection:
    "test:ok"                      every call succeeds
    "test:rate_limit_after:N"      N successes, then RATE_LIMIT
    "test:quota_after:N"           N successes, then QUOTA_EXHAUSTED
    "test:auth_fail"               AUTHENTICATION_FAILED on every call
    "test:timeout"                 PROVIDER_TIMEOUT on every call
Tokens reported: 10 in / 5 out (deterministic). Cost: never reported (NULL).
"""
from __future__ import annotations

import os
import threading

from app.integrations.llm.base import AdapterError, AdapterResult, ModelRequest, require_invocation_permit
from app.models.enums import AIExecutionStatus

PROVIDER_KEY = "test_provider"
_calls: dict[str, int] = {}
_lock = threading.Lock()


def enabled() -> bool:
    return os.getenv("TEST_PROVIDER_ENABLED", "0") == "1"


def reset_counters() -> None:
    with _lock:
        _calls.clear()


class TestProviderAdapter:
    __test__ = False  # not a pytest test class
    provider = PROVIDER_KEY

    def __init__(self, *, api_key: str | None = None, transport=None) -> None:  # noqa: ANN001
        # Anything after '#' only makes the credential unique (per-account call counter).
        self._key = api_key or "test:ok"
        self._script = self._key.split("#", 1)[0]

    def is_configured(self) -> bool:
        return enabled()

    def invoke(self, request: ModelRequest, *, model: str, execution) -> AdapterResult:  # noqa: ANN001
        require_invocation_permit(execution)
        if not enabled():
            raise AdapterError(error_code="not_configured", status=AIExecutionStatus.FAILED, retryable=False,
                               safe_message="TEST_PROVIDER is disabled")
        with _lock:
            n = _calls.get(self._key, 0)
            _calls[self._key] = n + 1
        parts = self._script.split(":")
        mode = parts[1] if len(parts) > 1 else "ok"
        limit = int(parts[2]) if len(parts) > 2 else 0
        if mode == "auth_fail":
            raise AdapterError(error_code="auth_failed", status=AIExecutionStatus.FAILED, retryable=False,
                               safe_message="TEST_PROVIDER: authentication failed (scripted)")
        if mode == "timeout":
            raise AdapterError(error_code="timeout", status=AIExecutionStatus.TIMEOUT, retryable=True,
                               safe_message="TEST_PROVIDER: timeout (scripted)")
        if mode == "rate_limit_after" and n >= limit:
            raise AdapterError(error_code="rate_limited", status=AIExecutionStatus.RATE_LIMITED, retryable=True,
                               safe_message="TEST_PROVIDER: rate limited (scripted)")
        if mode == "quota_after" and n >= limit:
            raise AdapterError(error_code="quota_exhausted", status=AIExecutionStatus.FAILED, retryable=False,
                               safe_message="TEST_PROVIDER: quota exhausted (scripted)")
        return AdapterResult(text=f"[TEST_PROVIDER {model}] processed", input_tokens=10, output_tokens=5,
                             provider_request_id=f"test-{execution.id}", model_version=f"{model}-test")
