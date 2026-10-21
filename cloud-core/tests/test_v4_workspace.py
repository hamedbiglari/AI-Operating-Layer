"""v4 persistent command workspace (ADR-125): drafts that survive the browser, versions that cannot be
rewritten once run, explicit scope, resumable execution, and privacy between users."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import exc, text

from app.main import app
from app.services import workspace_service as svc
from app.models.workspace import WorkspaceCommand
from tests.test_v4_context_synthesis import Echo, _adapters, _policy, _topic_with_claims, cred_key  # noqa: F401

W = "/api/v1/workspace"


@pytest.fixture()
def org(register_org):
    return register_org()


def _second_user(client, org, role="editor"):
    email = f"u{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/v1/users", headers=org["headers"], json={"email": email, "name": "Second",
                                                                   "password": "second-pass-123", "role": role})
    assert r.status_code == 201, r.text
    tok = client.post("/api/v1/auth/login", data={"username": email, "password": "second-pass-123"}).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


def _run_worker(db, cmd_id, version):
    """The eager Celery task opens its own session; drive the worker body on the test session instead."""
    return svc.execute(db, command_id=uuid.UUID(cmd_id), version=version)


# ---------------------------------------------------------------------- parser
@pytest.mark.parametrize("text_,intent", [
    ("Analyze all human studies on Toranjebin safety.", "evidence_research"),
    ("Show all claims derived from page 37.", "claims_from_page"),
    ("Show all unsupported statements in this section.", "unsupported_statements"),
    ("Find contradictions between these studies.", "contradictions"),
    ("Reprocess this PDF using the latest extraction technology.", "reprocess_document"),
    ("Check whether this newly discovered section applies to all topics in this category.", "section_applicability"),
    ("Research this empty Master Topic Matrix cell.", "matrix_cell_research"),
    ("Find evidence for this claim.", "find_evidence_for_claim"),
    ("Continue the previous research task.", "continue_previous"),
    ("تناقض‌های مطالعات را پیدا کن", "contradictions"),
    ("ادعاهای صفحه ۳۷ را نشان بده", "claims_from_page"),
    ("hello", "unknown"),
])
def test_the_parser_proposes_an_intent(text_, intent):
    assert svc.parse(text_)["intent"] == intent


def test_parser_hints_page_year_and_population():
    p = svc.parse("Find human studies after 2015 on page 12 about mannitol safety")
    assert p["hints"]["page"] == 12 and p["hints"]["published_after"] == 2015 and p["hints"]["population"] == "human"
    assert "mannitol" in p["hints"]["terms"] and "safety" in p["hints"]["terms"]
    assert svc.parse("ادعاهای صفحه ۳۷")["hints"]["page"] == 37


# ---------------------------------------------------------------------- drafts survive the browser (§48)
def test_a_typed_draft_survives_closing_the_browser(client, org):
    h = org["headers"]
    cmd = client.post(f"{W}/commands", headers=h, json={"text": "Analyze human"}).json()
    rev = cmd["current"]["draft_revision"]
    saved = client.put(f"{W}/commands/{cmd['id']}/draft", headers=h,
                       json={"text": "Analyze human studies on safety", "base_revision": rev}).json()
    assert saved["saved"] and saved["version"]["draft_revision"] == rev + 1
    # a brand-new client: no cookies, no local storage, nothing but the token — the server has the draft
    fresh = TestClient(app)
    fresh.app.dependency_overrides = client.app.dependency_overrides
    again = fresh.get(f"{W}/commands/{cmd['id']}", headers=h).json()
    assert again["current"]["text"] == "Analyze human studies on safety"
    assert again["state"] == "draft" and again["current"]["intent"] == "evidence_research"
    offered = fresh.get(f"{W}/commands/resumable", headers=h).json()
    assert any(o["id"] == cmd["id"] and o["offer"] == ["continue_editing"] for o in offered)


def test_a_stale_tab_cannot_overwrite_a_newer_draft(client, org):
    h = org["headers"]
    cmd = client.post(f"{W}/commands", headers=h, json={"text": "v"}).json()
    rev = cmd["current"]["draft_revision"]
    assert client.put(f"{W}/commands/{cmd['id']}/draft", headers=h, json={"text": "tab A", "base_revision": rev}).status_code == 200
    stale = client.put(f"{W}/commands/{cmd['id']}/draft", headers=h, json={"text": "tab B", "base_revision": rev})
    assert stale.status_code == 409
    assert client.get(f"{W}/commands/{cmd['id']}", headers=h).json()["current"]["text"] == "tab A"


# ---------------------------------------------------------------------- versions (§49)
def test_running_freezes_the_version_and_editing_starts_the_next(client, db_session, org):
    h = org["headers"]
    ko, _ = _topic_with_claims(client, h, db_session, n=1, contested=1)
    cmd = client.post(f"{W}/commands", headers=h, json={"text": "Find contradictions between these studies.",
                                                        "knowledge_object_id": ko["id"]}).json()
    r = client.post(f"{W}/commands/{cmd['id']}/run", headers=h)
    assert r.status_code == 202, r.text
    _run_worker(db_session, cmd["id"], 1)
    v1 = client.get(f"{W}/commands/{cmd['id']}/versions/1", headers=h).json()
    assert v1["frozen"] and v1["execution_state"] == "completed"
    assert v1["result"]["claims_with_both_sides_but_no_conflict_record"]           # contested claim reported
    # the database itself refuses to rewrite what was asked
    with pytest.raises(exc.IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE workspace_command_versions SET text = 'rewritten' "
                                    "WHERE command_id = :c AND version = 1"), {"c": cmd["id"]})
    edited = client.put(f"{W}/commands/{cmd['id']}/draft", headers=h,
                        json={"text": "Find contradictions between these studies after 2015."}).json()
    assert edited["version"]["version"] == 2 and not edited["version"]["frozen"]
    assert client.get(f"{W}/commands/{cmd['id']}/versions/1", headers=h).json()["text"] == \
        "Find contradictions between these studies."
    diff = client.get(f"{W}/commands/{cmd['id']}/compare?a=1&b=2", headers=h).json()
    assert any("after 2015" in line for line in diff["text_diff"])
    restored = client.post(f"{W}/commands/{cmd['id']}/versions/1/restore", headers=h).json()
    assert restored["text"] == "Find contradictions between these studies." and restored["version"] == 2
    again = client.post(f"{W}/commands/{cmd['id']}/regenerate", headers=h)
    assert again.status_code == 202 and again.json()["current_version"] == 3


def test_scope_must_be_explicit_before_running(client, org):
    h = org["headers"]
    cmd = client.post(f"{W}/commands", headers=h, json={"text": "Show all claims derived from page 37."}).json()
    plan = client.post(f"{W}/commands/{cmd['id']}/plan", headers=h).json()
    assert plan["plan"]["intent"] == "claims_from_page" and plan["plan"]["missing_scope"] == ["document_id"]
    assert plan["scope"]["page"] == 37
    r = client.post(f"{W}/commands/{cmd['id']}/run", headers=h)
    assert r.status_code == 422 and "document_id" in str(r.json())
    assert client.get(f"{W}/commands/{cmd['id']}/versions/1", headers=h).json()["frozen"] is False


def test_unknown_intent_is_blocked_with_a_reason_not_guessed(client, db_session, org):
    h = org["headers"]
    cmd = client.post(f"{W}/commands", headers=h, json={"text": "hello there"}).json()
    plan = client.post(f"{W}/commands/{cmd['id']}/plan", headers=h).json()
    assert plan["plan"]["missing_scope"] == ["intent"]
    assert client.post(f"{W}/commands/{cmd['id']}/run", headers=h).status_code == 422


# ---------------------------------------------------------------------- deterministic intents (§54)
def test_coverage_and_claim_evidence_intents_answer_from_the_knowledge_base(client, db_session, org):
    h = org["headers"]
    ko, claims = _topic_with_claims(client, h, db_session, n=2, contested=0)
    cov = client.post(f"{W}/commands", headers=h, json={"text": "Run the coverage audit",
                                                        "knowledge_object_id": ko["id"]}).json()
    client.post(f"{W}/commands/{cov['id']}/run", headers=h)
    _run_worker(db_session, cov["id"], 1)
    v = client.get(f"{W}/commands/{cov['id']}/versions/1", headers=h).json()
    assert v["execution_state"] == "completed", v["error"]
    assert v["result"]["dimensions"]["knowledge"]["claims"] == 2
    ev = client.post(f"{W}/commands", headers=h, json={"text": "Find evidence for this claim.",
                                                       "scope": {"claim_id": claims[0]["id"]}}).json()
    client.post(f"{W}/commands/{ev['id']}/run", headers=h)
    _run_worker(db_session, ev["id"], 1)
    r = client.get(f"{W}/commands/{ev['id']}/versions/1", headers=h).json()["result"]
    assert len(r["evidence"]) == 1 and r["external_search"]["run"] is False


# ---------------------------------------------------------------------- AI intents, resume (§50, §53)
def test_ai_command_runs_synthesis_and_resumes_after_a_provider_stop(client, db_session, org, monkeypatch):
    h = org["headers"]
    pol, a = _policy(client, h)
    ko, _ = _topic_with_claims(client, h, db_session, n=3, contested=0)
    cmd = client.post(f"{W}/commands", headers=h, json={"text": "Analyze all human studies on Taranjabin composition.",
                                                        "knowledge_object_id": ko["id"]}).json()
    client.put(f"{W}/commands/{cmd['id']}/draft", headers=h, json={
        "text": "Analyze all human studies on Taranjabin composition.", "model_config": {"policy_id": pol["id"]},
        "budget": {"context_tokens": 24000, "max_output_tokens": 400}})
    plan = client.post(f"{W}/commands/{cmd['id']}/plan", headers=h).json()["plan"]
    assert plan["runs_a_model"] and plan["synthesis_plan"]["units"] == 3          # human filter matched all three
    assert plan["synthesis_plan"]["scope_applied"]["terms"]
    # first attempt: the provider refuses (rate limited) — the command is blocked, not lost
    from app.services import synthesis_service
    real_advance = synthesis_service.advance
    monkeypatch.setattr(synthesis_service, "advance",
                        lambda db, run, **kw: real_advance(db, run, adapters=_adapters(db, a, Echo(fail_status=429))))
    client.post(f"{W}/commands/{cmd['id']}/run", headers=h)
    _run_worker(db_session, cmd["id"], 1)
    state = client.get(f"{W}/commands/{cmd['id']}", headers=h).json()
    assert state["state"] == "blocked", state["error"]
    assert state["resumable"] and state["error"]
    offered = client.get(f"{W}/commands/resumable", headers=h).json()
    assert any(o["id"] == cmd["id"] and "continue" in o["offer"] for o in offered)
    # the user comes back; the provider has recovered
    from app.models.ai_center import AIProviderAccount
    acc = db_session.get(AIProviderAccount, uuid.UUID(a["id"]))
    acc.health_status, acc.unavailable_until = "healthy", None
    db_session.commit()
    monkeypatch.setattr(synthesis_service, "advance",
                        lambda db, run, **kw: real_advance(db, run, adapters=_adapters(db, a, Echo())))
    out = client.post(f"{W}/commands/{cmd['id']}/resume", headers=h)
    assert out.status_code == 200, out.text
    v = client.get(f"{W}/commands/{cmd['id']}/versions/1", headers=h).json()
    assert v["execution_state"] == "completed" and v["result"]["coverage"]["omitted"] == 0
    assert v["cost"]["executions_with_unknown_cost"] >= 1          # no price configured: counted, never zeroed


def test_cancel_stops_and_records(client, db_session, org):
    h = org["headers"]
    pol, _ = _policy(client, h)
    ko, _ = _topic_with_claims(client, h, db_session, n=2, contested=0)
    cmd = client.post(f"{W}/commands", headers=h, json={"text": "Summarise the composition",
                                                        "knowledge_object_id": ko["id"]}).json()
    client.put(f"{W}/commands/{cmd['id']}/draft", headers=h, json={"text": "Summarise the composition",
                                                                   "model_config": {"policy_id": pol["id"]}})
    client.post(f"{W}/commands/{cmd['id']}/run", headers=h)        # worker not run: stays queued
    assert client.post(f"{W}/commands/{cmd['id']}/cancel", headers=h).json()["state"] == "cancelled"
    assert client.post(f"{W}/commands/{cmd['id']}/cancel", headers=h).status_code == 409


# ---------------------------------------------------------------------- privacy, archive, delete (§49, §64)
def test_commands_are_private_to_their_author(client, org, register_org):
    h = org["headers"]
    cmd = client.post(f"{W}/commands", headers=h, json={"text": "private research note"}).json()
    colleague = _second_user(client, org)
    for path in (f"/commands/{cmd['id']}", f"/commands/{cmd['id']}/versions"):
        assert client.get(W + path, headers=colleague).status_code == 404
    assert client.put(f"{W}/commands/{cmd['id']}/draft", headers=colleague, json={"text": "x"}).status_code == 404
    assert client.get(f"{W}/commands", headers=colleague).json()["total"] == 0
    other = register_org()["headers"]
    assert client.get(f"{W}/commands/{cmd['id']}", headers=other).status_code == 404
    viewer = _second_user(client, org, role="viewer")
    assert client.post(f"{W}/commands", headers=viewer, json={"text": "x"}).status_code == 403


def test_archive_hides_and_delete_requires_explicit_permanent(client, db_session, org):
    h = org["headers"]
    cmd = client.post(f"{W}/commands", headers=h, json={"text": "keep me"}).json()
    client.post(f"{W}/commands/{cmd['id']}/archive", headers=h)
    assert client.get(f"{W}/commands", headers=h).json()["total"] == 0
    assert client.get(f"{W}/commands?archived=true", headers=h).json()["total"] == 1
    assert client.put(f"{W}/commands/{cmd['id']}/draft", headers=h, json={"text": "x"}).status_code == 409
    assert client.delete(f"{W}/commands/{cmd['id']}", headers=h).status_code == 400
    assert client.get(f"{W}/commands/{cmd['id']}", headers=h).status_code == 200
    assert client.delete(f"{W}/commands/{cmd['id']}?permanent=true", headers=h).status_code == 204
    assert client.get(f"{W}/commands/{cmd['id']}", headers=h).status_code == 404
    assert db_session.get(WorkspaceCommand, uuid.UUID(cmd["id"])) is None


def test_history_search_and_state_filter(client, org):
    h = org["headers"]
    client.post(f"{W}/commands", headers=h, json={"text": "mannitol safety"})
    client.post(f"{W}/commands", headers=h, json={"text": "saffron colour"})
    assert client.get(f"{W}/commands?q=mannitol", headers=h).json()["total"] == 1
    assert client.get(f"{W}/commands?state=draft", headers=h).json()["total"] == 2
