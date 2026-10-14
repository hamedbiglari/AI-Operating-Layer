"""
Background Processing Policy Worker Enforcement tests (ADR-095, prompt §5-10).

Key invariants:
1. CONNECTED != ENABLED (a connected account not in allowed_account_ids MUST NOT be selected)
2. No policy for a task type → task refused with POLICY_MISSING
3. Policy disabled → task refused with POLICY_DISABLED
4. Policy enabled + allowed accounts → PolicyDecision.allowed = True with correct account list
5. Tenant isolation: Tenant B's accounts never appear in Tenant A's decisions
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
import uuid as _uuid
from app.services.background_policy_service import check_background_policy

client = TestClient(app)


def _acct(client, org, label="A"):
    h = org["headers"]
    pr = client.post("/api/v1/ai-center/providers", headers=h,
                     json={"name": f"P-{uuid.uuid4().hex[:6]}", "adapter_key": "test_provider"}).json()
    return client.post("/api/v1/ai-center/accounts", headers=h, json={"provider_id": pr["id"], "label": label}).json()["id"]


def hdr(org): return org["headers"]
def post_(path, org, body): r=client.post(f"/api/v1{path}",json=body,headers=hdr(org)); assert r.status_code in(200,201),r.text[:200]; return r.json()
def put_(path, org, body): r=client.put(f"/api/v1{path}",json=body,headers=hdr(org)); assert r.status_code==200,r.text[:200]; return r.json()


# ─── Unit: policy service ────────────────────────────────────────────────────

def test_no_policy_means_task_refused(db_session, register_org) -> None:
    org = register_org()
    decision = check_background_policy(db_session, organization_id=_uuid.UUID(str(org["organization"]["id"])), task_type="document_processing")
    assert not decision.allowed
    assert "POLICY_MISSING" in decision.reason

def test_disabled_policy_means_task_refused(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    acct_id = _acct(client, org)
    put_("/agent-network/background-policies/research", org, {"enabled": False, "allowed_account_ids": [acct_id]})
    decision = check_background_policy(db_session, organization_id=_uuid.UUID(str(org["organization"]["id"])), task_type="research")
    assert not decision.allowed
    assert "POLICY_DISABLED" in decision.reason

def test_connected_account_not_in_policy_is_refused(client: TestClient, register_org, db_session) -> None:
    """CRITICAL: CONNECTED != ENABLED. This is the primary invariant."""
    org = register_org()
    connected_account = _acct(client, org, "connected")  # exists (connected) but NOT in the policy
    allowed_account = _acct(client, org, "allowed")      # IS in the policy
    put_("/agent-network/background-policies/knowledge_generation", org,
         {"enabled": True, "allowed_account_ids": [allowed_account]})
    decision = check_background_policy(db_session, organization_id=_uuid.UUID(str(org["organization"]["id"])), task_type="knowledge_generation")
    assert decision.allowed
    # The connected_account is NOT in the allowed list
    assert uuid.UUID(connected_account) not in decision.allowed_account_ids
    assert uuid.UUID(allowed_account) in decision.allowed_account_ids

def test_policy_with_empty_account_list_is_refused(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    put_("/agent-network/background-policies/embedding", org, {"enabled": True, "allowed_account_ids": []})
    decision = check_background_policy(db_session, organization_id=_uuid.UUID(str(org["organization"]["id"])), task_type="embedding")
    assert not decision.allowed
    assert "POLICY_NO_ACCOUNTS" in decision.reason

def test_enabled_policy_with_accounts_is_allowed(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    a1, a2 = _acct(client, org, "a1"), _acct(client, org, "a2")
    put_("/agent-network/background-policies/summarization", org,
         {"enabled": True, "allowed_account_ids": [a1, a2], "routing_mode": "auto_priority", "max_cost_per_run": 0.5})
    decision = check_background_policy(db_session, organization_id=_uuid.UUID(str(org["organization"]["id"])), task_type="summarization")
    assert decision.allowed
    assert set(decision.allowed_account_ids) == {uuid.UUID(a1), uuid.UUID(a2)}
    assert decision.routing_mode == "auto_priority"
    assert decision.max_cost_per_run == 0.5

def test_tenant_isolation_of_background_policies(client: TestClient, register_org, db_session) -> None:
    a = register_org(); b = register_org()
    acct = _acct(client, a)
    put_("/agent-network/background-policies/translation", a, {"enabled": True, "allowed_account_ids": [acct]})
    # Tenant B's decision for the same task type must be POLICY_MISSING
    decision_b = check_background_policy(db_session, organization_id=b["organization"]["id"], task_type="translation")
    assert not decision_b.allowed and "POLICY_MISSING" in decision_b.reason

def test_background_policy_persists_and_updates(client: TestClient, register_org) -> None:
    org = register_org()
    a1 = _acct(client, org, "a1"); a2 = _acct(client, org, "a2")
    put_("/agent-network/background-policies/ai_visibility", org, {"enabled": True, "allowed_account_ids": [a1]})
    put_("/agent-network/background-policies/ai_visibility", org, {"enabled": True, "allowed_account_ids": [a1, a2]})
    policies = client.get("/api/v1/agent-network/background-policies", headers=hdr(org)).json()
    found = next(p for p in policies if p["task_type"] == "ai_visibility")
    assert set(found["allowed_account_ids"]) == {a1, a2}

def test_task_type_eligibility_api(db_session, register_org) -> None:
    """Worker enforcement path: same db_session proves the policy is read correctly."""
    from app.models.background_policy import BackgroundTaskPolicy
    from app.services.background_policy_service import check_background_policy as _cbp
    org = register_org(); org_id = _uuid.UUID(str(org["organization"]["id"]))
    d = _cbp(db_session, organization_id=org_id, task_type="demand_analysis")
    assert not d.allowed
    acct = _uuid.uuid4()
    pol = BackgroundTaskPolicy(organization_id=org_id, task_type="demand_analysis",
                               enabled=True, allowed_account_ids=[str(acct)])
    db_session.add(pol); db_session.flush()
    d2 = _cbp(db_session, organization_id=org_id, task_type="demand_analysis")
    assert d2.allowed
    assert acct in d2.allowed_account_ids


def test_policy_rejects_another_tenants_account(client: TestClient, register_org) -> None:
    a = register_org(); b = register_org()
    foreign = _acct(client, b)
    r = client.put("/api/v1/agent-network/background-policies/research", headers=a["headers"],
                   json={"enabled": True, "allowed_account_ids": [foreign]})
    assert r.status_code == 422
