"""
Phase 17 — canonical AIExecution + first real provider path.

Everything here is MOCK_VERIFIED at the provider boundary: the Anthropic
adapter runs for real (real httpx, real request building, real response
parsing, real error mapping) against an httpx.MockTransport. No test here
is evidence of a real provider call; that requires a real credential.
"""
from __future__ import annotations

import json
import logging
import pathlib
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import exc, func, select, text

from app.ai.invocation import (
    BudgetGateNotCleared, InvocationContext, ModelTarget, ProviderNotConfigured,
    invoke_once, invoke_with_policy,
)
from app.ai.pricing import ConfiguredPricing
from app.core.config import settings
from app.integrations.llm.anthropic import AnthropicAdapter
from app.integrations.llm.base import InvocationPermitError, ModelRequest
from app.models.ai_execution import ARC_COLUMNS, AIExecution
from app.models.audit_log import AuditLog
from app.models.enums import (
    AIAttemptReason, AIExecutionStatus, AIOperationType, AIParentType, AdapterType,
    InstallationStatus, ProviderOutcome, SignalPresence, VisibilityPlatform,
)
from app.models.installation import Installation
from app.models.visibility import VisibilityTest
from app.models.visibility_project import VisibilityRun
from app.services import ai_execution_service as svc
from app.services import visibility_run_service

FAKE_KEY = "sk-test-NOT-A-REAL-KEY-phase17"
MODEL = "claude-haiku-4-5-20251001"
PRICING = ConfiguredPricing(json.dumps({
    f"anthropic/{MODEL}": {"input_per_mtok": "1.00", "output_per_mtok": "5.00", "currency": "USD"},
    "anthropic/model-b": {"input_per_mtok": "2.00", "output_per_mtok": "8.00", "currency": "USD"},
    "backup/backup-model": {"input_per_mtok": "3.00", "output_per_mtok": "9.00", "currency": "USD"},
}))
PROMPT = "PHASE17-SECRET-PROMPT best saffron supplier?"


# --- helpers -----------------------------------------------------------------

def ok_body(text_="Taranjabin Co at merchant.example is great", usage=True):
    body = {"id": "msg_test_1", "model": MODEL + "-v", "content": [{"type": "text", "text": text_}]}
    if usage:
        body["usage"] = {"input_tokens": 10, "output_tokens": 20}
    return body


class Script:
    """Scripted provider: each call pops the next response. Records calls
    and, at call time, whether a RUNNING execution already exists."""

    def __init__(self, db, responses):
        self.db, self.responses, self.calls, self.running_at_call = db, list(responses), [], []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        self.running_at_call.append(self.db.execute(
            select(func.count()).select_from(AIExecution)
            .where(AIExecution.status == AIExecutionStatus.RUNNING.value)).scalar_one())
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        status, body, headers = nxt
        content = body if isinstance(body, bytes) else json.dumps(body).encode()
        return httpx.Response(status, content=content, headers=headers or {})


def adapter_for(script, cls=AnthropicAdapter):
    return cls(transport=httpx.MockTransport(script.handler), api_key=FAKE_KEY)


class BackupAdapter(AnthropicAdapter):
    provider = "backup"


def make_run(client, db, org, platform=VisibilityPlatform.OTHER):
    headers = org["headers"]
    proj = client.post("/api/v1/visibility/projects", headers=headers, json={
        "name": f"p17-{uuid.uuid4().hex[:6]}", "markets": ["US"], "languages": ["en"],
        "platforms": [platform.value], "target_brand": "Taranjabin Co",
        "target_domain": "merchant.example"}).json()
    client.post("/api/v1/queries/import", headers=headers, data={
        "source": "manual", "rows_json": json.dumps([{"query": PROMPT}])})
    client.put("/api/v1/visibility/budget", json={"period_limit": 5.0, "currency": "USD"}, headers=headers)
    run = visibility_run_service.create_run(
        db, organization_id=uuid.UUID(org["organization"]["id"]), project_id=uuid.UUID(proj["id"]),
        platform=platform, provider_name="anthropic")
    db.commit()
    return run


def ctx_for(run, **kw):
    return InvocationContext(organization_id=run.organization_id, parent_type=AIParentType.VISIBILITY_RUN,
                             parent_id=run.id, budget_cleared=True, **kw)


def req():
    return ModelRequest(prompt=PROMPT, max_output_tokens=50)


def exec_count(db):
    return db.execute(select(func.count()).select_from(AIExecution)).scalar_one()


def raw_insert(db, **overrides):
    values = dict(id=uuid.uuid4(), parent_type="visibility_run", operation_type="chat",
                  provider="anthropic", model=MODEL, status="running")
    values.update(overrides)
    cols = ", ".join(values) + ", started_at, created_at, updated_at"
    params = ", ".join(f":{k}" for k in values) + ", now(), now(), now()"
    db.execute(text(f"INSERT INTO ai_executions ({cols}) VALUES ({params})"), values)
    db.flush()


@pytest.fixture()
def org(register_org):
    return register_org()


@pytest.fixture()
def run(client, db_session, org):
    return make_run(client, db_session, org)


# --- database integrity --------------------------------------------------------

def test_arc_valid_parent_accepted(db_session, run):
    e = svc.start_execution(db_session, organization_id=run.organization_id,
                            parent_type=AIParentType.VISIBILITY_RUN, parent_id=run.id,
                            operation_type=AIOperationType.CHAT, provider="anthropic", model=MODEL)
    assert e.visibility_run_id == run.id and e.status == "running"


def test_arc_no_parent_rejected_by_database(db_session, run):
    with pytest.raises(exc.DBAPIError, match="exactly one parent"):
        raw_insert(db_session, organization_id=run.organization_id)
    db_session.rollback()


def test_arc_unknown_parent_type_rejected(db_session, run):
    with pytest.raises(exc.IntegrityError):
        raw_insert(db_session, organization_id=run.organization_id, parent_type="research_task",
                   visibility_run_id=run.id)
    db_session.rollback()


def test_arc_cardinality_constraint_present(db_session):
    # Phase 17 had one arc column. The AI Center (ADR-093, migration 0020)
    # added a second parent domain, ai_job; the cardinality CHECK written over
    # the arc now covers both (the two-parents case itself is tested in
    # test_ai_center.py::test_arc_now_rejects_two_parents).
    assert ARC_COLUMNS == ("visibility_run_id", "ai_job_id")
    defn = db_session.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conname='ck_ai_executions_arc_cardinality'")).scalar_one()
    assert "num_nonnulls(visibility_run_id, ai_job_id) <= 1" in defn


def test_cross_tenant_parent_rejected(db_session, client, register_org, run):
    other = register_org()
    with pytest.raises(exc.IntegrityError):
        raw_insert(db_session, organization_id=uuid.UUID(other["organization"]["id"]),
                   visibility_run_id=run.id)
    db_session.rollback()


def test_cross_tenant_knowledge_object_and_user_rejected(db_session, client, register_org, org, run):
    other = register_org()
    ko = client.post("/api/v1/knowledge", headers=other["headers"],
                     json={"canonical_name": "Foreign KO", "object_type": "ingredient"}).json()
    with pytest.raises(exc.IntegrityError):
        raw_insert(db_session, organization_id=run.organization_id, visibility_run_id=run.id,
                   knowledge_object_id=uuid.UUID(ko["id"]))
    db_session.rollback()
    with pytest.raises(exc.IntegrityError):
        raw_insert(db_session, organization_id=run.organization_id, visibility_run_id=run.id,
                   user_id=uuid.UUID(other["user"]["id"]))
    db_session.rollback()


def test_cross_tenant_previous_execution_rejected(db_session, register_org, client, run):
    other = register_org()
    other_run = make_run(client, db_session, other)
    foreign = svc.start_execution(db_session, organization_id=other_run.organization_id,
                                  parent_type=AIParentType.VISIBILITY_RUN, parent_id=other_run.id,
                                  operation_type=AIOperationType.CHAT, provider="anthropic", model=MODEL)
    svc.finalize_failure(db_session, foreign, status=AIExecutionStatus.FAILED, error_code="x", error_message="x")
    with pytest.raises(svc.InvalidExecutionChain):
        svc.start_execution(db_session, organization_id=run.organization_id,
                            parent_type=AIParentType.VISIBILITY_RUN, parent_id=run.id,
                            operation_type=AIOperationType.CHAT, provider="anthropic", model=MODEL,
                            previous=foreign, attempt_reason=AIAttemptReason.RETRY)
    with pytest.raises(exc.IntegrityError):  # and the DB refuses it even if app code is bypassed
        raw_insert(db_session, organization_id=run.organization_id, visibility_run_id=run.id,
                   previous_execution_id=foreign.id, attempt_reason="retry")
    db_session.rollback()


def test_parent_deletion_preserves_execution(db_session, run):
    e = svc.start_execution(db_session, organization_id=run.organization_id,
                            parent_type=AIParentType.VISIBILITY_RUN, parent_id=run.id,
                            operation_type=AIOperationType.CHAT, provider="anthropic", model=MODEL)
    svc.finalize_success(db_session, e, input_tokens=1, output_tokens=2, price=None)
    org_id, eid = run.organization_id, e.id
    db_session.execute(text("DELETE FROM visibility_runs WHERE id = :id"), {"id": run.id})
    db_session.commit()
    row = db_session.execute(text(
        "SELECT organization_id, visibility_run_id, parent_type, status FROM ai_executions WHERE id=:id"),
        {"id": eid}).one()
    assert row.organization_id == org_id          # organization_id preserved
    assert row.visibility_run_id is None          # parent FK nulled
    assert row.parent_type == "visibility_run"    # attribution kept
    assert row.status == "succeeded"              # accounting fact untouched


def test_terminal_execution_is_immutable_app_and_db(db_session, run):
    e = svc.start_execution(db_session, organization_id=run.organization_id,
                            parent_type=AIParentType.VISIBILITY_RUN, parent_id=run.id,
                            operation_type=AIOperationType.CHAT, provider="anthropic", model=MODEL)
    svc.finalize_failure(db_session, e, status=AIExecutionStatus.FAILED, error_code="x", error_message="x")
    with pytest.raises(svc.ExecutionAlreadyTerminal):
        svc.finalize_success(db_session, e, input_tokens=1, output_tokens=1, price=None)
    for sql in ("UPDATE ai_executions SET status='succeeded' WHERE id=:id",
                "UPDATE ai_executions SET estimated_provider_cost=0, currency='USD' WHERE id=:id",
                "UPDATE ai_executions SET input_tokens=999 WHERE id=:id",
                "UPDATE ai_executions SET provider='other' WHERE id=:id"):
        with pytest.raises(exc.DBAPIError, match="immutable"):
            db_session.execute(text(sql), {"id": e.id})
            db_session.flush()
        db_session.rollback()


# --- wrapper + adapter (MOCK_VERIFIED) --------------------------------------

def test_success_records_usage_cost_and_is_created_before_call(db_session, run):
    s = Script(db_session, [(200, ok_body(), {"request-id": "req_abc"})])
    out = invoke_once(db_session, ctx_for(run), ModelTarget("anthropic", MODEL), req(),
                      adapter=adapter_for(s), pricing=PRICING)
    e = out.execution
    assert s.running_at_call == [1]                     # row existed BEFORE the provider call
    assert e.status == "succeeded" and e.completed_at is not None and e.duration_ms is not None
    assert (e.input_tokens, e.output_tokens, e.total_tokens) == (10, 20, 30)
    assert e.estimated_provider_cost == Decimal("0.000110")   # (10*1 + 20*5) / 1e6
    assert e.actual_provider_cost is None                     # never copied from estimate
    assert e.currency == "USD"
    assert e.provider_request_id == "req_abc" and e.model_version == MODEL + "-v"
    assert s.calls[0].headers["x-api-key"] == FAKE_KEY


def test_usage_absent_stays_null(db_session, run):
    s = Script(db_session, [(200, ok_body(usage=False), {})])
    e = invoke_once(db_session, ctx_for(run), ModelTarget("anthropic", MODEL), req(),
                    adapter=adapter_for(s), pricing=PRICING).execution
    assert e.input_tokens is None and e.output_tokens is None and e.total_tokens is None
    assert e.estimated_provider_cost is None and e.currency is None
    assert e.provider_request_id == "msg_test_1"   # body id used; never fabricated


def test_unknown_price_is_null_not_zero(db_session, run):
    s = Script(db_session, [(200, ok_body(), {})])
    e = invoke_once(db_session, ctx_for(run), ModelTarget("anthropic", MODEL), req(),
                    adapter=adapter_for(s), pricing=ConfiguredPricing("{}")).execution
    assert e.input_tokens == 10 and e.estimated_provider_cost is None and e.currency is None


@pytest.mark.parametrize("response,status,code", [
    ((401, {"error": "nope " + PROMPT}, {}), "failed", "auth_failed"),
    ((429, {}, {}), "rate_limited", "rate_limited"),
    (httpx.ReadTimeout("slow"), "timeout", "timeout"),
    (httpx.ConnectError("down"), "failed", "network_error"),
    ((200, b"{not json", {}), "failed", "invalid_response"),
    ((200, {"no_content": True}, {}), "failed", "invalid_response"),
    ((503, {}, {}), "failed", "provider_error"),
])
def test_failures_create_terminal_execution_with_safe_error(db_session, run, response, status, code):
    s = Script(db_session, [response])
    out = invoke_once(db_session, ctx_for(run), ModelTarget("anthropic", MODEL), req(),
                      adapter=adapter_for(s), pricing=PRICING)
    e = out.execution
    assert e.status == status and e.error_code == code and e.completed_at is not None
    assert PROMPT not in (e.error_message or "") and FAKE_KEY not in (e.error_message or "")


def test_oversized_response_is_rejected(db_session, run, monkeypatch):
    monkeypatch.setattr(settings, "AI_MAX_RESPONSE_BYTES", 64)
    s = Script(db_session, [(200, ok_body(text_="x" * 500), {})])
    e = invoke_once(db_session, ctx_for(run), ModelTarget("anthropic", MODEL), req(),
                    adapter=adapter_for(s), pricing=PRICING).execution
    assert e.status == "failed" and e.error_code == "response_too_large"


def test_retry_chain_failed_failed_succeeded(db_session, run, client, org):
    s = Script(db_session, [(503, {}, {}), (503, {}, {}), (200, ok_body(), {})])
    out = invoke_with_policy(db_session, ctx_for(run), [ModelTarget("anthropic", MODEL)], req(),
                             attempts_per_target=3, adapters={"anthropic": adapter_for(s)}, pricing=PRICING)
    e1, e2, e3 = out.executions
    assert [e.status for e in (e1, e2, e3)] == ["failed", "failed", "succeeded"]
    assert e1.previous_execution_id is None and e1.attempt_reason is None
    assert (e2.previous_execution_id, e2.attempt_reason) == (e1.id, "retry")
    assert (e3.previous_execution_id, e3.attempt_reason) == (e2.id, "retry")
    db_session.expire_all()
    assert db_session.get(AIExecution, e1.id).status == "failed"   # E1 never rewritten
    chain = client.get(f"/api/v1/ai-executions/{e3.id}/chain", headers=org["headers"]).json()
    assert [c["id"] for c in chain] == [str(e1.id), str(e2.id), str(e3.id)]


def test_retry_costs_are_independent_and_not_double_counted(db_session, run):
    s = Script(db_session, [(503, {}, {}), (200, ok_body(), {})])
    out = invoke_with_policy(db_session, ctx_for(run), [ModelTarget("anthropic", MODEL)], req(),
                             attempts_per_target=2, adapters={"anthropic": adapter_for(s)}, pricing=PRICING)
    failed, ok = out.executions
    assert failed.estimated_provider_cost is None           # provider reported no usage for the 503
    assert ok.estimated_provider_cost == Decimal("0.000110")
    total = db_session.execute(select(func.sum(AIExecution.estimated_provider_cost))
                               .where(AIExecution.visibility_run_id == run.id)).scalar_one()
    assert total == Decimal("0.000110")


def test_provider_fallback_creates_new_execution(db_session, run):
    s1 = Script(db_session, [(401, {}, {})])
    s2 = Script(db_session, [(200, ok_body(), {})])
    out = invoke_with_policy(
        db_session, ctx_for(run), [ModelTarget("anthropic", MODEL), ModelTarget("backup", "backup-model")],
        req(), adapters={"anthropic": adapter_for(s1), "backup": adapter_for(s2, BackupAdapter)},
        pricing=PRICING)
    e1, e2 = out.executions
    assert (e1.provider, e1.status) == ("anthropic", "failed")
    assert (e2.provider, e2.status, e2.attempt_reason) == ("backup", "succeeded", "provider_fallback")
    assert e2.previous_execution_id == e1.id


def test_model_fallback_creates_new_execution(db_session, run):
    s = Script(db_session, [(400, {}, {}), (200, ok_body(), {})])
    a = adapter_for(s)
    out = invoke_with_policy(
        db_session, ctx_for(run), [ModelTarget("anthropic", MODEL), ModelTarget("anthropic", "model-b")],
        req(), adapters={"anthropic": a}, pricing=PRICING)
    e1, e2 = out.executions
    assert (e1.model, e1.status) == (MODEL, "failed")
    assert (e2.model, e2.status, e2.attempt_reason) == ("model-b", "succeeded", "model_fallback")
    assert e2.estimated_provider_cost == Decimal("0.000180")   # model-b price, not model A's


def test_manual_retry_links_previous_terminal_execution(db_session, run):
    s = Script(db_session, [(401, {}, {}), (200, ok_body(), {})])
    first = invoke_with_policy(db_session, ctx_for(run), [ModelTarget("anthropic", MODEL)], req(),
                               adapters={"anthropic": adapter_for(s)}, pricing=PRICING).final.execution
    again = invoke_with_policy(db_session, ctx_for(run), [ModelTarget("anthropic", MODEL)], req(),
                               adapters={"anthropic": adapter_for(s)}, pricing=PRICING,
                               manual_retry_of=first)
    e = again.executions[0]
    assert (e.previous_execution_id, e.attempt_reason, e.status) == (first.id, "manual_retry", "succeeded")


def test_not_configured_creates_no_execution(db_session, run):
    before = exec_count(db_session)
    with pytest.raises(ProviderNotConfigured):
        invoke_once(db_session, ctx_for(run), ModelTarget("anthropic", MODEL), req(),
                    adapter=AnthropicAdapter(api_key=""), pricing=PRICING)
    assert exec_count(db_session) == before


def test_budget_gate_required_before_any_call(db_session, run):
    s = Script(db_session, [(200, ok_body(), {})])
    ctx = InvocationContext(organization_id=run.organization_id, parent_type=AIParentType.VISIBILITY_RUN,
                            parent_id=run.id, budget_cleared=False)
    before = exec_count(db_session)
    with pytest.raises(BudgetGateNotCleared):
        invoke_once(db_session, ctx, ModelTarget("anthropic", MODEL), req(), adapter=adapter_for(s))
    assert s.calls == [] and exec_count(db_session) == before


def test_adapter_refuses_call_without_persisted_running_execution(db_session, run):
    s = Script(db_session, [(200, ok_body(), {})])
    with pytest.raises(InvocationPermitError):
        adapter_for(s).invoke(req(), model=MODEL, execution=None)
    with pytest.raises(InvocationPermitError):
        adapter_for(s).invoke(req(), model=MODEL, execution=AIExecution(status="running"))
    assert s.calls == []


def test_no_provider_http_outside_adapter_package():
    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in app_dir.rglob("*.py"):
        rel = path.relative_to(app_dir).as_posix()
        if rel.startswith("integrations/llm/") or rel == "core/config.py":
            continue
        src = path.read_text(encoding="utf-8")
        if "api.anthropic.com" in src or "/v1/messages" in src or "x-api-key" in src:
            offenders.append(rel)
    assert offenders == []


def test_machine_actor_attribution(db_session, run):
    inst = Installation(organization_id=run.organization_id, name="wp", adapter_type=AdapterType.WORDPRESS,
                        status=InstallationStatus.ACTIVE)
    db_session.add(inst)
    db_session.commit()
    s = Script(db_session, [(200, ok_body(), {})])
    e = invoke_once(db_session, ctx_for(run, installation_id=inst.id), ModelTarget("anthropic", MODEL), req(),
                    adapter=adapter_for(s), pricing=PRICING).execution
    assert e.user_id is None and e.installation_id == inst.id


def test_stale_running_reclaimed_as_abandoned(db_session, run):
    # started_at is a creation fact (immutable), so an "old" row is inserted
    # old rather than back-dated.
    old_id = uuid.uuid4()
    db_session.execute(text(
        "INSERT INTO ai_executions (id, organization_id, parent_type, visibility_run_id, operation_type, "
        "provider, model, started_at, status, created_at, updated_at) VALUES (:id, :org, 'visibility_run', "
        ":run, 'chat', 'anthropic', :model, now() - interval '2 hours', 'running', now(), now())"),
        {"id": old_id, "org": run.organization_id, "run": run.id, "model": MODEL})
    db_session.commit()
    old = db_session.get(AIExecution, old_id)
    young = svc.start_execution(db_session, organization_id=run.organization_id,
                                parent_type=AIParentType.VISIBILITY_RUN, parent_id=run.id,
                                operation_type=AIOperationType.CHAT, provider="anthropic", model=MODEL)
    with pytest.raises(ValueError):
        svc.reclaim_stale_executions(db_session, older_than_seconds=5)
    assert svc.reclaim_stale_executions(db_session, older_than_seconds=900) >= 1
    db_session.expire_all()
    o, y = db_session.get(AIExecution, old.id), db_session.get(AIExecution, young.id)
    assert o.status == "abandoned" and o.error_code == "stale_running_reclaimed"
    assert o.estimated_provider_cost is None and o.actual_provider_cost is None
    assert y.status == "running"


# --- visibility domain provenance ---------------------------------------------

def _patch_provider(monkeypatch, db_session, responses):
    from app.integrations.visibility import fixture
    from app.integrations.visibility.llm import LLMVisibilityProvider

    s = Script(db_session, responses)
    monkeypatch.setitem(fixture._REGISTRY, "anthropic",
                        LLMVisibilityProvider(adapters={"anthropic": adapter_for(s)}, pricing=PRICING))
    return s


def test_visibility_run_links_observation_to_execution(db_session, client, org, run, monkeypatch):
    s = _patch_provider(monkeypatch, db_session, [(200, ok_body(), {})])
    audit_before = db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    visibility_run_service.execute_run(db_session, run_id=run.id)
    test_row = db_session.execute(select(VisibilityTest).where(VisibilityTest.run_id == run.id)).scalar_one()
    execution = db_session.get(AIExecution, test_row.ai_execution_id)
    assert execution.visibility_run_id == run.id and execution.status == "succeeded"
    assert execution.organization_id == test_row.organization_id
    assert test_row.provider_outcome == ProviderOutcome.SUCCESS.value
    assert test_row.mentioned == SignalPresence.PRESENT and test_row.url_present == SignalPresence.PRESENT
    assert test_row.cited == SignalPresence.NOT_CHECKED        # not evaluated => not claimed
    assert test_row.parser_version == "v1-llm"
    # Audit and execution stay separate: invoking a model writes no audit row.
    assert db_session.execute(select(func.count()).select_from(AuditLog)
                              .where(AuditLog.resource_id == execution.id)).scalar_one() == 0
    assert db_session.execute(select(func.count()).select_from(AuditLog)).scalar_one() == audit_before
    # Raw content lives on the domain observation, never on the execution.
    assert not hasattr(execution, "prompt") and not hasattr(execution, "response")
    assert len(s.calls) == 1


def test_visibility_retry_links_terminal_execution(db_session, run, monkeypatch):
    _patch_provider(monkeypatch, db_session, [(429, {}, {}), (200, ok_body(), {})])
    visibility_run_service.execute_run(db_session, run_id=run.id)
    test_row = db_session.execute(select(VisibilityTest).where(VisibilityTest.run_id == run.id)).scalar_one()
    execs = db_session.execute(select(AIExecution).where(AIExecution.visibility_run_id == run.id)
                               .order_by(AIExecution.started_at)).scalars().all()
    assert [e.status for e in execs] == ["rate_limited", "succeeded"]
    assert test_row.ai_execution_id == execs[1].id and execs[1].previous_execution_id == execs[0].id


def test_visibility_without_credential_records_no_execution(db_session, run):
    # The registered provider uses the real settings, which hold no key.
    assert settings.ANTHROPIC_API_KEY is None
    visibility_run_service.execute_run(db_session, run_id=run.id)
    row = db_session.execute(select(VisibilityTest).where(VisibilityTest.run_id == run.id)).scalar_one()
    assert row.provider_outcome in (ProviderOutcome.NOT_CONFIGURED.value, ProviderOutcome.AUTH_REQUIRED.value)
    assert row.ai_execution_id is None
    assert db_session.execute(select(func.count()).select_from(AIExecution)
                              .where(AIExecution.visibility_run_id == run.id)).scalar_one() == 0


def test_visibility_wrong_platform_is_not_faked(db_session, client, register_org, monkeypatch):
    other = register_org()
    run = make_run(client, db_session, other, platform=VisibilityPlatform.CHATGPT)
    s = _patch_provider(monkeypatch, db_session, [(200, ok_body(), {})])
    visibility_run_service.execute_run(db_session, run_id=run.id)
    row = db_session.execute(select(VisibilityTest).where(VisibilityTest.run_id == run.id)).scalar_one()
    assert row.provider_outcome == ProviderOutcome.UNAVAILABLE.value and row.ai_execution_id is None
    assert s.calls == []   # asking Claude is not observing ChatGPT


# --- API / security --------------------------------------------------------------

def _one_execution(db_session, run):
    s = Script(db_session, [(200, ok_body(), {})])
    return invoke_once(db_session, ctx_for(run), ModelTarget("anthropic", MODEL), req(),
                       adapter=adapter_for(s), pricing=PRICING).execution


def test_api_tenant_isolation_and_read_only(db_session, client, register_org, org, run):
    e = _one_execution(db_session, run)
    other = register_org()
    own = client.get(f"/api/v1/ai-executions/{e.id}", headers=org["headers"])
    assert own.status_code == 200
    assert own.json()["provider_cost_visible"] is True                     # registering user is OWNER
    assert own.json()["provider_cost"]["estimated_provider_cost"] is not None
    assert client.get(f"/api/v1/ai-executions/{e.id}", headers=other["headers"]).status_code == 404
    assert client.get(f"/api/v1/ai-executions/{e.id}/chain", headers=other["headers"]).status_code == 404
    foreign_list = client.get("/api/v1/ai-executions", headers=other["headers"]).json()
    assert foreign_list["total"] == 0 and foreign_list["items"] == []
    own_list = client.get("/api/v1/ai-executions?status=succeeded", headers=org["headers"]).json()
    assert own_list["total"] == 1
    assert client.get(f"/api/v1/ai-executions/{e.id}").status_code == 401
    assert client.post("/api/v1/ai-executions", json={}, headers=org["headers"]).status_code == 405
    for method in ("patch", "put", "delete"):
        r = getattr(client, method)(f"/api/v1/ai-executions/{e.id}", headers=org["headers"],
                                    **({} if method == "delete" else {"json": {"status": "succeeded",
                                                                             "estimated_provider_cost": 0}}))
        assert r.status_code == 405


def test_no_secret_or_prompt_leaks(db_session, client, org, run, caplog):
    caplog.set_level(logging.DEBUG)
    e = _one_execution(db_session, run)
    body = client.get(f"/api/v1/ai-executions/{e.id}", headers=org["headers"]).text
    assert FAKE_KEY not in body and PROMPT not in body
    assert FAKE_KEY not in caplog.text and PROMPT not in caplog.text
    row = db_session.execute(text("SELECT row_to_json(a)::text FROM ai_executions a WHERE id=:id"),
                             {"id": e.id}).scalar_one()
    assert FAKE_KEY not in row and PROMPT not in row


# --- budget settlement (found by the Phase 17 live runtime run) ---------------

def _budget_spent(db_session, org_id):
    return db_session.execute(text(
        "SELECT period_spent FROM visibility_budgets WHERE organization_id=:o"), {"o": org_id}).scalar_one()


def test_no_call_means_no_budget_spend(db_session, run, monkeypatch):
    from app.integrations.visibility import fixture
    from app.integrations.visibility.llm import LLMVisibilityProvider

    # Priced, but no credential: the probe is refused before any call.
    monkeypatch.setitem(fixture._REGISTRY, "anthropic",
                        LLMVisibilityProvider(adapters={"anthropic": AnthropicAdapter(api_key="")},
                                              pricing=PRICING))
    visibility_run_service.execute_run(db_session, run_id=run.id)
    assert _budget_spent(db_session, run.organization_id) == 0


def test_budget_settles_to_chain_estimated_cost(db_session, run, monkeypatch):
    _patch_provider(monkeypatch, db_session, [(200, ok_body(), {})])
    visibility_run_service.execute_run(db_session, run_id=run.id)
    assert _budget_spent(db_session, run.organization_id) == Decimal("0.0001")  # 0.000110 at NUMERIC(10,4)



# --- Phase 17 closure: adversarial immutability --------------------------------

def _terminal(db_session, run, *, succeed=True, **kw):
    e = svc.start_execution(db_session, organization_id=run.organization_id,
                            parent_type=AIParentType.VISIBILITY_RUN, parent_id=run.id,
                            operation_type=AIOperationType.CHAT, provider="anthropic", model=MODEL, **kw)
    if succeed:
        return svc.finalize_success(db_session, e, input_tokens=10, output_tokens=20, price=PRICING.price("anthropic", MODEL),
                                    provider_request_id="req_1", model_version="v1")
    return svc.finalize_failure(db_session, e, status=AIExecutionStatus.FAILED, error_code="provider_error",
                                error_message="boom", input_tokens=3, output_tokens=0,
                                price=PRICING.price("anthropic", MODEL))


_NEW_VALUE = {  # a different, type-valid value for every protected column
    "id": "gen_random_uuid()", "created_at": "now() - interval '1 day'",
    "organization_id": "gen_random_uuid()", "parent_type": "'visibility_run'::varchar || ''",
    "operation_type": "'embedding'", "provider": "'other'", "model": "'other-model'", "stage": "'x'",
    "started_at": "now() - interval '1 day'", "prompt_reference": "'p'", "input_hash": "'h'",
    "previous_execution_id": "gen_random_uuid()", "attempt_reason": "'retry'", "request_id": "'r'",
    "status": "'failed'", "completed_at": "now() + interval '1 day'", "duration_ms": "123456",
    "error_code": "'changed'", "error_message": "'changed'", "input_tokens": "999",
    "output_tokens": "999", "total_tokens": "1998", "estimated_provider_cost": "0",
    "actual_provider_cost": "0", "currency": "'EUR'", "provider_request_id": "'forged'",
    "model_version": "'forged'",
    "visibility_run_id": "gen_random_uuid()", "knowledge_object_id": "gen_random_uuid()",
    "user_id": "gen_random_uuid()", "installation_id": "gen_random_uuid()",
}


@pytest.mark.parametrize("column", sorted(_NEW_VALUE))
@pytest.mark.parametrize("succeed", [True, False], ids=["terminal_success", "terminal_failure"])
def test_every_column_of_a_terminal_execution_is_immutable_via_sql(db_session, run, column, succeed):
    e = _terminal(db_session, run, succeed=succeed)
    value = _NEW_VALUE[column]
    if column == "parent_type":
        value = "'research_task'"
    if column == "status" and not succeed:
        value = "'succeeded'"
    with pytest.raises(exc.DBAPIError, match="immutable|parent_type|violates"):
        db_session.execute(text(f"UPDATE ai_executions SET {column} = {value} WHERE id = :id"), {"id": e.id})
        db_session.flush()
    db_session.rollback()


def test_link_columns_cannot_be_nulled_while_target_exists(db_session, run):
    e = _terminal(db_session, run)
    with pytest.raises(exc.DBAPIError, match="visibility_run_id is immutable"):
        db_session.execute(text("UPDATE ai_executions SET visibility_run_id = NULL WHERE id=:id"), {"id": e.id})
        db_session.flush()
    db_session.rollback()


def test_creation_facts_frozen_even_while_running(db_session, run):
    e = svc.start_execution(db_session, organization_id=run.organization_id,
                            parent_type=AIParentType.VISIBILITY_RUN, parent_id=run.id,
                            operation_type=AIOperationType.CHAT, provider="anthropic", model=MODEL)
    for col, val in (("provider", "'other'"), ("model", "'other'"), ("organization_id", "gen_random_uuid()"),
                     ("started_at", "now() - interval '1 day'")):
        with pytest.raises(exc.DBAPIError, match="creation facts are immutable"):
            db_session.execute(text(f"UPDATE ai_executions SET {col} = {val} WHERE id=:id"), {"id": e.id})
            db_session.flush()
        db_session.rollback()


def test_orm_mutation_of_terminal_execution_rejected(db_session, run):
    e = _terminal(db_session, run)
    e.estimated_provider_cost = Decimal("0")
    e.input_tokens = 1
    with pytest.raises(exc.DBAPIError, match="immutable"):
        db_session.commit()
    db_session.rollback()


def test_stale_object_concurrent_finalize_cannot_overwrite(db_session, run):
    e = svc.start_execution(db_session, organization_id=run.organization_id,
                            parent_type=AIParentType.VISIBILITY_RUN, parent_id=run.id,
                            operation_type=AIOperationType.CHAT, provider="anthropic", model=MODEL)
    # Another worker (or the reclaimer) finalizes the row behind this
    # object's back; the in-memory object still says "running".
    db_session.execute(text("UPDATE ai_executions SET status='abandoned', completed_at=now() WHERE id=:id"),
                       {"id": e.id})
    assert e.status == "running"
    with pytest.raises(svc.ExecutionAlreadyTerminal):
        svc.finalize_success(db_session, e, input_tokens=1, output_tokens=1, price=None)
    db_session.expire_all()
    assert db_session.get(AIExecution, e.id).status == "abandoned"


def test_execution_rows_cannot_be_deleted(db_session, run):
    e = _terminal(db_session, run)
    with pytest.raises(exc.DBAPIError, match="cannot be deleted"):
        db_session.execute(text("DELETE FROM ai_executions WHERE id=:id"), {"id": e.id})
        db_session.flush()
    db_session.rollback()


def test_parent_delete_and_recreate_does_not_relink(db_session, run):
    e = _terminal(db_session, run)
    run_id, org_id = run.id, run.organization_id
    db_session.execute(text("DELETE FROM visibility_runs WHERE id=:id"), {"id": run_id})
    db_session.commit()
    with pytest.raises(exc.DBAPIError, match="visibility_run_id is immutable"):
        db_session.execute(text("UPDATE ai_executions SET visibility_run_id=:r WHERE id=:id"),
                           {"r": run_id, "id": e.id})
        db_session.flush()
    db_session.rollback()
    row = db_session.execute(text("SELECT visibility_run_id, organization_id FROM ai_executions WHERE id=:id"),
                             {"id": e.id}).one()
    assert row.visibility_run_id is None and row.organization_id == org_id


def test_tenant_offboarding_removes_executions_including_chains(db_session, run):
    s = Script(db_session, [(503, {}, {}), (200, ok_body(), {})])
    invoke_with_policy(db_session, ctx_for(run), [ModelTarget("anthropic", MODEL)], req(),
                       adapters={"anthropic": adapter_for(s)}, pricing=PRICING)
    org_id = run.organization_id
    db_session.execute(text("DELETE FROM organizations WHERE id=:o"), {"o": org_id})
    db_session.flush()
    assert db_session.execute(text("SELECT count(*) FROM ai_executions WHERE organization_id=:o"),
                              {"o": org_id}).scalar_one() == 0


# --- Phase 17 closure: admin-only provider cost -----------------------------------

def test_provider_cost_hidden_from_non_admin_roles(db_session, client, org, run):
    e = _one_execution(db_session, run)
    # A real VIEWER in the same tenant, created through the real API and
    # logged in through the real OAuth2 form endpoint (role comes from the DB).
    assert client.post("/api/v1/users", headers=org["headers"], json={
        "email": "viewer-p17@example.dev", "name": "Viewer", "password": "viewerpass123",
        "role": "viewer"}).status_code == 201
    token = client.post("/api/v1/auth/login", data={"username": "viewer-p17@example.dev",
                                                    "password": "viewerpass123"}).json()["access_token"]
    viewer = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/v1/ai-executions/{e.id}", headers=viewer).status_code == 200
    for url in (f"/api/v1/ai-executions/{e.id}", f"/api/v1/ai-executions/{e.id}/chain", "/api/v1/ai-executions"):
        body = client.get(url, headers=viewer).json()
        rows = body["items"] if isinstance(body, dict) and "items" in body else (body if isinstance(body, list) else [body])
        for r in rows:
            assert r["provider_cost_visible"] is False and r["provider_cost"] is None
            assert "estimated_provider_cost" not in r and "actual_provider_cost" not in r
    r = client.get("/api/v1/ai-executions?sort_by=estimated_provider_cost", headers=viewer)
    assert r.status_code == 422   # cost is not a sort key: ordering would leak it


def test_reclaim_is_scheduled_with_celery_beat():
    from app.workers.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["ai-executions-reclaim-stale"]
    assert entry["task"] == "ai_executions.reclaim_stale"
    assert entry["schedule"] == float(settings.AI_EXECUTION_RECLAIM_INTERVAL_SECONDS)
    assert "ai_executions.reclaim_stale" in celery_app.tasks


def test_unconfigured_target_is_skipped_without_a_row(db_session, run):
    s = Script(db_session, [(200, ok_body(), {})])
    out = invoke_with_policy(
        db_session, ctx_for(run), [ModelTarget("backup", "backup-model"), ModelTarget("anthropic", MODEL)], req(),
        adapters={"backup": BackupAdapter(api_key=""), "anthropic": adapter_for(s)}, pricing=PRICING)
    assert len(out.executions) == 1 and out.succeeded
    e = out.executions[0]
    assert e.provider == "anthropic" and e.previous_execution_id is None and e.attempt_reason is None


# --- Phase 17 closure: finalization race + cost single-source -------------------

def test_reclaimed_mid_flight_is_not_overwritten_nor_reported_as_success(db_session, run):
    class ReclaimDuringCall(Script):
        def handler(self, request):
            # Another actor (the stale reclaimer) terminalizes the row while
            # the provider call is in flight.
            db_session.execute(text(
                "UPDATE ai_executions SET status='abandoned', completed_at=now(), "
                "error_code='stale_running_reclaimed' WHERE status='running'"))
            db_session.commit()
            return super().handler(request)

    s = ReclaimDuringCall(db_session, [(200, ok_body(), {})])
    out = invoke_once(db_session, ctx_for(run), ModelTarget("anthropic", MODEL), req(),
                      adapter=adapter_for(s), pricing=PRICING)
    assert not out.succeeded and out.result is None
    assert out.error.error_code == "finalized_elsewhere"
    db_session.expire_all()
    row = db_session.get(AIExecution, out.execution.id)
    assert row.status == "abandoned" and row.input_tokens is None   # reclaimer's verdict stands


def test_observation_does_not_duplicate_provider_cost(db_session, client, org, run, monkeypatch):
    _patch_provider(monkeypatch, db_session, [(200, ok_body(), {})])
    visibility_run_service.execute_run(db_session, run_id=run.id)
    obs = db_session.execute(select(VisibilityTest).where(VisibilityTest.run_id == run.id)).scalar_one()
    assert obs.estimated_cost is None                                  # cost lives on the execution
    assert db_session.get(AIExecution, obs.ai_execution_id).estimated_provider_cost == Decimal("0.000110")


def test_cors_is_closed_by_default(client):
    r = client.options("/api/v1/ai-executions", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


@pytest.mark.parametrize("raw", ["not json", '{"anthropic/%s": {"input_per_mtok": "abc"}}' % MODEL,
                                 '{"anthropic/%s": {"output_per_mtok": "1"}}' % MODEL, "[]"])
def test_malformed_pricing_is_unknown_not_zero(raw):
    # Added after mutation testing: forcing malformed pricing to a zero price survived the suite.
    assert ConfiguredPricing(raw).price("anthropic", MODEL) is None


# --- Project-closure audit: actor delete-and-recreate -------------------------------

@pytest.mark.parametrize("actor", ["user", "installation"])
def test_actor_delete_and_recreate_does_not_relink(db_session, run, actor):
    org_id = run.organization_id
    actor_id = uuid.uuid4()
    if actor == "user":
        insert = ("INSERT INTO users (id, organization_id, email, name, password_hash, role, status, created_at, "
                  "updated_at) VALUES (:id, :o, :e, 'Actor', 'x', 'viewer', 'active', now(), now())")
        params = {"id": actor_id, "o": org_id, "e": f"actor-{actor_id}@example.com"}
        table, col = "users", "user_id"
    else:
        insert = ("INSERT INTO installations (id, organization_id, name, adapter_type, status, created_at, updated_at) "
                  "VALUES (:id, :o, 'wp', 'wordpress', 'active', now(), now())")
        params = {"id": actor_id, "o": org_id}
        table, col = "installations", "installation_id"
    db_session.execute(text(insert), params)
    db_session.commit()
    ctx = ctx_for(run, **({"user_id": actor_id} if actor == "user" else {"installation_id": actor_id}))
    s = Script(db_session, [(200, ok_body(), {})])
    e = invoke_once(db_session, ctx, ModelTarget("anthropic", MODEL), req(), adapter=adapter_for(s),
                    pricing=PRICING).execution
    # delete the actor -> ON DELETE SET NULL (col) clears only that column
    db_session.execute(text(f"DELETE FROM {table} WHERE id=:id"), {"id": actor_id})
    db_session.commit()
    # recreate an actor with the SAME id; the execution must not be re-linked to it
    db_session.execute(text(insert), params)
    db_session.commit()
    with pytest.raises(exc.DBAPIError, match=f"{col} is immutable"):
        db_session.execute(text(f"UPDATE ai_executions SET {col}=:a WHERE id=:id"), {"a": actor_id, "id": e.id})
        db_session.flush()
    db_session.rollback()
    row = db_session.execute(text(f"SELECT {col} AS link, organization_id, status, input_tokens "
                                  "FROM ai_executions WHERE id=:id"), {"id": e.id}).one()
    assert row.link is None and row.organization_id == org_id
    assert row.status == "succeeded" and row.input_tokens == 10   # accounting facts untouched


# --- two real providers: Anthropic and OpenAI behind one policy (ADR-121) -------------------------

class OpenAIScript(Script):
    """Same scripted behaviour, in OpenAI's own response shape."""

    @staticmethod
    def ok(text="from openai", finish="stop"):
        return (200, {"id": "chatcmpl-1", "model": "gpt-x",
                      "choices": [{"index": 0, "finish_reason": finish,
                                   "message": {"role": "assistant", "content": text}}],
                      "usage": {"prompt_tokens": 7, "completion_tokens": 3}}, {"x-request-id": "req_oa"})


def openai_adapter(script):
    from app.integrations.llm.openai import OpenAIAdapter
    return OpenAIAdapter(transport=httpx.MockTransport(script.handler), api_key=FAKE_KEY)


def test_a_failing_anthropic_falls_over_to_openai(client, db_session, org, run):
    """The capability an admin orders with a routing policy: provider A first, provider B behind it.
    Everything here is MOCK_VERIFIED — both adapters run for real against a mock transport."""
    first = Script(db_session, [(500, {"error": "upstream"}, None), (500, {"error": "upstream"}, None)])
    second = OpenAIScript(db_session, [OpenAIScript.ok()])
    outcome = invoke_with_policy(
        db_session, ctx_for(run),
        [ModelTarget("anthropic", "claude-x"), ModelTarget("openai", "gpt-x")],
        req(), attempts_per_target=2,
        adapters={"anthropic": adapter_for(first), "openai": openai_adapter(second)},
        pricing=ConfiguredPricing(),
    )
    # the first provider was tried twice (500 is retryable), then the second answered
    assert len(first.calls) == 2 and len(second.calls) == 1
    assert outcome.final.succeeded and outcome.final.result.text == "from openai"
    assert len(outcome.executions) == 3

    rows = [db_session.get(AIExecution, e.id) for e in outcome.executions]
    assert [r.provider for r in rows] == ["anthropic", "anthropic", "openai"]
    assert [r.status for r in rows] == [AIExecutionStatus.FAILED.value, AIExecutionStatus.FAILED.value,
                                        AIExecutionStatus.SUCCEEDED.value]
    # every attempt is its own execution, chained to the one before — nothing is ever rewritten
    assert rows[0].previous_execution_id is None
    assert rows[1].previous_execution_id == rows[0].id and rows[1].attempt_reason == AIAttemptReason.RETRY.value
    assert rows[2].previous_execution_id == rows[1].id
    assert rows[2].attempt_reason == AIAttemptReason.PROVIDER_FALLBACK.value
    # the successful attempt carries OpenAI's own token counts and request id
    assert (rows[2].input_tokens, rows[2].output_tokens) == (7, 3)
    assert rows[2].provider_request_id == "req_oa"


def test_an_unconfigured_second_provider_is_skipped_without_an_execution(client, db_session, org, run):
    """A provider with no credential is not a failure: nothing was invoked, so nothing is recorded."""
    from app.integrations.llm.openai import OpenAIAdapter
    before = exec_count(db_session)
    first = Script(db_session, [(500, {"error": "upstream"}, None)])
    outcome = invoke_with_policy(
        db_session, ctx_for(run),
        [ModelTarget("anthropic", "claude-x"), ModelTarget("openai", "gpt-x")],
        req(), attempts_per_target=1,
        adapters={"anthropic": adapter_for(first), "openai": OpenAIAdapter(api_key=None)},
        pricing=ConfiguredPricing(),
    )
    assert not outcome.final.succeeded
    assert len(outcome.executions) == 1                       # only the Anthropic attempt exists
    assert exec_count(db_session) == before + 1
    assert db_session.get(AIExecution, outcome.executions[0].id).provider == "anthropic"


def test_a_non_retryable_failure_on_the_first_provider_still_tries_the_second(client, db_session, org, run):
    """A rejected credential on provider A must not strand the job: provider B is still tried."""
    first = Script(db_session, [(401, {"error": "bad key"}, None)])
    second = OpenAIScript(db_session, [OpenAIScript.ok("recovered")])
    outcome = invoke_with_policy(
        db_session, ctx_for(run),
        [ModelTarget("anthropic", "claude-x"), ModelTarget("openai", "gpt-x")],
        req(), attempts_per_target=2,
        adapters={"anthropic": adapter_for(first), "openai": openai_adapter(second)},
        pricing=ConfiguredPricing(),
    )
    assert len(first.calls) == 1                              # 401 is not retried against the same provider
    assert outcome.final.succeeded and outcome.final.result.text == "recovered"
    rows = [db_session.get(AIExecution, e.id) for e in outcome.executions]
    assert [r.provider for r in rows] == ["anthropic", "openai"]
    assert rows[0].error_code == "auth_failed"
    assert rows[1].attempt_reason == AIAttemptReason.PROVIDER_FALLBACK.value


def test_when_every_provider_fails_the_failure_is_reported_not_disguised(client, db_session, org, run):
    first = Script(db_session, [(500, {"error": "a"}, None)])
    second = OpenAIScript(db_session, [(503, {"error": "b"}, None)])
    outcome = invoke_with_policy(
        db_session, ctx_for(run),
        [ModelTarget("anthropic", "claude-x"), ModelTarget("openai", "gpt-x")],
        req(), attempts_per_target=1,
        adapters={"anthropic": adapter_for(first), "openai": openai_adapter(second)},
        pricing=ConfiguredPricing(),
    )
    assert not outcome.final.succeeded
    rows = [db_session.get(AIExecution, e.id) for e in outcome.executions]
    assert [r.provider for r in rows] == ["anthropic", "openai"]
    assert all(r.status == AIExecutionStatus.FAILED.value for r in rows)
    assert all(PROMPT not in (r.error_message or "") for r in rows)
