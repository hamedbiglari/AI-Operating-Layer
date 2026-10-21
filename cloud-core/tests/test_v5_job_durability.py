"""Prompt v5 §10/§74, Workflows B and D (ADR-131): an AI job survives a dead worker and a provider limit.

* A worker holds a lease; a second worker on the same job is refused (no item is processed twice).
* A lease that expires (the worker died) is recovered by `recover_jobs`; the job resumes from its
  checkpoint and finished items are not redone.
* A job blocked only by a rate limit / quota carries `resume_after` and resumes by itself after it,
  a bounded number of times. A job blocked by something a person must fix gets no resume time.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.ai_center import AIJob, AIWorkingMemory
from app.services import ai_job_service
from tests.test_ai_center import B, Scripted, _job, acct, cred_key, mk_account, mk_policy, mk_provider, ok_body  # noqa: F401


@pytest.fixture()
def org(register_org):
    return register_org()


@pytest.fixture(autouse=True)
def no_background(monkeypatch):
    import app.api.v1.ai_center as api
    monkeypatch.setattr(api, "_run_in_background", lambda job_id: None)


def _now():
    return datetime.now(timezone.utc)


def _one_account(client, h, label="A"):
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], label)
    return a, mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])


def _states(db, job):
    return [m.content for m in db.execute(select(AIWorkingMemory).where(
        AIWorkingMemory.job_key == job.job_key, AIWorkingMemory.kind == "job_state")
        .order_by(AIWorkingMemory.version)).scalars()]


def test_lease_is_released_after_a_normal_run(client, db_session, org):
    h = org["headers"]
    a, pol = _one_account(client, h)
    job = _job(client, db_session, h, pol, 3)
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: Scripted(lambda n: (200, ok_body())).adapter()})
    assert res["status"] == "completed"
    db_session.refresh(job)
    assert job.lease_owner is None and job.lease_expires_at is None and job.resume_after is None


def test_a_second_worker_is_refused_while_the_lease_is_live(client, db_session, org):
    h = org["headers"]
    a, pol = _one_account(client, h)
    job = _job(client, db_session, h, pol, 3)
    job.status, job.lease_owner, job.lease_expires_at = "running", "worker-1", _now() + timedelta(minutes=10)
    db_session.commit()
    s = Scripted(lambda n: (200, ok_body()))
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: s.adapter()})
    assert res["stop_reason"] == "LEASED_BY_ANOTHER_WORKER" and s.calls == 0
    db_session.refresh(job)
    assert job.lease_owner == "worker-1"          # the live worker keeps its lease


def test_dead_worker_is_recovered_and_finished_items_are_not_redone(client, db_session, org):
    """Workflow B: 4 of 10 items done, then the worker dies holding the lease."""
    h = org["headers"]
    a, pol = _one_account(client, h)
    job = _job(client, db_session, h, pol, 10)

    def first(n):
        if n == 4:
            ai_job_service.request_control(db_session, db_session.get(AIJob, job.id), "pause")
        return 200, ok_body()
    ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: Scripted(first).adapter()})
    # what a killed worker leaves behind: running, lease held, never released
    job.status, job.lease_owner, job.lease_expires_at = "running", "dead-worker", _now() - timedelta(seconds=1)
    db_session.commit()

    out = ai_job_service.recover_jobs(db_session)
    assert job.id in out["requeued"] and out["stale_leases"] >= 1
    db_session.refresh(job)
    assert job.status == "queued" and job.lease_owner is None and job.retry_count >= 1
    assert any(s.get("reason") == "worker lease expired" and s.get("previous_lease_owner") == "dead-worker"
               for s in _states(db_session, job))

    second = Scripted(lambda n: (200, ok_body()))
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: second.adapter()})
    assert res["status"] == "completed" and res["completed"] == 10
    assert second.calls == 6                      # only the six unfinished items


def test_live_lease_is_not_recovered(client, db_session, org):
    h = org["headers"]
    _a, pol = _one_account(client, h)
    job = _job(client, db_session, h, pol, 2)
    job.status, job.lease_owner, job.lease_expires_at = "running", "busy-worker", _now() + timedelta(minutes=5)
    db_session.commit()
    assert job.id not in ai_job_service.recover_jobs(db_session)["requeued"]
    db_session.refresh(job)
    assert job.status == "running" and job.lease_owner == "busy-worker"


def test_rate_limited_job_gets_a_resume_time_and_resumes_after_it(client, db_session, org):
    """Workflow D: the only account hits its rate limit at item 3."""
    h = org["headers"]
    a, pol = _one_account(client, h)
    job = _job(client, db_session, h, pol, 5)
    first = Scripted(lambda n: (200, ok_body()) if n <= 2 else (429, {}))
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: first.adapter()})
    assert res["status"] == "blocked" and res["completed"] == 2 and res["resume_after"]
    db_session.refresh(job)
    account = acct(db_session, a)
    assert job.resume_after == account.unavailable_until and job.resume_after > _now()

    # before the reset nothing happens
    assert job.id not in ai_job_service.recover_jobs(db_session)["requeued"]
    # the reset time passes
    account.unavailable_until = job.resume_after = _now() - timedelta(seconds=1)
    account.health_status = "healthy"
    db_session.commit()
    out = ai_job_service.recover_jobs(db_session)
    assert job.id in out["requeued"]
    db_session.refresh(job)
    assert job.status == "queued" and job.auto_resume_count == 1 and job.resume_after is None

    second = Scripted(lambda n: (200, ok_body()))
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: second.adapter()})
    assert res["status"] == "completed" and res["completed"] == 5 and second.calls == 3


def test_auth_failure_gets_no_resume_time(client, db_session, org):
    """A rejected credential does not pass with time: the job waits for a person, never loops."""
    h = org["headers"]
    a, pol = _one_account(client, h)
    job = _job(client, db_session, h, pol, 3)
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: Scripted(lambda n: (401, {})).adapter()})
    assert res["status"] == "blocked" and res["resume_after"] is None
    assert job.id not in ai_job_service.recover_jobs(db_session)["requeued"]


def test_automatic_resumes_are_bounded(client, db_session, org, monkeypatch):
    monkeypatch.setattr(settings, "AI_JOB_MAX_AUTO_RESUMES", 2)
    h = org["headers"]
    _a, pol = _one_account(client, h)
    job = _job(client, db_session, h, pol, 1)
    job.status, job.stop_reason, job.auto_resume_count = "blocked", "PROVIDER_UNAVAILABLE", 2
    job.resume_after = _now() - timedelta(seconds=1)
    db_session.commit()
    assert job.id not in ai_job_service.recover_jobs(db_session)["requeued"]
    db_session.refresh(job)
    assert job.status == "blocked" and job.stop_reason == "AUTO_RESUME_LIMIT" and job.resume_after is None


def test_manual_resume_resets_the_allowance_and_api_shows_the_state(client, db_session, org):
    h = org["headers"]
    _a, pol = _one_account(client, h)
    job = _job(client, db_session, h, pol, 1)
    job.status, job.stop_reason, job.auto_resume_count = "blocked", "AUTO_RESUME_LIMIT", 24
    db_session.commit()
    view = client.get(f"{B}/jobs/{job.job_key}", headers=h).json()
    assert view["auto_resume_count"] == 24 and view["resume_after"] is None and view["worker_lease_active"] is False
    r = client.post(f"{B}/jobs/{job.job_key}/control", headers=h, json={"action": "resume"})
    assert r.status_code == 202 and r.json()["status"] == "queued" and r.json()["auto_resume_count"] == 0


def test_a_code_error_blocks_the_job_and_releases_the_lease(client, db_session, org, monkeypatch):
    h = org["headers"]
    a, pol = _one_account(client, h)
    job = _job(client, db_session, h, pol, 5)
    real = ai_job_service.prompt_safety.check_output
    calls = {"n": 0}

    def boom(*args, **kw):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("bug")
        return real(*args, **kw)
    monkeypatch.setattr(ai_job_service.prompt_safety, "check_output", boom)
    with pytest.raises(RuntimeError):
        ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: Scripted(lambda n: (200, ok_body())).adapter()})
    db_session.refresh(job)
    assert job.status == "blocked" and job.stop_reason == "WORKER_ERROR"
    assert job.lease_owner is None and job.resume_after is None
    assert job.id not in ai_job_service.recover_jobs(db_session)["requeued"]   # a bug is never retried by itself


# ---------------- ADR-132: the provider's Retry-After ----------------

def test_retry_after_parsing():
    from app.integrations.llm.base import parse_retry_after
    now = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    assert parse_retry_after("120") == 120
    assert parse_retry_after("0") == 1                                   # "now" still means wait a moment
    assert parse_retry_after("Tue, 20 Oct 2026 12:05:00 GMT", now=now) == 300
    assert parse_retry_after("Tue, 20 Oct 2026 11:00:00 GMT", now=now) is None   # in the past
    for bad in (None, "", "soon", "-5", "999999"):
        assert parse_retry_after(bad) is None                            # unreadable or longer than a day


def test_provider_retry_after_sets_the_resume_time(client, db_session, org):
    import httpx

    from app.integrations.llm.anthropic import AnthropicAdapter
    from app.models.ai_center import AIHealthEvent
    from tests.test_ai_center import SECRET

    h = org["headers"]
    a, pol = _one_account(client, h)
    job = _job(client, db_session, h, pol, 2)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=ok_body())
        return httpx.Response(429, json={}, headers={"retry-after": "120"})
    adapter = AnthropicAdapter(transport=httpx.MockTransport(handler), api_key=SECRET)
    before = _now()
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: adapter})
    assert res["status"] == "blocked" and res["completed"] == 1
    db_session.refresh(job)
    # 120 s from the header, not the 60 s default for a rate limit
    assert before + timedelta(seconds=115) <= job.resume_after <= _now() + timedelta(seconds=125)
    ev = db_session.execute(select(AIHealthEvent).where(AIHealthEvent.account_id == acct(db_session, a).id)
                            .order_by(AIHealthEvent.observed_at.desc())).scalars().first()
    assert ev.retry_after_seconds == 120 and ev.status == "rate_limited"
