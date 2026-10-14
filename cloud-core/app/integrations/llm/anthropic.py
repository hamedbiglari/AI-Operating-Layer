"""
Anthropic Messages API adapter — the first real model provider (P17-06).

Credential: settings.ANTHROPIC_API_KEY (environment / .env only). The key
is sent only in the x-api-key header and never logged, persisted, echoed
in errors, or returned by any API.
"""
from __future__ import annotations

import json

import httpx

from app.core.config import settings
from app.integrations.llm.base import (
    AdapterError,
    AdapterResult,
    ModelRequest,
    register_adapter,
    require_invocation_permit,
)
from app.models.enums import AIExecutionStatus

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter:
    provider = "anthropic"

    def __init__(self, *, transport: httpx.BaseTransport | None = None, api_key: str | None = None) -> None:
        self._transport = transport
        self._api_key_override = api_key

    def _api_key(self) -> str | None:
        if self._api_key_override is not None:
            return self._api_key_override
        secret = settings.ANTHROPIC_API_KEY
        return secret.get_secret_value() if secret is not None else None

    def is_configured(self) -> bool:
        return bool(self._api_key())

    def invoke(self, request: ModelRequest, *, model: str, execution) -> AdapterResult:  # noqa: ANN001
        require_invocation_permit(execution)
        key = self._api_key()
        if not key:
            raise AdapterError(error_code="not_configured", status=AIExecutionStatus.FAILED,
                               retryable=False, safe_message="Provider credential is not configured")
        body = {
            "model": model,
            "max_tokens": request.max_output_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION,
                   "content-type": "application/json"}
        url = settings.ANTHROPIC_API_BASE_URL.rstrip("/") + "/v1/messages"
        cap = settings.AI_MAX_RESPONSE_BYTES
        try:
            with httpx.Client(timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS, transport=self._transport) as client:
                with client.stream("POST", url, headers=headers, json=body) as response:
                    request_id = response.headers.get("request-id")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > cap:
                            raise AdapterError(
                                error_code="response_too_large", status=AIExecutionStatus.FAILED,
                                retryable=False, provider_request_id=request_id,
                                safe_message=f"Provider response exceeded {cap} bytes",
                            )
                        chunks.append(chunk)
                    status_code = response.status_code
                    raw = b"".join(chunks)
        except AdapterError:
            raise
        except httpx.TimeoutException:
            raise AdapterError(error_code="timeout", status=AIExecutionStatus.TIMEOUT, retryable=True,
                               safe_message="Provider request timed out") from None
        except httpx.HTTPError as exc:
            raise AdapterError(error_code="network_error", status=AIExecutionStatus.FAILED, retryable=True,
                               safe_message=f"Network error contacting provider ({type(exc).__name__})") from None

        if status_code != 200:
            raise _http_error(status_code, request_id)

        try:
            data = json.loads(raw)
            blocks = data["content"]
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            usage = data.get("usage") or {}
        except (ValueError, KeyError, TypeError, AttributeError):
            raise AdapterError(error_code="invalid_response", status=AIExecutionStatus.FAILED,
                               retryable=False, provider_request_id=request_id,
                               safe_message="Provider returned a malformed response") from None

        return AdapterResult(
            text=text,
            input_tokens=_int_or_none(usage.get("input_tokens")),
            output_tokens=_int_or_none(usage.get("output_tokens")),
            provider_request_id=request_id or _str_or_none(data.get("id")),
            model_version=_str_or_none(data.get("model")),
            stop_reason={"max_tokens": "TOKEN_LIMIT", "refusal": "SAFETY_BLOCKED"}.get(data.get("stop_reason"), "COMPLETED"),
        )

    def test_connection(self) -> tuple[str, int | None, str]:
        """Connectivity + authentication + model listing, WITHOUT a model
        invocation (no tokens, no cost): GET /v1/models.
        Returns (PASS|FAIL|BLOCKED_EXTERNAL_DEPENDENCY, http_status, message)."""
        key = self._api_key()
        if not key:
            return "BLOCKED_EXTERNAL_DEPENDENCY", None, "No credential configured"
        url = settings.ANTHROPIC_API_BASE_URL.rstrip("/") + "/v1/models"
        try:
            with httpx.Client(timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS, transport=self._transport) as c:
                r = c.get(url, headers={"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION})
        except httpx.TimeoutException:
            return "FAIL", None, "Provider request timed out"
        except httpx.HTTPError as exc:
            return "FAIL", None, f"Network error ({type(exc).__name__})"
        if r.status_code == 200:
            try:
                n = len(r.json().get("data", []))
            except ValueError:
                return "PARTIAL", 200, "Authenticated, but the model list was unreadable"
            return "PASS", 200, f"Authenticated; {n} models listed"
        return "FAIL", r.status_code, f"Provider answered HTTP {r.status_code}"



def _int_or_none(value) -> int | None:  # noqa: ANN001
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _str_or_none(value) -> str | None:  # noqa: ANN001
    return str(value)[:200] if isinstance(value, str) and value else None


def _http_error(status_code: int, request_id: str | None) -> AdapterError:
    # Only the status code is surfaced — never the provider body, which may
    # echo the prompt.
    if status_code in (401, 403):
        return AdapterError(error_code="auth_failed", status=AIExecutionStatus.FAILED, retryable=False,
                            provider_request_id=request_id,
                            safe_message=f"Provider rejected the credential (HTTP {status_code})")
    if status_code == 402:
        return AdapterError(error_code="quota_exhausted", status=AIExecutionStatus.FAILED, retryable=False,
                            provider_request_id=request_id, safe_message="Provider quota or credit exhausted (HTTP 402)")
    if status_code == 429:
        return AdapterError(error_code="rate_limited", status=AIExecutionStatus.RATE_LIMITED, retryable=True,
                            provider_request_id=request_id, safe_message="Provider rate limit (HTTP 429)")
    if status_code == 408:
        return AdapterError(error_code="timeout", status=AIExecutionStatus.TIMEOUT, retryable=True,
                            provider_request_id=request_id, safe_message="Provider timeout (HTTP 408)")
    if status_code >= 500:
        return AdapterError(error_code="provider_error", status=AIExecutionStatus.FAILED, retryable=True,
                            provider_request_id=request_id,
                            safe_message=f"Provider server error (HTTP {status_code})")
    return AdapterError(error_code="invalid_request", status=AIExecutionStatus.FAILED, retryable=False,
                        provider_request_id=request_id,
                        safe_message=f"Provider rejected the request (HTTP {status_code})")


register_adapter(AnthropicAdapter())
