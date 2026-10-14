"""
OpenAI adapter (ADR-121) — the second provider behind the same boundary as Anthropic.

Mirrors app/integrations/llm/anthropic.py exactly in behaviour: the non-bypass rule, the response-size cap,
honest token reporting, and a `safe_message` that never carries the prompt, the response body or a credential.
What differs is only what the provider's own API differs in:

  * endpoint            /v1/chat/completions   (vs /v1/messages)
  * authentication      Authorization: Bearer  (vs x-api-key + a version header)
  * output limit        max_completion_tokens  (the current field; max_tokens is the older name)
  * the answer          choices[0].message.content   (vs a list of content blocks)
  * token counts        usage.prompt_tokens / usage.completion_tokens
  * finish reason       "length" | "content_filter" | "stop"
  * request id          the `x-request-id` response header

No cost is ever reported: the chat endpoint does not say what it billed, so `actual_cost` stays None and the
wallet's own estimate stands rather than an invented figure.
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


class OpenAIAdapter:
    provider = "openai"

    def __init__(self, *, transport: httpx.BaseTransport | None = None, api_key: str | None = None) -> None:
        self._transport = transport
        self._api_key_override = api_key

    def _api_key(self) -> str | None:
        if self._api_key_override is not None:
            return self._api_key_override
        secret = settings.OPENAI_API_KEY
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
            "max_completion_tokens": request.max_output_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
        url = settings.OPENAI_API_BASE_URL.rstrip("/") + "/v1/chat/completions"
        cap = settings.AI_MAX_RESPONSE_BYTES
        try:
            with httpx.Client(timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS, transport=self._transport) as client:
                with client.stream("POST", url, headers=headers, json=body) as response:
                    request_id = response.headers.get("x-request-id")
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
            choice = data["choices"][0]
            content = choice["message"]["content"]
            # content may be a plain string or a list of typed parts, depending on the model
            if isinstance(content, list):
                text = "".join(part.get("text", "") for part in content
                               if isinstance(part, dict) and part.get("type") in ("text", "output_text"))
            else:
                text = content or ""
            usage = data.get("usage") or {}
        except (ValueError, KeyError, TypeError, AttributeError, IndexError):
            raise AdapterError(error_code="invalid_response", status=AIExecutionStatus.FAILED,
                               retryable=False, provider_request_id=request_id,
                               safe_message="Provider returned a malformed response") from None

        return AdapterResult(
            text=text,
            input_tokens=_int_or_none(usage.get("prompt_tokens")),
            output_tokens=_int_or_none(usage.get("completion_tokens")),
            provider_request_id=request_id or _str_or_none(data.get("id")),
            model_version=_str_or_none(data.get("model")),
            stop_reason={"length": "TOKEN_LIMIT", "content_filter": "SAFETY_BLOCKED"}.get(
                choice.get("finish_reason"), "COMPLETED"),
        )

    def test_connection(self) -> tuple[str, int | None, str]:
        """Connectivity + authentication + model listing, WITHOUT a model invocation (no tokens, no cost):
        GET /v1/models. Returns (PASS|FAIL|PARTIAL|BLOCKED_EXTERNAL_DEPENDENCY, http_status, message)."""
        key = self._api_key()
        if not key:
            return "BLOCKED_EXTERNAL_DEPENDENCY", None, "No credential configured"
        url = settings.OPENAI_API_BASE_URL.rstrip("/") + "/v1/models"
        try:
            with httpx.Client(timeout=settings.AI_PROVIDER_TIMEOUT_SECONDS, transport=self._transport) as c:
                r = c.get(url, headers={"Authorization": f"Bearer {key}"})
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
    # Only the status code is surfaced — never the provider body, which may echo the prompt.
    if status_code in (401, 403):
        return AdapterError(error_code="auth_failed", status=AIExecutionStatus.FAILED, retryable=False,
                            provider_request_id=request_id,
                            safe_message=f"Provider rejected the credential (HTTP {status_code})")
    if status_code == 402:
        return AdapterError(error_code="quota_exhausted", status=AIExecutionStatus.FAILED, retryable=False,
                            provider_request_id=request_id, safe_message="Provider quota or credit exhausted (HTTP 402)")
    if status_code == 429:
        # OpenAI uses 429 both for rate limiting and for an exhausted quota; the body would say which, but the
        # body is never read. Treated as retryable, which the ledger's reservation already protects against.
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


register_adapter(OpenAIAdapter())
