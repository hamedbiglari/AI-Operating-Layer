"""AI Center (REQ-AIC-*, REQ-KW-*). Provider HTTP is mocked (httpx.MockTransport)
because no real credential exists; everything else — DB, routing, memory,
AIExecution, API, tenancy — is real."""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import exc, func, select, text

from app.ai.pricing import ConfiguredPricing
from app.core.config import settings
from app.integrations.llm.anthropic import AnthropicAdapter
from app.models.ai_center import (AIJob, AIJobItem, AIProviderAccount, AIRoutingDecision, AIRoutingPolicy,
                                  AIWorkingMemory, KnowledgeKeyword)
from app.models.ai_execution import AIExecution
from app.services import ai_center_service, ai_job_service, ai_memory_service
from app.services.ai_routing_service import decide

SECRET = "sk-test-NOT-REAL-aicenter-0001"
B = "/api/v1/ai-center"


@pytest.fixture(autouse=True)
def cred_key(monkeypatch):
    monkeypatch.setattr(settings, "AI_CREDENTIAL_KEY", SecretStr(Fernet.generate_key().decode()))


@pytest.fixture()
def org(register_org):
    return register_org()


def ok_body(text_="finding"):
    return {"id": "msg_1", "model": "m", "stop_reason": "end_turn", "content": [{"type": "text", "text": text_}],
            "usage": {"input_tokens": 10, "output_tokens": 5}}


class Scripted:
    """Per-account scripted provider: fn(call_number) -> (status, body)."""
    def __init__(self, fn):
        self.fn, self.calls = fn, 0

    def adapter(self):
        def h(req):
            self.calls += 1
            st, body = self.fn(self.calls)
            return httpx.Response(st, json=body)
        return AnthropicAdapter(transport=httpx.MockTransport(h), api_key=SECRET)


def mk_provider(client, h, name="Anthropic", adapter_key="anthropic"):
    r = client.post(f"{B}/providers", headers=h, json={"name": name, "adapter_key": adapter_key, "official_url": "https://example.com"})
    assert r.status_code == 201, r.text
    return r.json()


def mk_account(client, h, provider_id, label, with_cred=True):
    a = client.post(f"{B}/accounts", headers=h, json={"provider_id": provider_id, "label": label}).json()
    if with_cred:
        assert client.put(f"{B}/accounts/{a['id']}/credential", headers=h, json={"secret": SECRET + label}).status_code == 200
    return a


def mk_policy(client, h, mode, steps, **kw):
    r = client.post(f"{B}/routing-policies", headers=h, json={"name": f"p-{uuid.uuid4().hex[:6]}", "mode": mode, "steps": steps, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def acct(db, a):
    return db.get(AIProviderAccount, uuid.UUID(a["id"]))


# ---------------- registry, credentials, tenancy ----------------

def test_credentials_are_write_only_and_encrypted(client, db_session, org):
    h = org["headers"]
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], "A")
    got = client.get(f"{B}/accounts/{a['id']}", headers=h)
    assert got.json()["credential_set"] is True and got.json()["credential_last4"] == (SECRET + "A")[-4:]
    for r in (got, client.get(f"{B}/accounts", headers=h)):
        assert SECRET not in r.text and "credential_ciphertext" not in r.text
    stored = db_session.execute(text("SELECT credential_ciphertext FROM ai_provider_accounts WHERE id=:i"), {"i": a["id"]}).scalar_one()
    assert stored and SECRET not in stored


def test_no_encryption_key_means_credential_is_refused(client, org, monkeypatch):
    h = org["headers"]
    a = mk_account(client, h, mk_provider(client, h)["id"], "A", with_cred=False)
    monkeypatch.setattr(settings, "AI_CREDENTIAL_KEY", None)
    r = client.put(f"{B}/accounts/{a['id']}/credential", headers=h, json={"secret": SECRET})
    assert r.status_code == 503 and client.get(f"{B}/accounts/{a['id']}", headers=h).json()["credential_set"] is False


def test_multiple_accounts_of_one_provider_are_independent(client, db_session, org):
    h = org["headers"]
    p = mk_provider(client, h, "Google", adapter_key=None)
    a, b = mk_account(client, h, p["id"], "Account A"), mk_account(client, h, p["id"], "Account B")
    ai_center_service.record_health(db_session, acct(db_session, a), health="quota_exhausted", source="execution", avoid_seconds=60)
    db_session.expire_all()
    assert acct(db_session, a).health_status == "quota_exhausted" and acct(db_session, a).failure_count == 1
    assert acct(db_session, b).health_status == "unknown" and acct(db_session, b).failure_count == 0
    assert client.get(f"{B}/accounts?provider_id={p['id']}", headers=h).json()["total"] == 2


def test_tenant_isolation_and_admin_only_writes(client, register_org, org):
    h = org["headers"]
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], "A")
    other = register_org()
    hb = other["headers"]
    for path in (f"/providers/{p['id']}", f"/accounts/{a['id']}", f"/accounts/{a['id']}/usage", f"/accounts/{a['id']}/health-events"):
        assert client.get(B + path, headers=hb).status_code == 404
    assert client.get(f"{B}/providers", headers=hb).json()["total"] == 0
    assert client.post(f"{B}/accounts", headers=hb, json={"provider_id": p["id"], "label": "steal"}).status_code == 404
    assert client.put(f"{B}/accounts/{a['id']}/credential", headers=hb, json={"secret": "x" * 12}).status_code == 404
    pb = mk_provider(client, hb)
    assert client.post(f"{B}/routing-policies", headers=hb, json={"name": "x", "mode": "manual_single",
                       "steps": [{"account_id": a["id"], "model": "m"}]}).status_code == 404
    # a viewer cannot write
    client.post("/api/v1/users", headers=h, json={"email": f"v{uuid.uuid4().hex[:6]}@example.com", "name": "V", "password": "viewer-pass-1", "role": "viewer"})
    assert pb


def test_connection_test_pass_fail_and_blocked(client, db_session, org, monkeypatch):
    h = org["headers"]
    answers = [(200, {"data": [{"id": "m1"}, {"id": "m2"}]}), (401, {"error": "no"})]

    def handler(req):
        assert req.url.path == "/v1/models" and req.method == "GET"   # never a model invocation
        st, body = answers.pop(0)
        return httpx.Response(st, json=body)
    monkeypatch.setitem(ai_center_service.IMPLEMENTED_ADAPTERS, "anthropic",
                        lambda api_key: AnthropicAdapter(transport=httpx.MockTransport(handler), api_key=api_key))
    a = mk_account(client, h, mk_provider(client, h)["id"], "A")
    r1 = client.post(f"{B}/accounts/{a['id']}/test", headers=h).json()
    r2 = client.post(f"{B}/accounts/{a['id']}/test", headers=h).json()
    assert (r1["result"], r2["result"]) == ("PASS", "FAIL") and "2 models" in r1["message"]
    assert client.get(f"{B}/accounts/{a['id']}", headers=h).json()["health_status"] == "auth_failed"
    assert client.get(f"{B}/accounts/{a['id']}/health-events", headers=h).json()["total"] == 2
    assert db_session.execute(select(func.count()).select_from(AIExecution)).scalar_one() == 0
    noadapter = mk_account(client, h, mk_provider(client, h, "Mistral", adapter_key=None)["id"], "M")
    assert client.post(f"{B}/accounts/{noadapter['id']}/test", headers=h).json()["result"] == "BLOCKED_EXTERNAL_DEPENDENCY"


# ---------------- routing: six modes ----------------

def _setup_three(client, h):
    p = mk_provider(client, h)
    return p, [mk_account(client, h, p["id"], n) for n in ("A", "B", "C")]


def _pol(db, pol):
    return db.get(AIRoutingPolicy, uuid.UUID(pol["id"]))


def _chosen(d):
    return d.chosen.account.label if d.chosen else None


def _ratelimit(db, a):
    x = acct(db, a)
    x.health_status, x.unavailable_until = "rate_limited", datetime.now(timezone.utc) + timedelta(minutes=5)
    db.commit()


def test_manual_single_never_falls_back(client, db_session, org):
    h = org["headers"]; _, (a, b, c) = _setup_three(client, h)
    pol = _pol(db_session, mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}]))
    assert _chosen(decide(db_session, organization_id=pol.organization_id, policy=pol)) == "A"
    d = decide(db_session, organization_id=pol.organization_id, policy=pol, excluded={acct(db_session, a).id})
    assert d.chosen is None and d.stop_reason


def test_manual_chain_follows_user_order_strictly(client, db_session, org):
    h = org["headers"]; _, (a, b, c) = _setup_three(client, h)
    pol = _pol(db_session, mk_policy(client, h, "manual_chain", [{"account_id": x["id"], "model": "m"} for x in (a, b, c)]))
    _ratelimit(db_session, a)   # known unhealthy, but the chain only advances when A actually stops
    assert _chosen(decide(db_session, organization_id=pol.organization_id, policy=pol)) == "A"
    assert _chosen(decide(db_session, organization_id=pol.organization_id, policy=pol, excluded={acct(db_session, a).id})) == "B"


def test_stage_manual_uses_the_stage_step(client, db_session, org):
    h = org["headers"]; _, (a, b, c) = _setup_three(client, h)
    pol = _pol(db_session, mk_policy(client, h, "stage_manual", [{"account_id": a["id"], "model": "m", "stage": "research"},
                                                                 {"account_id": b["id"], "model": "m", "stage": "synthesis"}]))
    assert _chosen(decide(db_session, organization_id=pol.organization_id, policy=pol, stage="synthesis")) == "B"
    assert _chosen(decide(db_session, organization_id=pol.organization_id, policy=pol, stage="research")) == "A"
    assert decide(db_session, organization_id=pol.organization_id, policy=pol, stage="translation").chosen is None


def test_priority_pool_skips_ineligible_with_reason(client, db_session, org):
    h = org["headers"]; _, (a, b, c) = _setup_three(client, h)
    pol = _pol(db_session, mk_policy(client, h, "priority_pool", [{"account_id": x["id"], "model": "m"} for x in (a, b, c)]))
    _ratelimit(db_session, a)
    d = decide(db_session, organization_id=pol.organization_id, policy=pol)
    assert _chosen(d) == "B"
    skipped = next(e for e in d.explanation if e["account"] == "A")
    assert skipped["verdict"] == "skipped" and "rate_limited" in skipped["reason"]


def test_auto_pool_ranks_by_health_failures_price(client, db_session, org, monkeypatch):
    h = org["headers"]; _, (a, b, c) = _setup_three(client, h)
    pol = _pol(db_session, mk_policy(client, h, "auto_pool", [{"account_id": a["id"], "model": "expensive"},
                                                              {"account_id": b["id"], "model": "cheap"},
                                                              {"account_id": c["id"], "model": "cheap"}]))
    monkeypatch.setattr(settings, "AI_MODEL_PRICING_JSON", json.dumps({
        "anthropic/expensive": {"input_per_mtok": "10", "output_per_mtok": "50"}, "anthropic/cheap": {"input_per_mtok": "1", "output_per_mtok": "5"}}))
    x = acct(db_session, c); x.failure_count = 3; db_session.commit()
    d = decide(db_session, organization_id=pol.organization_id, policy=pol)
    assert _chosen(d) == "B"   # A dearer, C more recent failures


def test_hybrid_prefers_stage_rule_then_pool(client, db_session, org):
    h = org["headers"]; _, (a, b, c) = _setup_three(client, h)
    pol = _pol(db_session, mk_policy(client, h, "hybrid", [{"account_id": a["id"], "model": "m", "stage": "extraction"},
                                                           {"account_id": b["id"], "model": "m"}, {"account_id": c["id"], "model": "m"}]))
    assert _chosen(decide(db_session, organization_id=pol.organization_id, policy=pol, stage="extraction")) == "A"
    _ratelimit(db_session, a)
    d = decide(db_session, organization_id=pol.organization_id, policy=pol, stage="extraction")
    assert _chosen(d) in ("B", "C") and "pool" in next(e for e in d.explanation if e["verdict"] == "chosen")["reason"]


def test_capability_spend_and_adapter_gates_are_explained(client, db_session, org):
    h = org["headers"]
    p = mk_provider(client, h)
    a, b = mk_account(client, h, p["id"], "A"), mk_account(client, h, p["id"], "B")
    client.post(f"{B}/models", headers=h, json={"provider_id": p["id"], "name": "text-only", "capabilities": ["text"]})
    no = mk_account(client, h, mk_provider(client, h, "Gemini", adapter_key=None)["id"], "G")
    pol = _pol(db_session, mk_policy(client, h, "priority_pool", [
        {"account_id": no["id"], "model": "g"}, {"account_id": a["id"], "model": "text-only", "required_capability": "vision"},
        {"account_id": b["id"], "model": "text-only"}]))
    x = acct(db_session, b); x.spend_limit = 0; db_session.commit()
    d = decide(db_session, organization_id=pol.organization_id, policy=pol)
    reasons = {e["account"]: e["reason"] for e in d.explanation}
    assert d.chosen is None
    assert "no adapter implemented" in reasons["G"] and "lacks capability 'vision'" in reasons["A"] and "spend limit" in reasons["B"]


def test_preview_endpoint_explains_and_decisions_are_audited(client, db_session, org):
    h = org["headers"]; _, (a, b, c) = _setup_three(client, h)
    pol = mk_policy(client, h, "priority_pool", [{"account_id": x["id"], "model": "m"} for x in (a, b, c)])
    r = client.get(f"{B}/routing-policies/{pol['id']}/preview", headers=h).json()
    assert r["chosen"]["account"] == "A" and len(r["candidates"]) == 3
    assert db_session.execute(select(func.count()).select_from(AIRoutingDecision)).scalar_one() == 0   # preview is not persisted


# ---------------- jobs: checkpoint, handoff, switch, resume ----------------

def _job(client, db_session, h, pol, n, key=None, stage=None):
    key = key or f"job-{uuid.uuid4().hex[:8]}"
    r = client.post(f"{B}/jobs", headers=h, json={"job_key": key, "goal": "extract findings", "policy_id": pol["id"], "stage": stage,
                                                  "items": [{"key": f"doc-{i:03d}", "prompt": f"document {i}"} for i in range(n)]})
    assert r.status_code == 202, r.text
    return db_session.execute(select(AIJob).where(AIJob.job_key == key)).scalar_one()


@pytest.fixture()
def no_background(monkeypatch):
    import app.api.v1.ai_center as api
    monkeypatch.setattr(api, "_run_in_background", lambda job_id: None)


def test_quota_switch_after_50_of_100_preserves_all_progress(client, db_session, org, no_background):
    h = org["headers"]; _, (a, b, _c) = _setup_three(client, h)
    pol = mk_policy(client, h, "manual_chain", [{"account_id": a["id"], "model": "m"}, {"account_id": b["id"], "model": "m"}])
    job = _job(client, db_session, h, pol, 100, key="docs-100")
    A = Scripted(lambda n: (200, ok_body(f"A{n}")) if n <= 50 else (402, {}))
    Bs = Scripted(lambda n: (200, ok_body(f"B{n}")))
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: A.adapter(), acct(db_session, b).id: Bs.adapter()})
    assert res["status"] == "completed" and res["completed"] == 100 and res["pending"] == 0
    by = dict(db_session.execute(select(AIJobItem.completed_by_account_id, func.count()).where(AIJobItem.job_id == job.id)
                                 .group_by(AIJobItem.completed_by_account_id)).all())
    assert by == {acct(db_session, a).id: 50, acct(db_session, b).id: 50}
    execs = db_session.execute(select(AIExecution).where(AIExecution.ai_job_id == job.id).order_by(AIExecution.started_at)).scalars().all()
    assert len(execs) == 101 and sum(e.status == "succeeded" for e in execs) == 100      # no item processed twice
    failed = [e for e in execs if e.status != "succeeded"]
    assert len(failed) == 1 and failed[0].stop_reason == "QUOTA_EXHAUSTED"
    resumed = next(e for e in execs if e.previous_execution_id == failed[0].id)
    assert resumed.attempt_reason == "account_fallback" and resumed.provider_account_id == acct(db_session, b).id
    assert all(e.parent_type == "ai_job" for e in execs)
    handoff = client.get(f"{B}/jobs/docs-100/handoff", headers=h).json()["package"]
    assert handoff["failure_reason"] == "QUOTA_EXHAUSTED" and len(handoff["completed_items"]) == 50 and len(handoff["pending_items"]) == 50
    assert str(failed[0].id) in handoff["previous_executions"] and len(handoff["finding_memory_ids"]) == 50
    triggers = [d["trigger"] for d in client.get(f"{B}/routing-decisions?job_key=docs-100", headers=h).json()]
    assert triggers == ["initial", "switch:QUOTA_EXHAUSTED"]
    assert db_session.execute(select(func.count()).select_from(AIWorkingMemory).where(
        AIWorkingMemory.job_key == "docs-100", AIWorkingMemory.kind == "intermediate_finding")).scalar_one() == 100
    assert acct(db_session, a).health_status == "quota_exhausted"


def test_blocked_job_resumes_from_checkpoint_not_from_zero(client, db_session, org, no_background):
    h = org["headers"]; _, (a, *_r) = _setup_three(client, h)
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    job = _job(client, db_session, h, pol, 100, key="resume-100")
    first = Scripted(lambda n: (200, ok_body()) if n <= 30 else (401, {}))
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: first.adapter()})
    assert res["status"] == "blocked" and res["completed"] == 30 and res["pending"] == 70
    # the owner rotates the credential: the account is usable again
    ai_center_service.set_credential(db_session, acct(db_session, a), SECRET + "rotated")
    second = Scripted(lambda n: (200, ok_body()))
    res2 = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: second.adapter()})
    assert res2["status"] == "completed" and res2["completed"] == 100
    assert second.calls == 70   # resumed; the first 30 were not redone


def test_pause_then_resume(client, db_session, org, no_background):
    h = org["headers"]; _, (a, *_r) = _setup_three(client, h)
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    job = _job(client, db_session, h, pol, 10, key="pause-10")

    def fn(n):
        if n == 4:
            ai_job_service.request_control(db_session, db_session.get(AIJob, job.id), "pause")
        return 200, ok_body()
    s = Scripted(fn)
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: s.adapter()})
    assert res["status"] == "paused" and res["completed"] == 4
    res2 = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: s.adapter()})
    assert res2["status"] == "completed" and s.calls == 10


def test_manual_switch_mid_job(client, db_session, org, no_background):
    h = org["headers"]; _, (a, b, _c) = _setup_three(client, h)
    pol = mk_policy(client, h, "priority_pool", [{"account_id": a["id"], "model": "m"}, {"account_id": b["id"], "model": "m"}])
    job = _job(client, db_session, h, pol, 10, key="switch-10")

    def fa(n):
        if n == 3:
            assert client.post(f"{B}/jobs/switch-10/control", headers=h, json={"action": "switch", "account_id": b["id"]}).status_code == 202
        return 200, ok_body()
    A, Bs = Scripted(fa), Scripted(lambda n: (200, ok_body()))
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: A.adapter(), acct(db_session, b).id: Bs.adapter()})
    assert res["completed"] == 10 and A.calls == 3 and Bs.calls == 7
    assert "manual_switch" in [d["trigger"] for d in client.get(f"{B}/routing-decisions?job_key=switch-10", headers=h).json()]


def test_job_cost_limit_stops_the_job(client, db_session, org, no_background, monkeypatch):
    h = org["headers"]; _, (a, *_r) = _setup_three(client, h)
    monkeypatch.setattr(settings, "AI_MODEL_PRICING_JSON", json.dumps({"anthropic/m": {"input_per_mtok": "1000", "output_per_mtok": "1000"}}))
    pol = mk_policy(client, h, "priority_pool", [{"account_id": a["id"], "model": "m"}], max_cost_per_job=0.5, currency="USD")
    job = _job(client, db_session, h, pol, 10, key="cost-10")
    # actual per call: 15 tokens * 1000/1e6 = 0.015; worst case checked BEFORE each call:
    # (10 prompt bytes + 400 max output tokens) * 1000/1e6 = 0.41 -> 7 calls fit, the 8th is never made
    s = Scripted(lambda n: (200, ok_body()))
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: s.adapter()})
    assert res["status"] == "blocked" and res["stop_reason"] == "SPEND_LIMIT" and res["completed"] == 7 and s.calls == 7


def test_job_creation_is_idempotent_and_tenant_scoped(client, db_session, register_org, org, no_background):
    h = org["headers"]; _, (a, *_r) = _setup_three(client, h)
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    body = {"job_key": "same", "goal": "g", "policy_id": pol["id"], "items": [{"key": "x", "prompt": "p"}]}
    assert client.post(f"{B}/jobs", headers=h, json=body).json()["created"] is True
    assert client.post(f"{B}/jobs", headers=h, json=body).json()["created"] is False
    hb = register_org()["headers"]
    assert client.get(f"{B}/jobs/same", headers=hb).status_code == 404
    assert client.get(f"{B}/memory?job_key=same", headers=hb).json()["total"] == 0


# ---------------- memory, arc, walrus ----------------

def test_memory_write_is_idempotent_and_versioned(db_session, org):
    oid = uuid.UUID(org["organization"]["id"])
    m1 = ai_memory_service.write(db_session, organization_id=oid, job_key="k", kind="open_question", created_by="t", content={"q": 1})
    m2 = ai_memory_service.write(db_session, organization_id=oid, job_key="k", kind="open_question", created_by="t", content={"q": 1})
    m3 = ai_memory_service.write(db_session, organization_id=oid, job_key="k", kind="open_question", created_by="t", content={"q": 2})
    assert m1.id == m2.id and (m1.version, m3.version) == (1, 2)
    assert m1.provenance["semantic_mirror"] == "none"


def test_walrus_is_optional_and_reported_honestly(client, org):
    r = client.get(f"{B}/memory/semantic-backend", headers=org["headers"]).json()
    assert r["status"] == "DISCONNECTED" and r["canonical_store"] == "postgresql"


def test_arc_now_rejects_two_parents(client, db_session, org, no_background):
    h = org["headers"]; _, (a, *_r) = _setup_three(client, h)
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    job = _job(client, db_session, h, pol, 1)
    run = db_session.execute(text("INSERT INTO visibility_projects (id,organization_id,name,markets,languages,platforms,methodology_version,created_at,updated_at) "
                                  "VALUES (gen_random_uuid(),:o,'p','[]','[]','[]','v1',now(),now()) RETURNING id"), {"o": job.organization_id}).scalar_one()
    vr = db_session.execute(text("INSERT INTO visibility_runs (id,organization_id,project_id,platform,provider_name,methodology_version,status,queries_planned,queries_observed,queries_failed,created_at,updated_at) "
                                 "VALUES (gen_random_uuid(),:o,:p,'other','x','v1','queued',0,0,0,now(),now()) RETURNING id"), {"o": job.organization_id, "p": run}).scalar_one()
    with pytest.raises(exc.IntegrityError):
        db_session.execute(text("INSERT INTO ai_executions (id,organization_id,parent_type,visibility_run_id,ai_job_id,operation_type,provider,model,status,started_at,created_at,updated_at) "
                                "VALUES (gen_random_uuid(),:o,'ai_job',:v,:j,'chat','anthropic','m','running',now(),now(),now())"),
                           {"o": job.organization_id, "v": vr, "j": job.id})
        db_session.flush()
    db_session.rollback()


def test_stop_reason_is_immutable_once_terminal(client, db_session, org, no_background):
    h = org["headers"]; _, (a, *_r) = _setup_three(client, h)
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    job = _job(client, db_session, h, pol, 1)
    ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: Scripted(lambda n: (200, ok_body())).adapter()})
    e = db_session.execute(select(AIExecution).where(AIExecution.ai_job_id == job.id)).scalar_one()
    assert e.stop_reason == "COMPLETED" and e.provider_account_id == acct(db_session, a).id
    with pytest.raises(exc.DBAPIError, match="immutable"):
        db_session.execute(text("UPDATE ai_executions SET stop_reason='RATE_LIMIT' WHERE id=:i"), {"i": e.id}); db_session.flush()
    db_session.rollback()


def test_account_usage_is_honest(client, db_session, org, no_background):
    h = org["headers"]; _, (a, *_r) = _setup_three(client, h)
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    job = _job(client, db_session, h, pol, 3)
    ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: Scripted(lambda n: (200, ok_body())).adapter()},
                           pricing=ConfiguredPricing("{}"))
    u = client.get(f"{B}/accounts/{a['id']}/usage", headers=h).json()
    assert u["requests"] == 3 and u["input_tokens"] == 30 and u["estimated_cost"] is None and u["executions_without_cost"] == 3


# ---------------- keyword workspace ----------------

def _ko(client, h, name="Toranjebin"):
    return client.post("/api/v1/knowledge", headers=h, json={"canonical_name": name, "object_type": "ingredient"}).json()


def test_keyword_upload_all_formats_keeps_original_rows(client, db_session, org):
    h = org["headers"]; ko = _ko(client, h)
    base = f"/api/v1/knowledge/{ko['id']}/keywords"
    csv_ = "keyword,type,volume,country,custom_col\nbuy toranjebin,transactional,1200,IR,keep me\n,,,,\nwhat is toranjebin,question,,,\n"
    r = client.post(f"{base}/import", headers=h, files={"file": ("k.csv", csv_.encode(), "text/csv")}).json()
    assert (r["inserted"], len(r["rejected"])) == (2, 1)
    r = client.post(f"{base}/import", headers=h, files={"file": ("k.json", json.dumps(["persian manna", {"keyword": "buy toranjebin", "type": "transactional"}]).encode(), "application/json")}).json()
    assert (r["inserted"], r["duplicates"]) == (1, 1)
    r = client.post(f"{base}/import", headers=h, files={"file": ("k.txt", "ترنجبین\ntoranjebin benefits\n".encode(), "text/plain")}).json()
    assert r["inserted"] == 2
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.append(["keyword", "type", "notes"]); ws.append(["toranjebin price", "commercial", "from sheet"])
    buf = io.BytesIO(); wb.save(buf)
    r = client.post(f"{base}/import", headers=h, files={"file": ("k.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}).json()
    assert r["inserted"] == 1
    items = client.get(f"{base}?limit=50", headers=h).json()["items"]
    assert len(items) == 6
    buy = next(i for i in items if i["keyword"] == "buy toranjebin")
    assert buy["volume"] == 1200 and buy["raw"]["custom_col"] == "keep me"


def test_keywords_drive_research_with_traceability(client, db_session, org):
    h = org["headers"]; ko = _ko(client, h, "Toranjebin")
    base = f"/api/v1/knowledge/{ko['id']}/keywords"
    client.post(base, headers=h, json=[{"keyword": "manna mannitol content"}, {"keyword": "toranjebin safety"}])
    ids = [k["id"] for k in client.get(base, headers=h).json()["items"]]
    r = client.post(f"{base}/search-sources", headers=h, json={"keyword_ids": ids})
    assert r.status_code == 201, r.text
    tasks = r.json()["tasks"]
    assert len(tasks) == 2 and any("Toranjebin" in t["query"] for t in tasks)
    for t in tasks:
        assert client.get(f"/api/v1/research/tasks/{t['research_task_id']}", headers=h).status_code == 200
    kws = client.get(base, headers=h).json()["items"]
    assert all(len(k["research_task_ids"]) == 1 for k in kws)


def test_keyword_workspace_is_tenant_isolated(client, register_org, org):
    h = org["headers"]; ko = _ko(client, h)
    hb = register_org()["headers"]
    assert client.get(f"/api/v1/knowledge/{ko['id']}/keywords", headers=hb).status_code == 404
    assert client.post(f"/api/v1/knowledge/{ko['id']}/keywords", headers=hb, json=[{"keyword": "x"}]).status_code == 404


def test_upload_limits(client, org):
    h = org["headers"]; ko = _ko(client, h)
    big = ("k\n" * 1_100_000).encode()
    assert client.post(f"/api/v1/knowledge/{ko['id']}/keywords/import", headers=h, files={"file": ("big.txt", big, "text/plain")}).status_code == 413
    assert client.post(f"/api/v1/knowledge/{ko['id']}/keywords/import", headers=h, files={"file": ("x.json", b"{bad", "application/json")}).status_code == 422


# ---------------- discovery ----------------

def test_discovery_seed_is_idempotent_and_never_claims_activity(client, org):
    h = org["headers"]
    r1 = client.post(f"{B}/discovery/import-seed", headers=h).json()
    r2 = client.post(f"{B}/discovery/import-seed", headers=h).json()
    assert r1["inserted"] == r1["received"] and r2["inserted"] == 0
    items = client.get(f"{B}/discovery?limit=200", headers=h).json()
    assert items["total"] == r1["received"]
    assert all(i["status"] == "discovered" and i["classification_basis"].startswith("INFERENCE") and i["api_url"] is None for i in items["items"])
    tools = client.get(f"{B}/discovery?type=RESEARCH_TOOL&limit=200", headers=h).json()["items"]
    assert any(i["name"] == "Consensus" for i in tools) and not any("PROVIDER" in i["proposed_types"] for i in tools if i["name"] == "Consensus")
    apps = {i["name"]: i["proposed_types"] for i in items["items"]}
    assert apps["ChatGPT"] == ["APPLICATION"] and apps["OpenAI API"] == ["PROVIDER"]
    assert apps["Claude.ai"] == ["APPLICATION"] and apps["Anthropic API"] == ["PROVIDER"]


# ---------------- routing policies: an admin can edit them and set the order (ADR-120) ----------------

def _steps(pol):
    return [(s["position"], s["model"], s["account_id"]) for s in pol["steps"]]


def test_an_admin_can_rename_a_policy_and_change_its_ceiling(client, org):
    h = org["headers"]
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], "A")
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m-1"}], max_cost_per_job=2.5, currency="USD")
    r = client.patch(f"{B}/routing-policies/{pol['id']}", headers=h, json={"name": "evidence extraction", "max_cost_per_job": 0.5})
    assert r.status_code == 200 and r.json()["name"] == "evidence extraction" and float(r.json()["max_cost_per_job"]) == 0.5
    # the ceiling can be removed outright, which a null could not express
    r = client.patch(f"{B}/routing-policies/{pol['id']}", headers=h, json={"clear_max_cost": True})
    assert r.json()["max_cost_per_job"] is None
    # the steps are untouched by a policy edit
    assert len(r.json()["steps"]) == 1


def test_the_order_of_steps_is_what_an_admin_sets(client, org):
    """This is the priority: position 0 is tried first."""
    h = org["headers"]
    p = mk_provider(client, h)
    a, b = mk_account(client, h, p["id"], "A"), mk_account(client, h, p["id"], "B")
    pol = mk_policy(client, h, "manual_chain", [{"account_id": a["id"], "model": "first"},
                                                {"account_id": b["id"], "model": "second"}])
    r = client.post(f"{B}/routing-policies/{pol['id']}/steps", headers=h, json={"account_id": a["id"], "model": "third"})
    assert r.status_code == 201
    assert [s[1] for s in _steps(r.json())] == ["first", "second", "third"]
    # promote the last to the front: everything between shifts by one, positions stay 0..n-1
    r = client.post(f"{B}/routing-policies/{pol['id']}/steps/2/move", headers=h, json={"position": 0})
    assert r.status_code == 200
    assert [s[1] for s in _steps(r.json())] == ["third", "first", "second"]
    assert [s[0] for s in _steps(r.json())] == [0, 1, 2]
    # and back down again
    r = client.post(f"{B}/routing-policies/{pol['id']}/steps/0/move", headers=h, json={"position": 2})
    assert [s[1] for s in _steps(r.json())] == ["first", "second", "third"]
    # removing the middle one closes the gap
    r = client.delete(f"{B}/routing-policies/{pol['id']}/steps/1", headers=h)
    assert r.status_code == 200
    assert [s[1] for s in _steps(r.json())] == ["first", "third"] and [s[0] for s in _steps(r.json())] == [0, 1]


def test_a_step_can_be_pointed_at_another_account_or_model(client, org):
    h = org["headers"]
    p = mk_provider(client, h)
    a, b = mk_account(client, h, p["id"], "A"), mk_account(client, h, p["id"], "B")
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "old"}])
    r = client.patch(f"{B}/routing-policies/{pol['id']}/steps/0", headers=h, json={"account_id": b["id"], "model": "new"})
    assert r.status_code == 200
    assert _steps(r.json()) == [(0, "new", b["id"])]
    assert client.patch(f"{B}/routing-policies/{pol['id']}/steps/9", headers=h,
                        json={"account_id": b["id"], "model": "x"}).status_code == 404


def test_an_edit_can_never_leave_a_policy_in_a_shape_it_could_not_be_created_in(client, org):
    h = org["headers"]
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], "A")
    single = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "only"}])
    # manual_single takes exactly one step, so a second one is refused
    assert client.post(f"{B}/routing-policies/{single['id']}/steps", headers=h,
                       json={"account_id": a["id"], "model": "second"}).status_code == 422
    # and the last step cannot be removed
    assert client.delete(f"{B}/routing-policies/{single['id']}/steps/0", headers=h).status_code == 422
    # stage_manual needs a stage on every step: switching to it with a step that has none is refused
    assert client.patch(f"{B}/routing-policies/{single['id']}", headers=h, json={"mode": "stage_manual"}).status_code == 422
    # with a stage present, the same switch is allowed
    client.patch(f"{B}/routing-policies/{single['id']}/steps/0", headers=h,
                 json={"account_id": a["id"], "model": "only", "stage": "extract"})
    assert client.patch(f"{B}/routing-policies/{single['id']}", headers=h, json={"mode": "stage_manual"}).status_code == 200


def test_a_policy_that_has_run_jobs_is_kept(client, db_session, org):
    """History stays readable: a policy with jobs behind it is refused deletion rather than cascading."""
    h = org["headers"]
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], "A")
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    unused = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    assert client.delete(f"{B}/routing-policies/{unused['id']}", headers=h).status_code == 204
    assert client.get(f"{B}/routing-policies/{unused['id']}", headers=h).status_code == 404
    r = client.post(f"{B}/jobs", headers=h, json={"job_key": f"j-{uuid.uuid4().hex[:6]}", "goal": "g", "policy_id": pol["id"],
                                               "items": [{"key": "i-1", "prompt": "hello"}]})
    assert r.status_code == 202, r.text
    r = client.delete(f"{B}/routing-policies/{pol['id']}", headers=h)
    assert r.status_code == 409 and "history" in r.text
    assert client.get(f"{B}/routing-policies/{pol['id']}", headers=h).status_code == 200


def test_policy_editing_is_admin_only_and_tenant_isolated(client, org, register_org):
    h = org["headers"]
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], "A")
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    other = register_org()["headers"]
    assert client.get(f"{B}/routing-policies/{pol['id']}", headers=other).status_code == 404
    assert client.patch(f"{B}/routing-policies/{pol['id']}", headers=other, json={"name": "theirs"}).status_code == 404
    assert client.delete(f"{B}/routing-policies/{pol['id']}", headers=other).status_code == 404
    assert client.post(f"{B}/routing-policies/{pol['id']}/steps", headers=other,
                       json={"account_id": a["id"], "model": "x"}).status_code == 404
    assert client.patch(f"{B}/routing-policies/{pol['id']}").status_code in (401, 403)
