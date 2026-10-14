"""The OpenAI adapter (ADR-121): the same contract as Anthropic, against OpenAI's own request and
response shape. Every call here uses a mock transport — no network, no credential, no cost."""
import httpx
import pytest

from app.integrations.llm.base import AdapterError, InvocationPermitError, ModelRequest, get_adapter
from app.integrations.llm.openai import OpenAIAdapter
from app.models.enums import AIExecutionStatus

KEY = "sk-test-not-a-real-key"
PROMPT = "a prompt that must never appear in an error"


def ok_body(text="finding", finish="stop"):
    return {"id": "chatcmpl-1", "model": "gpt-x", "choices": [{"index": 0, "finish_reason": finish,
            "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 4}}


def adapter(handler, *, key=KEY):
    return OpenAIAdapter(transport=httpx.MockTransport(handler), api_key=key)


def responds(status=200, body=None, headers=None):
    def h(request):
        return httpx.Response(status, json=body if body is not None else ok_body(), headers=headers or {})
    return h


class Running:
    """A stand-in for a persisted RUNNING AIExecution; the real permit check is exercised separately."""
    pass


@pytest.fixture
def permitted(monkeypatch):
    monkeypatch.setattr("app.integrations.llm.openai.require_invocation_permit", lambda execution: None)
    return Running()


def req(max_tokens=64):
    return ModelRequest(prompt=PROMPT, max_output_tokens=max_tokens)


# ---------------------------------------------------------------- registration and configuration
def test_the_registry_resolves_openai():
    a = get_adapter("openai")
    assert a is not None and a.provider == "openai"


def test_without_a_credential_it_reports_unconfigured_and_refuses_to_invoke(permitted):
    a = OpenAIAdapter(api_key=None)
    a._api_key_override = None
    object.__setattr__(a, "_api_key_override", None)
    from app.core.config import settings
    if settings.OPENAI_API_KEY is None:
        assert a.is_configured() is False
        with pytest.raises(AdapterError) as e:
            a.invoke(req(), model="gpt-x", execution=permitted)
        assert e.value.error_code == "not_configured" and e.value.retryable is False


def test_a_call_without_a_running_execution_is_refused():
    """The non-bypass rule: no persisted RUNNING execution, no provider call — so money cannot be spent invisibly."""
    a = adapter(responds())
    with pytest.raises(InvocationPermitError):
        a.invoke(req(), model="gpt-x", execution=None)


# ---------------------------------------------------------------- the request it builds
def test_it_sends_openais_own_request_shape(permitted):
    seen = {}

    def h(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = httpx.Response(200, json=ok_body()).json() and __import__("json").loads(request.content)
        return httpx.Response(200, json=ok_body())

    adapter(h).invoke(req(max_tokens=128), model="gpt-x", execution=permitted)
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["auth"] == f"Bearer {KEY}"                      # not x-api-key
    assert seen["body"]["max_completion_tokens"] == 128          # the current field name
    assert seen["body"]["messages"] == [{"role": "user", "content": PROMPT}]


# ---------------------------------------------------------------- the answer it reads
def test_it_reads_the_answer_tokens_and_request_id(permitted):
    r = adapter(responds(headers={"x-request-id": "req_42"})).invoke(req(), model="gpt-x", execution=permitted)
    assert r.text == "finding"
    assert (r.input_tokens, r.output_tokens) == (11, 4)
    assert r.provider_request_id == "req_42" and r.model_version == "gpt-x"
    assert r.stop_reason == "COMPLETED"
    assert r.actual_cost is None                                 # the endpoint does not say what it billed


def test_it_reads_content_given_as_typed_parts(permitted):
    body = ok_body()
    body["choices"][0]["message"]["content"] = [{"type": "text", "text": "one "}, {"type": "text", "text": "two"}]
    r = adapter(responds(body=body)).invoke(req(), model="gpt-x", execution=permitted)
    assert r.text == "one two"


@pytest.mark.parametrize("finish,expected", [("stop", "COMPLETED"), ("length", "TOKEN_LIMIT"),
                                             ("content_filter", "SAFETY_BLOCKED"), ("something_new", "COMPLETED")])
def test_finish_reasons_are_normalised(permitted, finish, expected):
    r = adapter(responds(body=ok_body(finish=finish))).invoke(req(), model="gpt-x", execution=permitted)
    assert r.stop_reason == expected


def test_missing_token_counts_stay_none_rather_than_being_estimated(permitted):
    body = ok_body(); body.pop("usage")
    r = adapter(responds(body=body)).invoke(req(), model="gpt-x", execution=permitted)
    assert r.input_tokens is None and r.output_tokens is None


def test_a_malformed_answer_is_an_honest_failure(permitted):
    for body in ({"choices": []}, {"nope": 1}, {"choices": [{"message": {}}]}):
        with pytest.raises(AdapterError) as e:
            adapter(responds(body=body)).invoke(req(), model="gpt-x", execution=permitted)
        assert e.value.error_code == "invalid_response" and e.value.retryable is False


# ---------------------------------------------------------------- failures
@pytest.mark.parametrize("status,code,retryable,exec_status", [
    (401, "auth_failed", False, AIExecutionStatus.FAILED),
    (403, "auth_failed", False, AIExecutionStatus.FAILED),
    (402, "quota_exhausted", False, AIExecutionStatus.FAILED),
    (429, "rate_limited", True, AIExecutionStatus.RATE_LIMITED),
    (408, "timeout", True, AIExecutionStatus.TIMEOUT),
    (500, "provider_error", True, AIExecutionStatus.FAILED),
    (503, "provider_error", True, AIExecutionStatus.FAILED),
    (400, "invalid_request", False, AIExecutionStatus.FAILED),
])
def test_http_failures_map_to_the_shared_vocabulary(permitted, status, code, retryable, exec_status):
    with pytest.raises(AdapterError) as e:
        adapter(responds(status=status, body={"error": {"message": PROMPT}})).invoke(req(), model="gpt-x", execution=permitted)
    assert e.value.error_code == code and e.value.retryable is retryable and e.value.status == exec_status


def test_an_error_never_carries_the_prompt_or_the_credential(permitted):
    """The provider's body may echo the prompt; it is never read into the message."""
    with pytest.raises(AdapterError) as e:
        adapter(responds(status=400, body={"error": {"message": PROMPT, "key": KEY}})).invoke(
            req(), model="gpt-x", execution=permitted)
    assert PROMPT not in e.value.safe_message and KEY not in e.value.safe_message
    assert len(e.value.safe_message) <= 500


def test_a_timeout_and_a_network_error_are_retryable(permitted):
    def timeout(request):
        raise httpx.TimeoutException("slow")

    def broken(request):
        raise httpx.ConnectError("refused")

    for handler, code, status in ((timeout, "timeout", AIExecutionStatus.TIMEOUT),
                                  (broken, "network_error", AIExecutionStatus.FAILED)):
        with pytest.raises(AdapterError) as e:
            adapter(handler).invoke(req(), model="gpt-x", execution=permitted)
        assert e.value.error_code == code and e.value.retryable is True and e.value.status == status


def test_an_oversized_response_is_refused(permitted, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "AI_MAX_RESPONSE_BYTES", 50)
    with pytest.raises(AdapterError) as e:
        adapter(responds(body=ok_body(text="x" * 5000))).invoke(req(), model="gpt-x", execution=permitted)
    assert e.value.error_code == "response_too_large" and e.value.retryable is False


# ---------------------------------------------------------------- the connection test
def test_connection_test_authenticates_without_spending_tokens():
    seen = {}

    def h(request):
        seen["url"] = str(request.url)
        seen["method"] = request.method
        return httpx.Response(200, json={"data": [{"id": "gpt-x"}, {"id": "gpt-y"}]})

    verdict, status, message = adapter(h).test_connection()
    assert (verdict, status) == ("PASS", 200) and "2 models" in message
    assert seen["method"] == "GET" and seen["url"].endswith("/v1/models")   # no completion is requested


def test_connection_test_reports_a_missing_credential_as_blocked(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    verdict, status, message = OpenAIAdapter().test_connection()
    assert verdict == "BLOCKED_EXTERNAL_DEPENDENCY" and status is None


def test_connection_test_reports_a_rejected_credential_as_failure():
    verdict, status, _ = adapter(responds(status=401, body={"error": "nope"})).test_connection()
    assert verdict == "FAIL" and status == 401
