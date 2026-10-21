"""Prompt v5 §10/§50 (ADR-135): AI-job items form a task DAG.

* An item runs only after every item it depends on has completed; otherwise position order is kept.
* A failed dependency fails its dependents, transitively, with DEPENDENCY_FAILED; independent items still run,
  and the job ends `completed_with_failures` instead of waiting for ever.
* A graph that is cyclic, self-referencing or names an unknown item is refused at creation.
* The handoff says which pending item waits for what.
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.integrations.llm.anthropic import AnthropicAdapter
from app.models.ai_center import AIJob, AIJobItem
from app.services import ai_job_service
from tests.test_ai_center import B, SECRET, acct, cred_key, mk_account, mk_policy, mk_provider, ok_body  # noqa: F401


@pytest.fixture()
def org(register_org):
    return register_org()


@pytest.fixture(autouse=True)
def no_background(monkeypatch):
    import app.api.v1.ai_center as api
    monkeypatch.setattr(api, "_run_in_background", lambda job_id: None)


class Recording:
    """Answers every call; records the prompt it was given. `fail` = prompts that get a non-retryable 400."""
    def __init__(self, fail=()):
        self.prompts, self.fail = [], set(fail)

    def adapter(self):
        def h(req):
            prompt = json.loads(req.content)["messages"][-1]["content"]
            prompt = prompt if isinstance(prompt, str) else " ".join(p.get("text", "") for p in prompt)
            self.prompts.append(prompt)
            if any(f in prompt for f in self.fail):
                return httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
            return httpx.Response(200, json=ok_body())
        return AnthropicAdapter(transport=httpx.MockTransport(h), api_key=SECRET)


def _setup(client, h):
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], "A")
    return a, mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])


def _post_job(client, h, pol, items):
    key = f"dag-{uuid.uuid4().hex[:8]}"
    r = client.post(f"{B}/jobs", headers=h, json={"job_key": key, "goal": "dag", "policy_id": pol["id"],
                                                  "items": items})
    return key, r


def _item(key, *deps):
    return {"key": key, "prompt": f"PROMPT<{key}>", "depends_on": list(deps)}


def _order(rec):
    return [p.split("PROMPT<", 1)[1].split(">", 1)[0] for p in rec.prompts]


def _items(db, key):
    job = db.execute(select(AIJob).where(AIJob.job_key == key)).scalar_one()
    return job, {i.item_key: i for i in db.execute(select(AIJobItem).where(AIJobItem.job_id == job.id)).scalars()}


def test_items_run_only_after_their_dependencies(client, db_session, org):
    h = org["headers"]
    a, pol = _setup(client, h)
    # position order is plan, merge, a, b; merge needs a and b, plan needs nothing
    key, r = _post_job(client, h, pol, [_item("plan"), _item("merge", "a", "b"), _item("a", "plan"), _item("b")])
    assert r.status_code == 202, r.text
    job, _ = _items(db_session, key)
    rec = Recording()
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: rec.adapter()})
    assert res["status"] == "completed" and res["completed"] == 4
    assert _order(rec) == ["plan", "a", "b", "merge"]


def test_a_failed_dependency_fails_its_dependents_and_spares_the_rest(client, db_session, org):
    h = org["headers"]
    a, pol = _setup(client, h)
    key, r = _post_job(client, h, pol, [_item("chem"), _item("pharm", "chem"), _item("tox", "pharm"),
                                        _item("botany")])
    assert r.status_code == 202, r.text
    job, _ = _items(db_session, key)
    rec = Recording(fail={"PROMPT<chem>"})
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: rec.adapter()})
    assert res["status"] == "completed_with_failures" and res["stop_reason"] == "ITEMS_FAILED"
    assert _order(rec) == ["chem", "botany"]          # pharm and tox were never sent to a provider
    _, items = _items(db_session, key)
    assert items["botany"].status == "completed"
    assert items["pharm"].failure_reason == "DEPENDENCY_FAILED: chem"
    assert items["tox"].failure_reason == "DEPENDENCY_FAILED: pharm"      # transitive


@pytest.mark.parametrize("items, fragment", [
    ([_item("a", "b"), _item("b", "c"), _item("c", "a")], "cycle"),
    ([_item("a", "a")], "itself"),
    ([_item("a", "ghost")], "unknown"),
    ([_item("a"), _item("a")], "unique"),
])
def test_an_invalid_graph_is_refused_at_creation(client, db_session, org, items, fragment):
    h = org["headers"]
    _, pol = _setup(client, h)
    key, r = _post_job(client, h, pol, items)
    assert r.status_code == 422 and fragment in r.text
    assert db_session.execute(select(AIJob).where(AIJob.job_key == key)).scalar_one_or_none() is None


def test_handoff_shows_what_each_pending_item_waits_for(client, db_session, org):
    h = org["headers"]
    a, pol = _setup(client, h)
    key, r = _post_job(client, h, pol, [_item("c"), _item("b", "a"), _item("a")])
    job, _ = _items(db_session, key)

    def stop_after_first(req):
        ai_job_service.request_control(db_session, db_session.get(AIJob, job.id), "pause")
        return httpx.Response(200, json=ok_body())
    adapter = AnthropicAdapter(transport=httpx.MockTransport(stop_after_first), api_key=SECRET)
    ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: adapter})
    hand = client.get(f"{B}/jobs/{key}/handoff", headers=h)
    assert hand.status_code == 200, hand.text
    package = hand.json()["package"]
    assert package["completed_items"] == ["c"]
    assert package["waiting_on"] == {"b": ["a"]}       # a has no dependency, so it is not listed


def test_a_job_without_dependencies_behaves_as_before(client, db_session, org):
    h = org["headers"]
    a, pol = _setup(client, h)
    key, r = _post_job(client, h, pol, [{"key": f"doc-{i}", "prompt": f"PROMPT<doc-{i}>"} for i in range(3)])
    job, items = _items(db_session, key)
    assert all(i.depends_on == [] for i in items.values())
    rec = Recording()
    ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: rec.adapter()})
    assert _order(rec) == ["doc-0", "doc-1", "doc-2"]
