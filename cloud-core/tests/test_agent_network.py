"""
Agent Network + Background Processing Policy tests (ADR-095/096, 2026-09-25).
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def reg(client, register_org, suffix=""):
    return register_org(suffix or None)

def hdr(org): return org["headers"]

def post_(client, path, org, body):
    r = client.post(f"/api/v1{path}", json=body, headers=hdr(org))
    assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text[:200]}"
    return r.json()

def get_(client, path, org):
    r = client.get(f"/api/v1{path}", headers=hdr(org))
    assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
    return r.json()

# ── Agent definition ───────────────────────────────────────────────────────

def test_create_and_list_agents(client: TestClient, register_org) -> None:
    org = register_org()
    a = post_(client, "/agent-network/agents", org, {"name": "Research-A", "agent_type": "research", "capabilities": ["web_search", "summarize"]})
    assert a["agent_type"] == "research" and a["status"] == "draft"
    items = get_(client, "/agent-network/agents", org)["items"]
    assert any(x["name"] == "Research-A" for x in items)

def test_agent_name_unique_per_tenant(client: TestClient, register_org) -> None:
    org = register_org()
    post_(client, "/agent-network/agents", org, {"name": "Dup", "agent_type": "content"})
    r = client.post("/api/v1/agent-network/agents", json={"name": "Dup", "agent_type": "content"}, headers=hdr(org))
    assert r.status_code == 409

def test_agent_tenant_isolation(client: TestClient, register_org) -> None:
    a = register_org(); b = register_org()
    agent = post_(client, "/agent-network/agents", a, {"name": "Private", "agent_type": "planner"})
    items_b = get_(client, "/agent-network/agents", b)["items"]
    assert not any(x["id"] == agent["id"] for x in items_b)
    r = client.get(f"/api/v1/agent-network/agents/{agent['id']}", headers=hdr(b))
    assert r.status_code == 404

# ── Sessions and tasks ─────────────────────────────────────────────────────

def test_session_and_tasks(client: TestClient, register_org) -> None:
    org = register_org()
    session = post_(client, "/agent-network/sessions", org, {"session_key": "run-001", "goal": "Research"})
    assert session["status"] == "active"
    sid = session["id"]
    t1 = post_(client, f"/agent-network/sessions/{sid}/tasks", org, {"task_type": "search", "task_key": "s1"})
    t2 = post_(client, f"/agent-network/sessions/{sid}/tasks", org, {"task_type": "summarize", "task_key": "s2", "depends_on": [t1["id"]]})
    tasks = get_(client, f"/agent-network/sessions/{sid}/tasks", org)
    assert len(tasks) == 2

def test_session_key_unique(client: TestClient, register_org) -> None:
    org = register_org()
    post_(client, "/agent-network/sessions", org, {"session_key": "dedup"})
    r = client.post("/api/v1/agent-network/sessions", json={"session_key": "dedup"}, headers=hdr(org))
    assert r.status_code == 409

# ── Handoffs ───────────────────────────────────────────────────────────────

def test_agent_handoff(client: TestClient, register_org) -> None:
    org = register_org()
    session = post_(client, "/agent-network/sessions", org, {"session_key": "hof-001"})
    # the raw handoff POST was replaced by the service-driven task handoff (see test_agent_execution.py)
    r = client.post(f"/api/v1/agent-network/sessions/{session['id']}/handoffs", json={}, headers=hdr(org))
    assert r.status_code == 405

# ── Memory Profiles ────────────────────────────────────────────────────────

def test_memory_profile_postgresql_is_canonical(client: TestClient, register_org) -> None:
    org = register_org()
    mp = post_(client, "/agent-network/memory-profiles", org, {"name": "Research Memory", "scope": "project"})
    assert mp["canonical_store"] == "postgresql"
    profiles = get_(client, "/agent-network/memory-profiles", org)
    assert all(p["canonical_store"] == "postgresql" for p in profiles)

def test_memory_profile_tenant_isolation(client: TestClient, register_org) -> None:
    a = register_org(); b = register_org()
    post_(client, "/agent-network/memory-profiles", a, {"name": "Private Memory"})
    profiles_b = get_(client, "/agent-network/memory-profiles", b)
    assert not any(p["name"] == "Private Memory" for p in profiles_b)

# ── Background Processing Policies ────────────────────────────────────────

def test_background_policy_empty_by_default(client: TestClient, register_org) -> None:
    org = register_org()
    policies = get_(client, "/agent-network/background-policies", org)
    # Connected != enabled for background processing
    assert not any(p["task_type"] == "document_processing" for p in policies)

def test_background_policy_upsert_persists(client: TestClient, register_org) -> None:
    org = register_org()
    pr = client.post("/api/v1/ai-center/providers", headers=hdr(org), json={"name": "P", "adapter_key": "anthropic"}).json()
    acct_id = client.post("/api/v1/ai-center/accounts", headers=hdr(org), json={"provider_id": pr["id"], "label": "A"}).json()["id"]
    r = client.put("/api/v1/agent-network/background-policies/document_processing",
                   json={"enabled": True, "allowed_account_ids": [acct_id], "routing_mode": "auto_priority",
                         "max_cost_per_run": 1.5}, headers=hdr(org))
    assert r.status_code == 200 and r.json()["enabled"] is True
    found = next(p for p in get_(client, "/agent-network/background-policies", org) if p["task_type"] == "document_processing")
    assert found["enabled"] is True and acct_id in found["allowed_account_ids"]

def test_background_policy_tenant_isolation(client: TestClient, register_org) -> None:
    a = register_org(); b = register_org()
    client.put("/api/v1/agent-network/background-policies/research", json={"enabled": True}, headers=hdr(a))
    b_policies = get_(client, "/agent-network/background-policies", b)
    assert not any(p["task_type"] == "research" for p in b_policies)

def test_existing_ai_agent_table_unchanged(db_session) -> None:
    """The legacy ai_agents table (crawler traffic detection) must not be touched."""
    from sqlalchemy import text
    # Table must still exist; agent orchestration is in agent_definitions
    result = db_session.execute(text("SELECT count(*) FROM ai_agents")).scalar_one()
    assert result == 0   # empty in a fresh DB
    result2 = db_session.execute(text("SELECT count(*) FROM agent_definitions")).scalar_one()
    assert result2 == 0  # also empty; separate concern
