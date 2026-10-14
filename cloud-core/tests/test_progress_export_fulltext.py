"""SSE job progress, memory export, full-text acquisition."""
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import exc, select, text

from app.core.config import settings

from app.ingestion import url_source
from app.integrations.research import scholarly
from app.models.ai_center import AIJob
from app.services import ai_job_service
from app.services import federated_research_service as fsvc
from tests.test_ai_center import B, Scripted, acct, mk_account, mk_policy, mk_provider, ok_body
from tests.test_federated_research import _handler, _ko


@pytest.fixture(autouse=True)
def cred_key(monkeypatch):
    monkeypatch.setattr(settings, "AI_CREDENTIAL_KEY", SecretStr(Fernet.generate_key().decode()))


@pytest.fixture(autouse=True)
def stream_uses_test_session(db_session, monkeypatch):
    """The SSE stream opens its own session per poll; tests run inside one transaction, so hand it that one."""
    import app.api.v1.ai_center as api

    class _Shared:
        def execute(self, *a, **k):
            db_session.expire_all()
            return db_session.execute(*a, **k)

        def __getattr__(self, name):
            return getattr(db_session, name)

        def close(self):
            pass
    monkeypatch.setattr(api, "stream_session_factory", lambda: _Shared())


@pytest.fixture()
def no_background(monkeypatch):
    import app.api.v1.ai_center as api
    monkeypatch.setattr(api, "_run_in_background", lambda job_id: None)


def _run_job(client, db_session, org, n=3):
    h = org["headers"]
    a = mk_account(client, h, mk_provider(client, h)["id"], "A")
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    key = f"job-{uuid.uuid4().hex[:8]}"
    r = client.post(f"{B}/jobs", headers=h, json={"job_key": key, "goal": "extract", "policy_id": pol["id"],
                    "items": [{"key": f"doc-{i}", "prompt": f"document {i}"} for i in range(n)]})
    assert r.status_code == 202, r.text
    job = db_session.execute(select(AIJob).where(AIJob.job_key == key)).scalar_one()
    return key, job, a, pol


def _sse(client, url, headers):
    events = []
    with client.stream("GET", url, headers=headers) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        ev = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                events.append((ev, json.loads(line[6:])))
                if ev == "end":
                    break
    return events


# ---------------------------------------------------------------- SSE progress
def test_sse_streams_progress_until_terminal(client: TestClient, db_session, register_org, no_background, monkeypatch) -> None:
    org = register_org()
    key, job, a, _ = _run_job(client, db_session, org, n=3)
    ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: Scripted(lambda n: (200, ok_body(f"f{n}"))).adapter()})
    events = _sse(client, f"{B}/jobs/{key}/events", org["headers"])
    kinds = [e for e, _ in events]
    assert kinds[0] == "progress" and kinds[-1] == "end"
    progress = events[0][1]
    assert progress["status"] == "completed" and progress["completed"] == 3 and progress["pending"] == 0
    assert events[-1][1]["status"] == "completed"


def test_sse_reports_cancellation(client: TestClient, db_session, register_org, no_background) -> None:
    org = register_org()
    key, job, _, _ = _run_job(client, db_session, org, n=2)
    r = client.post(f"{B}/jobs/{key}/control", headers=org["headers"], json={"action": "cancel"})
    assert r.status_code == 202, r.text
    events = _sse(client, f"{B}/jobs/{key}/events", org["headers"])
    assert events[0][1]["status"] == "cancelled" and events[-1] == ("end", {"status": "cancelled"})


def test_sse_is_authenticated_and_tenant_scoped(client: TestClient, db_session, register_org, no_background) -> None:
    a, b = register_org(), register_org()
    key, _, _, _ = _run_job(client, db_session, a, n=1)
    assert client.get(f"{B}/jobs/{key}/events").status_code == 401
    assert client.get(f"{B}/jobs/{key}/events", headers=b["headers"]).status_code == 404


# ---------------------------------------------------------------- memory export
def test_memory_export_is_complete_and_audited(client: TestClient, db_session, register_org, no_background) -> None:
    org = register_org()
    key, job, a, _ = _run_job(client, db_session, org, n=2)
    ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: Scripted(lambda n: (200, ok_body(f"f{n}"))).adapter()})
    client.post("/api/v1/agent-network/memory-profiles", headers=org["headers"], json={"name": "Research Memory"})
    r = client.get(f"{B}/memory/export", headers=org["headers"])
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
    doc = r.json()
    assert doc["format"] == "aiol-memory-export/1" and doc["canonical_store"] == "postgresql"
    assert {m["job_key"] for m in doc["working_memory"]} == {key} and any(m["kind"] == "intermediate_finding" for m in doc["working_memory"])
    assert [p["name"] for p in doc["memory_profiles"]] == ["Research Memory"]
    only = client.get(f"{B}/memory/export?job_key=nope", headers=org["headers"]).json()
    assert only["working_memory"] == []
    assert db_session.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'ai_memory.export' AND organization_id = :o"),
                              {"o": str(org["organization"]["id"])}).scalar_one() == 2


def test_memory_export_is_tenant_isolated_and_admin_only(client: TestClient, db_session, register_org, no_background) -> None:
    a, b = register_org(), register_org()
    key, job, acc, _ = _run_job(client, db_session, a, n=1)
    ai_job_service.run_job(db_session, job, adapters={acct(db_session, acc).id: Scripted(lambda n: (200, ok_body("secret finding"))).adapter()})
    doc_b = client.get(f"{B}/memory/export", headers=b["headers"]).json()
    assert doc_b["working_memory"] == [] and doc_b["organization_id"] == str(b["organization"]["id"])
    assert "secret finding" not in json.dumps(doc_b)
    u = client.post("/api/v1/users", headers=a["headers"], json={"email": f"v{uuid.uuid4().hex[:6]}@x.example", "name": "V",
                    "password": "viewer-pass-12345", "role": "viewer"}).json()
    tok = client.post("/api/v1/auth/login", data={"username": u["email"], "password": "viewer-pass-12345"}).json()["access_token"]
    assert client.get(f"{B}/memory/export", headers={"Authorization": f"Bearer {tok}"}).status_code == 403
    assert client.get(f"{B}/memory/export").status_code == 401


# ---------------------------------------------------------------- full-text acquisition
OA = "https://europepmc.org/articles/PMC999"
LONG = ("<html><head><title>Taranjabin trial</title></head><body><h1>Taranjabin in functional constipation</h1>"
        + "".join(f"<p>Section {i}: methods, participants, outcomes and statistical analysis of the randomised trial of taranjabin syrup "
                  f"versus placebo in adults with functional constipation, paragraph {i}.</p>" for i in range(80)) + "</body></html>").encode()
SHORT = b"<html><body><h1>Article</h1><p>Please sign in to read this article.</p></body></html>"


@pytest.fixture()
def oa_source(client, register_org, monkeypatch):
    monkeypatch.setattr(fsvc, "default_providers", lambda transport=None: scholarly.default_providers(httpx.MockTransport(_handler())))
    org = register_org()
    ko, kw = _ko(client, org)
    d = client.post("/api/v1/research/federated/keyword-search", headers=org["headers"], json={
        "knowledge_object_id": ko["id"], "keyword_ids": [kw["Taranjabin"]["id"]], "mode": "single"}).json()
    sid = next(s for s in d["source_ids"] if OA in client.get(f"/api/v1/research/sources/{s}/detail", headers=org["headers"]).json()["open_access_links"])
    return org, sid


def _fake_fetch(content):
    def fetch(url, **kw):
        return url_source.FetchedResource(url=url, final_url=url, content=content, content_type="text/html",
                                          status_code=200, resolved_ip="93.184.216.34")
    return fetch


def test_full_text_is_claimed_only_after_a_real_document(client: TestClient, oa_source, monkeypatch) -> None:
    org, sid = oa_source
    monkeypatch.setattr(url_source, "fetch_url", _fake_fetch(LONG))
    r = client.post(f"/api/v1/research/sources/{sid}/acquire-full-text", headers=org["headers"], json={"url": OA}).json()
    assert r["acquired"] is True and r["converted_bytes"] >= fsvc.FULL_TEXT_MIN_BYTES
    d = client.get(f"/api/v1/research/sources/{sid}/detail", headers=org["headers"]).json()
    assert d["content_access"] == "full_text_available" and d["full_text_accessed"] and "full_text" in d["what_was_accessed"]
    assert d["message"] is None and d["full_text_status"].startswith("available and read by the system")
    assert d["full_text_origin"] == "open_access_fetch"


def test_a_landing_page_is_not_full_text(client: TestClient, oa_source, monkeypatch) -> None:
    org, sid = oa_source
    monkeypatch.setattr(url_source, "fetch_url", _fake_fetch(SHORT))
    r = client.post(f"/api/v1/research/sources/{sid}/acquire-full-text", headers=org["headers"], json={"url": OA}).json()
    assert r["acquired"] is False and "too short" in r["reason"]
    d = client.get(f"/api/v1/research/sources/{sid}/detail", headers=org["headers"]).json()
    assert d["content_access"] == "abstract_only" and not d["full_text_accessed"]


def test_acquisition_only_from_recorded_open_access_locations(client: TestClient, oa_source) -> None:
    org, sid = oa_source
    for bad in ("http://169.254.169.254/latest/meta-data/", "https://evil.example/paper.pdf", "file:///etc/passwd"):
        r = client.post(f"/api/v1/research/sources/{sid}/acquire-full-text", headers=org["headers"], json={"url": bad})
        assert r.status_code == 422, bad


def test_acquisition_passes_through_the_ssrf_guard(client: TestClient, oa_source, monkeypatch) -> None:
    org, sid = oa_source
    def blocked(url, **kw):
        raise url_source.UrlRejected("resolves to a private address")
    monkeypatch.setattr(url_source, "fetch_url", blocked)
    r = client.post(f"/api/v1/research/sources/{sid}/acquire-full-text", headers=org["headers"], json={"url": OA}).json()
    assert r["acquired"] is False and r["reason"].startswith("blocked") and r["content_access"] == "abstract_only"


def test_acquisition_is_tenant_scoped(client: TestClient, oa_source, register_org) -> None:
    _, sid = oa_source
    other = register_org()
    assert client.post(f"/api/v1/research/sources/{sid}/acquire-full-text", headers=other["headers"], json={"url": OA}).status_code == 404


# ---------------------------------------------------------------- user-supplied full text (ADR-107)
LONG_PDF_TEXT = ("Taranjabin in functional constipation: a randomised controlled trial. " * 40 +
                 "Methods: adults received taranjabin syrup or placebo for four weeks. " * 40).encode()


def _upload(client, org, source_id, data, name="article.txt"):
    r = client.post("/api/v1/documents/upload", headers=org["headers"],
                    files={"file": (name, data, "text/plain")},
                    data={"source_id": str(source_id), "title": "Uploaded article", "enable_ocr": "false"})
    assert r.status_code == 202, r.text
    doc_id = r.json()["document_id"]
    from app.services import ingestion_service
    from app.models.document_artifact import DocumentConversion
    from sqlalchemy import select as _select
    return doc_id


def test_user_uploaded_full_text_is_attached_with_provenance(client: TestClient, oa_source, db_session) -> None:
    org, sid = oa_source
    before = client.get(f"/api/v1/research/sources/{sid}/detail", headers=org["headers"]).json()
    assert before["content_access"] == "abstract_only" and not before["full_text_accessed"]
    doc_id = _upload(client, org, sid, LONG_PDF_TEXT)
    from app.models.document_artifact import DocumentConversion
    from sqlalchemy import select as _select
    conv = db_session.execute(_select(DocumentConversion).where(DocumentConversion.document_id == uuid.UUID(doc_id))).scalars().first()
    from app.services import ingestion_service
    ingestion_service.process_pending_conversion(db_session, organization_id=uuid.UUID(str(org["organization"]["id"])),
                                                 document_id=uuid.UUID(doc_id), conversion_id=conv.id, enable_ocr=False)
    r = client.post(f"/api/v1/research/sources/{sid}/attach-full-text", headers=org["headers"], json={"document_id": doc_id}).json()
    assert r["attached"] is True and r["full_text_origin"] == "user_upload"
    d = client.get(f"/api/v1/research/sources/{sid}/detail", headers=org["headers"]).json()
    assert d["content_access"] == "full_text_available" and d["full_text_accessed"]
    assert d["full_text_origin"] == "user_upload" and d["full_text_document_id"] == doc_id
    assert "uploaded by a person" in d["full_text_status"] and d["message"] is None
    assert d["access_history"] and d["access_history"][0]["was"] == "abstract_only"      # earlier state preserved
    assert db_session.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'source.full_text_attached'")).scalar_one() == 1


def test_an_unparsed_or_tiny_upload_claims_nothing(client: TestClient, oa_source, db_session) -> None:
    org, sid = oa_source
    doc_id = _upload(client, org, sid, LONG_PDF_TEXT)                       # never processed
    r = client.post(f"/api/v1/research/sources/{sid}/attach-full-text", headers=org["headers"], json={"document_id": doc_id}).json()
    assert r["attached"] is False and "not been parsed" in r["reason"]
    tiny = _upload(client, org, sid, b"one line", name="tiny.txt")
    from app.models.document_artifact import DocumentConversion
    from sqlalchemy import select as _select
    conv = db_session.execute(_select(DocumentConversion).where(DocumentConversion.document_id == uuid.UUID(tiny))).scalars().first()
    from app.services import ingestion_service
    ingestion_service.process_pending_conversion(db_session, organization_id=uuid.UUID(str(org["organization"]["id"])),
                                                 document_id=uuid.UUID(tiny), conversion_id=conv.id, enable_ocr=False)
    r2 = client.post(f"/api/v1/research/sources/{sid}/attach-full-text", headers=org["headers"], json={"document_id": tiny}).json()
    assert r2["attached"] is False and "too little text" in r2["reason"]
    assert client.get(f"/api/v1/research/sources/{sid}/detail", headers=org["headers"]).json()["content_access"] == "abstract_only"


def test_a_document_of_another_source_or_tenant_is_refused(client: TestClient, oa_source, register_org) -> None:
    org, sid = oa_source
    other_source = client.post("/api/v1/sources", headers=org["headers"],
                               json={"title": "Other paper", "source_type": "scientific_paper"}).json()
    doc_id = _upload(client, org, other_source["id"], LONG_PDF_TEXT)
    assert client.post(f"/api/v1/research/sources/{sid}/attach-full-text", headers=org["headers"],
                       json={"document_id": doc_id}).status_code == 422
    other_tenant = register_org()
    assert client.post(f"/api/v1/research/sources/{sid}/attach-full-text", headers=other_tenant["headers"],
                       json={"document_id": doc_id}).status_code == 404


def test_access_states_can_be_recorded_but_never_claim_full_text(client: TestClient, oa_source) -> None:
    org, sid = oa_source
    for state in ("title_only", "paywalled", "registration_required", "access_blocked", "landing_page_only"):
        r = client.post(f"/api/v1/research/sources/{sid}/access-state", headers=org["headers"],
                        json={"state": state, "reason": "checked by hand"}).json()
        assert r["content_access"] == state and r["checked_at"]
    assert client.post(f"/api/v1/research/sources/{sid}/access-state", headers=org["headers"],
                       json={"state": "full_text_available"}).status_code == 422
    d = client.get(f"/api/v1/research/sources/{sid}/detail", headers=org["headers"]).json()
    assert not d["full_text_accessed"] and d["message"] == fsvc.NOT_REVIEWED_MESSAGE


def test_the_database_refuses_full_text_without_an_origin(client: TestClient, oa_source, db_session) -> None:
    org, sid = oa_source
    with pytest.raises(exc.IntegrityError, match="full_text_origin_required"):
        db_session.execute(text("UPDATE sources SET full_text_accessed = true, content_access = 'full_text_available' WHERE id = :i"), {"i": sid})
        db_session.flush()
    db_session.rollback()
