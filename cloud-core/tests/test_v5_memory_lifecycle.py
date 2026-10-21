"""Prompt v5 §11-14, §87 (ADR-133): working memory has a lifecycle, state records supersede each other
instead of piling up as equals, model output is not validated by being written, and memory never turns
into a claim. Tenant isolation of the transition endpoint is checked too."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import exc, func, select, text

from app.models.ai_center import AIWorkingMemory
from app.models.claim import Claim
from app.services import ai_memory_service as memory

B = "/api/v1/ai-center"


@pytest.fixture()
def org(register_org):
    return register_org()


def _org_id(client, org):
    return uuid.UUID(str(org["organization"]["id"]))


def test_state_records_supersede_and_point_at_their_successor(client, db_session, org):
    oid = _org_id(client, org)
    v1 = memory.write(db_session, organization_id=oid, job_key="j", kind="job_state", content={"s": 1}, created_by="system")
    v2 = memory.write(db_session, organization_id=oid, job_key="j", kind="job_state", content={"s": 2}, created_by="system")
    v3 = memory.write(db_session, organization_id=oid, job_key="j", kind="job_state", content={"s": 3}, created_by="system")
    for r in (v1, v2, v3):
        db_session.refresh(r)
    assert (v1.status, v2.status, v3.status) == ("superseded", "superseded", "active")
    assert v1.superseded_by_id == v2.id and v2.superseded_by_id == v3.id and v3.superseded_by_id is None
    assert memory.latest(db_session, organization_id=oid, job_key="j", kind="job_state").id == v3.id
    # nothing was deleted
    assert db_session.execute(select(func.count()).select_from(AIWorkingMemory).where(
        AIWorkingMemory.organization_id == oid, AIWorkingMemory.job_key == "j")).scalar_one() == 3


def test_findings_accumulate_and_model_output_starts_unvalidated(client, db_session, org):
    oid = _org_id(client, org)
    a = memory.write(db_session, organization_id=oid, job_key="j", kind="intermediate_finding", content={"r": "a"},
                     created_by="execution:00000000-0000-0000-0000-000000000001")
    b = memory.write(db_session, organization_id=oid, job_key="j", kind="intermediate_finding", content={"r": "b"},
                     created_by="execution:00000000-0000-0000-0000-000000000002")
    u = memory.write(db_session, organization_id=oid, job_key="j", kind="open_question", content={"q": "?"},
                     created_by="user:x")
    db_session.refresh(a)
    assert (a.status, b.status, u.status) == ("created", "created", "active")   # findings are not superseded


def test_only_the_defined_transitions_exist(client, db_session, org):
    oid = _org_id(client, org)
    f = memory.write(db_session, organization_id=oid, job_key="j", kind="intermediate_finding", content={"r": 1},
                     created_by="execution:00000000-0000-0000-0000-000000000001")
    with pytest.raises(memory.InvalidMemoryTransition):
        memory.transition(db_session, f, "active", actor="test")            # must be validated first
    with pytest.raises(memory.InvalidMemoryTransition):
        memory.transition(db_session, f, "superseded", actor="test")        # only by a newer version
    memory.transition(db_session, f, "validated", actor="test", reason="checked against source")
    memory.transition(db_session, f, "active", actor="test")
    memory.transition(db_session, f, "archived", actor="test")
    with pytest.raises(memory.InvalidMemoryTransition):
        memory.transition(db_session, f, "active", actor="test")            # archived is terminal
    assert [t["to"] for t in f.provenance["transitions"]] == ["validated", "active", "archived"]


def test_database_refuses_an_unknown_status(client, db_session, org):
    oid = _org_id(client, org)
    f = memory.write(db_session, organization_id=oid, job_key="j", kind="open_question", content={"q": 1}, created_by="system")
    with pytest.raises(exc.IntegrityError):
        db_session.execute(text("UPDATE ai_working_memory SET status = 'canonical' WHERE id = :i"), {"i": f.id})
        db_session.flush()
    db_session.rollback()


def test_memory_never_becomes_a_claim(client, db_session, org):
    oid = _org_id(client, org)
    before = db_session.execute(select(func.count()).select_from(Claim)).scalar_one()
    f = memory.write(db_session, organization_id=oid, job_key="j", kind="intermediate_finding",
                     content={"claim": "Toranjebin contains mannitol"}, created_by="execution:00000000-0000-0000-0000-000000000003")
    for s in ("validated", "active", "archived"):
        memory.transition(db_session, f, s, actor="test")
    assert db_session.execute(select(func.count()).select_from(Claim)).scalar_one() == before


def test_transition_endpoint_is_role_and_tenant_scoped(client, db_session, register_org, org):
    oid = _org_id(client, org)
    f = memory.write(db_session, organization_id=oid, job_key="j", kind="intermediate_finding", content={"r": 9},
                     created_by="execution:00000000-0000-0000-0000-000000000004")
    other = register_org()
    assert client.post(f"{B}/memory/{f.id}/status", headers=other["headers"], json={"status": "validated"}).status_code == 404
    r = client.post(f"{B}/memory/{f.id}/status", headers=org["headers"], json={"status": "validated", "reason": "ok"})
    assert r.status_code == 200 and r.json()["status"] == "validated"
    r = client.post(f"{B}/memory/{f.id}/status", headers=org["headers"], json={"status": "validated"})
    assert r.status_code == 409
    assert client.post(f"{B}/memory/{f.id}/status", headers=org["headers"], json={"status": "superseded"}).status_code == 422


def test_agent_memory_access_level_is_constrained(client, db_session, org):
    with pytest.raises(exc.IntegrityError):
        db_session.execute(text(
            "INSERT INTO agent_memory_bindings (id, organization_id, agent_definition_id, memory_profile_id, access_level, "
            "created_at, updated_at) VALUES (gen_random_uuid(), :o, gen_random_uuid(), gen_random_uuid(), 'superuser', "
            "now(), now())"), {"o": _org_id(client, org)})
        db_session.flush()
    db_session.rollback()
