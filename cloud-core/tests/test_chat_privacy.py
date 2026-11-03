"""SEC-chat-memory-org-read: a chat question and its answer run through the single AI execution path, so they are
stored as an AI job (key chat-<message id>) and AI working-memory rows. Only the person who asked may read them;
nobody else in the organization, at any role; and they go when the conversation or its user is deleted."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.ai_center import AIJob, AIWorkingMemory
from app.services import chat_service as svc
from tests.test_chat import Echo, _adapters, _convo, _enable, _policy, _topic, _user, cred_key  # noqa: F401

QUESTION = "What did the confidential trial measure?"


def _asked(client, register_org, db):
    org = register_org()
    pol, acct = _policy(client, org["headers"])
    topic = _topic(client, org["headers"], db, n=2)
    _enable(client, org["headers"], routing_policy_id=pol["id"])
    convo = _convo(db, client, org["headers"], knowledge_object_id=topic["id"])
    msg = svc.ask(db, convo=convo, user=_user(db, org), question=QUESTION, adapters=_adapters(db, acct, Echo()))
    key = msg.grounding["ai_job_key"]
    assert key.startswith("chat-")
    return {"org": org, "convo": convo, "key": key, "acct": acct, "topic": topic}


# --- the question is not copied into the job ----------------------------------------------------------------
def test_the_job_goal_and_its_state_row_do_not_repeat_the_question(client, register_org, db_session):
    a = _asked(client, register_org, db_session)
    goal = db_session.execute(select(AIJob.goal).where(AIJob.job_key == a["key"])).scalar_one()
    assert "confidential" not in goal and QUESTION not in goal
    states = db_session.execute(select(AIWorkingMemory.content).where(
        AIWorkingMemory.job_key == a["key"], AIWorkingMemory.kind == "job_state")).scalars().all()
    assert states and all("confidential" not in str(s.get("goal", "")) for s in states)
    r = client.get(f"/api/v1/ai-center/jobs/{a['key']}", headers=a["org"]["headers"])
    assert r.status_code == 200 and "confidential" not in r.text                     # the owner's own view
