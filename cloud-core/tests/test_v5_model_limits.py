"""Prompt v5 §7, §16, Workflow C (ADR-136): provider limits are tenant data, and a request that cannot fit them is
refused before any call instead of being truncated.

* A model is registered with max input/output, RPM/TPM, structured-output/tool flags and a capability source;
  an admin can correct them later (audit-logged). NULL means unknown.
* An item larger than the model's input room, or a job reserving more output than the model allows, fails
  with CONTEXT_OVERFLOW / OUTPUT_EXCEEDS_MODEL_LIMIT and no provider call. Other items still run.
* Without `max_input_tokens`, the room is context_window minus the output reserve, never the whole window.
* An unregistered model or unknown limits block nothing.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.integrations.llm.anthropic import AnthropicAdapter
from app.models.ai_center import AIJob, AIJobItem
from app.models.audit_log import AuditLog
from app.services import ai_job_service
from tests.test_ai_center import B, SECRET, acct, cred_key, mk_account, mk_policy, mk_provider, ok_body  # noqa: F401


@pytest.fixture()
def org(register_org):
    return register_org()


@pytest.fixture(autouse=True)
def no_background(monkeypatch):
    import app.api.v1.ai_center as api
    monkeypatch.setattr(api, "_run_in_background", lambda job_id: None)


class Counting:
    def __init__(self):
        self.calls = 0

    def adapter(self):
        def h(req):
            self.calls += 1
            return httpx.Response(200, json=ok_body())
        return AnthropicAdapter(transport=httpx.MockTransport(h), api_key=SECRET)


def _setup(client, h, model_name="m", **limits):
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], "A")
    r = client.post(f"{B}/models", headers=h, json={"provider_id": p["id"], "name": model_name, **limits})
    assert r.status_code == 201, r.text
    return a, mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": model_name}]), r.json()


def _run(client, db, h, a, pol, prompts, max_output_tokens=None):
    key = f"fit-{uuid.uuid4().hex[:8]}"
    r = client.post(f"{B}/jobs", headers=h, json={"job_key": key, "goal": "fit", "policy_id": pol["id"],
                                                  "items": [{"key": k, "prompt": v} for k, v in prompts.items()]})
    assert r.status_code == 202, r.text
    job = db.execute(select(AIJob).where(AIJob.job_key == key)).scalar_one()
    if max_output_tokens is not None:
        job.max_output_tokens = max_output_tokens
        db.commit()
    counter = Counting()
    res = ai_job_service.run_job(db, job, adapters={acct(db, a).id: counter.adapter()})
    items = {i.item_key: i for i in db.execute(select(AIJobItem).where(AIJobItem.job_id == job.id)).scalars()}
    return res, items, counter


def test_limits_are_registered_and_correctable(client, db_session, org):
    h = org["headers"]
    _, _, m = _setup(client, h, max_input_tokens=1000, max_output_tokens=500, rpm_limit=50, tpm_limit=40000,
                     supports_structured_output=True, supports_tools=False, capability_source="official_docs")
    assert (m["max_input_tokens"], m["max_output_tokens"], m["rpm_limit"], m["tpm_limit"]) == (1000, 500, 50, 40000)
    assert m["supports_structured_output"] is True and m["capability_source"] == "official_docs"
    r = client.patch(f"{B}/models/{m['id']}", headers=h, json={"max_output_tokens": 800, "rpm_limit": None})
    assert r.status_code == 200, r.text
    assert r.json()["max_output_tokens"] == 800 and r.json()["rpm_limit"] is None
    assert r.json()["max_input_tokens"] == 1000                      # untouched field kept
    log = db_session.execute(select(AuditLog).where(AuditLog.action == "ai_model.limits_updated",
                                                    AuditLog.resource_id == uuid.UUID(m["id"]))).scalar_one()
    assert log.old_value == {"max_output_tokens": 500, "rpm_limit": 50}


@pytest.mark.parametrize("body", [{"max_input_tokens": 0}, {"capability_source": "a blog post"}])
def test_invalid_limits_are_refused(client, org, body):
    h = org["headers"]
    _, _, m = _setup(client, h)
    assert client.patch(f"{B}/models/{m['id']}", headers=h, json=body).status_code == 422


def test_limits_cannot_be_changed_in_another_tenant(client, register_org, org):
    _, _, m = _setup(client, org["headers"])
    other = register_org()
    r = client.patch(f"{B}/models/{m['id']}", headers=other["headers"], json={"max_input_tokens": 5})
    assert r.status_code == 404


def test_an_item_too_large_for_the_model_fails_without_a_call(client, db_session, org):
    h = org["headers"]
    a, pol, _ = _setup(client, h, max_input_tokens=2000)
    res, items, counter = _run(client, db_session, h, a, pol, {"small": "short document", "huge": "x " * 20000})
    assert res["status"] == "completed_with_failures"
    assert items["small"].status == "completed"
    assert items["huge"].status == "failed" and items["huge"].failure_reason.startswith("CONTEXT_OVERFLOW")
    assert counter.calls == 1                                       # the oversized item was never sent


def test_without_max_input_the_output_reserve_comes_off_the_window(client, db_session, org):
    """context window != available input (§16): 1500-token window, 400 reserved for output."""
    h = org["headers"]
    a, pol, _ = _setup(client, h, context_window=1500)
    # ~1250 tokens of input: fits a 1500 window on its own, but not once 400 are reserved for output
    res, items, counter = _run(client, db_session, h, a, pol, {"doc": "word " * 1000}, max_output_tokens=400)
    assert items["doc"].status == "failed" and "CONTEXT_OVERFLOW" in items["doc"].failure_reason
    assert counter.calls == 0


def test_an_output_reserve_above_the_model_maximum_is_refused(client, db_session, org):
    h = org["headers"]
    a, pol, _ = _setup(client, h, max_output_tokens=256)
    res, items, counter = _run(client, db_session, h, a, pol, {"doc": "short"}, max_output_tokens=400)
    assert items["doc"].failure_reason.startswith("OUTPUT_EXCEEDS_MODEL_LIMIT") and counter.calls == 0


def test_unknown_limits_block_nothing(client, db_session, org):
    h = org["headers"]
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], "A")
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "unregistered"}])
    res, items, counter = _run(client, db_session, h, a, pol, {"doc": "x " * 20000})
    assert res["status"] == "completed" and counter.calls == 1
