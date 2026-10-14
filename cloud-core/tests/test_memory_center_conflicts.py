"""Memory Center (§9), extraction confidence vs evidence strength (§19), conflict intelligence (§21) — ADR-110."""
import csv
import io
import json
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import exc, text

from app.services import ai_memory_service as mem

M = "/api/v1/memory"
C = "/api/v1/evidence-conflicts"


def _org_id(org):
    return uuid.UUID(str(org["organization"]["id"]))


def _write(db, org, job_key, kind, content, by="tester"):
    return mem.write(db, organization_id=_org_id(org), job_key=job_key, kind=kind, content=content,
                     created_by=by, commit=False)


def _seed(db, org):
    _write(db, org, "job-a", "intermediate_finding", {"finding": "mannitol is osmotic", "n": 1})
    _write(db, org, "job-a", "intermediate_finding", {"finding": "mannitol is osmotic", "n": 2, "extra": "added"})
    _write(db, org, "job-a", "ai_handoff", {"goal": "research taranjabin"})
    _write(db, org, "job-b", "open_question", {"question": "is it safe for children"})
    db.flush()


# ---------------------------------------------------------------- §9 search / filter / versions / compare
def test_search_filter_and_sort(client: TestClient, db_session, register_org) -> None:
    org = register_org()
    _seed(db_session, org)
    all_items = client.get(f"{M}/search?limit=50", headers=org["headers"]).json()
    assert all_items["total"] == 4
    assert client.get(f"{M}/search?kind=intermediate_finding", headers=org["headers"]).json()["total"] == 2
    assert client.get(f"{M}/search?job_key=job-b", headers=org["headers"]).json()["total"] == 1
    assert client.get(f"{M}/search?q=children", headers=org["headers"]).json()["total"] == 1      # searches the content
    assert client.get(f"{M}/search?q=MANNITOL", headers=org["headers"]).json()["total"] == 2      # case-insensitive
    latest = client.get(f"{M}/search?latest_only=true&limit=50", headers=org["headers"]).json()
    assert latest["total"] == 3 and all(i["version"] >= 1 for i in latest["items"])
    asc = client.get(f"{M}/search?sort=version&direction=asc&kind=intermediate_finding", headers=org["headers"]).json()
    assert [i["version"] for i in asc["items"]] == [1, 2]
    assert client.get(f"{M}/search?kind=not_a_kind", headers=org["headers"]).status_code == 422
    first = all_items["items"][0]
    assert {"created_by", "created_at", "content_hash", "provenance"} <= set(first)                # provenance


def test_versions_and_compare(client: TestClient, db_session, register_org) -> None:
    org = register_org()
    _seed(db_session, org)
    vs = client.get(f"{M}/items/job-a/intermediate_finding/versions", headers=org["headers"]).json()
    assert [v["version"] for v in vs] == [1, 2]
    d = client.get(f"{M}/items/job-a/intermediate_finding/compare?left=1&right=2", headers=org["headers"]).json()
    assert d["identical"] is False and set(d["changed_keys"]) == {"n", "extra"}
    changes = {x["key"]: x["change"] for x in d["diff"]}
    assert changes == {"finding": "unchanged", "n": "changed", "extra": "added"}
    assert client.get(f"{M}/items/job-a/intermediate_finding/compare?left=1&right=9", headers=org["headers"]).status_code == 404
    assert client.get(f"{M}/items/nope/ai_handoff/versions", headers=org["headers"]).status_code == 404


# ---------------------------------------------------------------- §9 export
def test_export_in_every_format(client: TestClient, db_session, register_org) -> None:
    org = register_org()
    _seed(db_session, org)
    j = client.get(f"{M}/export.json", headers=org["headers"])
    assert j.status_code == 200 and j.headers["cache-control"] == "no-store" and "attachment" in j.headers["content-disposition"]
    doc = j.json()
    assert doc["format"] == "aiol-memory-export/2" and doc["counts"]["working_memory"] == 4
    assert doc["canonical_store"] == "postgresql" and len(doc["working_memory"]) == 4
    l = client.get(f"{M}/export.jsonl", headers=org["headers"])
    records = [json.loads(x) for x in l.text.strip().split("\n")]
    assert records[0]["record"] == "meta" and sum(1 for r in records if r["record"] == "working_memory") == 4
    c = client.get(f"{M}/export.csv", headers=org["headers"])
    rows = list(csv.DictReader(io.StringIO(c.text)))
    assert len(rows) == 4 and "content" in rows[0] and json.loads(rows[0]["content"])
    z = client.get(f"{M}/export.zip", headers=org["headers"])
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    assert set(zf.namelist()) == {"manifest.json", "working_memory.json", "memory_profiles.json",
                                  "agent_handoffs.json", "working_memory.csv", "memory.md", "README.txt"}
    assert len(json.loads(zf.read("working_memory.json"))) == 4
    assert client.get(f"{M}/export.pdf", headers=org["headers"]).status_code == 422


def test_export_scope_and_audit(client: TestClient, db_session, register_org) -> None:
    org = register_org()
    _seed(db_session, org)
    scoped = client.get(f"{M}/export.json?job_key=job-b", headers=org["headers"]).json()
    assert scoped["counts"]["working_memory"] == 1 and scoped["scope"]["job_key"] == "job-b"
    kind = client.get(f"{M}/export.json?kind=ai_handoff", headers=org["headers"]).json()
    assert kind["counts"]["working_memory"] == 1
    n = db_session.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'ai_memory.export' AND organization_id = :o"),
                           {"o": str(org["organization"]["id"])}).scalar_one()
    assert n == 2


def test_memory_is_tenant_isolated_and_export_is_admin_only(client: TestClient, db_session, register_org) -> None:
    a, b = register_org(), register_org()
    _seed(db_session, a)
    assert client.get(f"{M}/search?limit=50", headers=b["headers"]).json()["total"] == 0
    assert client.get(f"{M}/items/job-a/intermediate_finding/versions", headers=b["headers"]).status_code == 404
    doc_b = client.get(f"{M}/export.json", headers=b["headers"]).json()
    assert doc_b["counts"]["working_memory"] == 0 and "mannitol" not in json.dumps(doc_b).lower()
    u = client.post("/api/v1/users", headers=a["headers"], json={"email": f"v{uuid.uuid4().hex[:6]}@x.example",
                    "name": "V", "password": "viewer-pass-12345", "role": "viewer"}).json()
    tok = client.post("/api/v1/auth/login", data={"username": u["email"], "password": "viewer-pass-12345"}).json()["access_token"]
    vh = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"{M}/search", headers=vh).status_code == 200            # a viewer may look
    assert client.get(f"{M}/export.json", headers=vh).status_code == 403       # but not export
    assert client.get(f"{M}/search").status_code == 401


# ---------------------------------------------------------------- §19 extraction confidence
def test_extraction_confidence_is_separate_from_evidence_strength(client: TestClient, db_session, register_org) -> None:
    org = register_org()
    src = client.post("/api/v1/sources", headers=org["headers"],
                      json={"title": "A trial", "source_type": "scientific_paper"}).json()
    ev = client.post("/api/v1/evidence", headers=org["headers"],
                     json={"source_id": src["id"], "summary": "The abstract reports a laxative effect.",
                           "directness": "direct", "evidence_strength": "moderate"}).json()
    # a strong finding read with low confidence, and the reverse, are both expressible
    db_session.execute(text("UPDATE evidence SET extraction_confidence = 0.4, extraction_note = 'wording is ambiguous' WHERE id = :i"),
                       {"i": ev["id"]})
    db_session.flush()
    row = db_session.execute(text("SELECT evidence_strength, extraction_confidence FROM evidence WHERE id = :i"), {"i": ev["id"]}).one()
    assert str(row[0]) == "moderate" and float(row[1]) == 0.4
    for bad in (-0.1, 1.5):
        with pytest.raises(exc.IntegrityError, match="extraction_confidence_range"):
            db_session.execute(text("UPDATE evidence SET extraction_confidence = :c WHERE id = :i"), {"c": bad, "i": ev["id"]})
            db_session.flush()
        db_session.rollback()


def test_a_machine_extraction_cannot_claim_certainty(client: TestClient, db_session, register_org) -> None:
    org = register_org()
    src = client.post("/api/v1/sources", headers=org["headers"],
                      json={"title": "A trial", "source_type": "scientific_paper"}).json()
    ev = client.post("/api/v1/evidence", headers=org["headers"],
                     json={"source_id": src["id"], "summary": "Machine reading.", "directness": "indirect",
                           "evidence_strength": "low"}).json()
    db_session.execute(text("UPDATE evidence SET source_generated = true, human_reviewed = false WHERE id = :i"), {"i": ev["id"]})
    db_session.flush()
    with pytest.raises(exc.IntegrityError, match="machine_extraction_is_not_certain"):
        db_session.execute(text("UPDATE evidence SET extraction_confidence = 1.0 WHERE id = :i"), {"i": ev["id"]})
        db_session.flush()
    db_session.rollback()
    db_session.execute(text("UPDATE evidence SET human_reviewed = true, extraction_confidence = 1.0 WHERE id = :i"), {"i": ev["id"]})
    db_session.flush()                                                         # after human review it is allowed


# ---------------------------------------------------------------- §21 conflicts
def _conflicting_claim(client, org):
    ko = client.post("/api/v1/knowledge", headers=org["headers"],
                     json={"canonical_name": f"KO-{uuid.uuid4().hex[:6]}", "object_type": "ingredient"}).json()
    ent = client.post("/api/v1/entities", headers=org["headers"],
                      json={"knowledge_object_id": ko["id"], "entity_type": "ingredient", "canonical_name": "X"}).json()
    claim = client.post("/api/v1/claims", headers=org["headers"],
                        json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"], "predicate": "relieves",
                              "object_value": "constipation", "claim_type": "efficacy"}).json()
    evs = []
    for i, (strength, pop) in enumerate((("high", "adults"), ("low", "children"))):
        s = client.post("/api/v1/sources", headers=org["headers"],
                        json={"title": f"Study {i}", "source_type": "scientific_paper"}).json()
        e = client.post("/api/v1/evidence", headers=org["headers"],
                        json={"source_id": s["id"], "summary": f"Study {i}", "directness": "direct",
                              "evidence_strength": strength, "population": pop}).json()
        evs.append(e)
    for e, rel in ((evs[0], "supports"), (evs[1], "contradicts")):
        r = client.post("/api/v1/claim-evidence", headers=org["headers"],
                        json={"claim_id": claim["id"], "evidence_id": e["id"], "relation": rel})
        assert r.status_code in (200, 201), r.text
    return ko, claim, evs


def test_a_conflict_is_recorded_with_its_comparison(client: TestClient, register_org) -> None:
    org = register_org()
    ko, claim, evs = _conflicting_claim(client, org)
    d = client.post(f"{C}/detect/{claim['id']}", headers=org["headers"])
    assert d.status_code == 201 and d.json()["created"] == 1
    c = d.json()["conflicts"][0]
    assert c["status"] == "unreviewed" and "does not choose" in c["note"]
    assert c["comparison"]["supporting"]["population"] == "adults"
    assert c["comparison"]["contradicting"]["population"] == "children"
    assert "population" in c["comparison"]["differs_on"]
    assert "dose" in c["comparison"]["not_recorded"]                 # honest about what is unknown
    assert client.post(f"{C}/detect/{claim['id']}", headers=org["headers"]).json()["created"] == 0   # idempotent
    listed = client.get(f"{C}?status=unreviewed", headers=org["headers"]).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == c["id"]
    assert client.get(f"{C}?knowledge_object_id={ko['id']}", headers=org["headers"]).json()["total"] == 1


def test_resolving_a_conflict_needs_a_reason(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    _, claim, _ = _conflicting_claim(client, org)
    cid = client.post(f"{C}/detect/{claim['id']}", headers=org["headers"]).json()["conflicts"][0]["id"]
    assert client.post(f"{C}/{cid}/review", headers=org["headers"], json={"status": "resolved"}).status_code == 422
    ok = client.post(f"{C}/{cid}/review", headers=org["headers"],
                     json={"status": "resolved", "note": "different populations; both findings stand for their own group"}).json()
    assert ok["status"] == "resolved" and ok["reviewed_at"] and "different populations" in ok["resolution_note"]
    assert db_session.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'evidence_conflict.reviewed'")).scalar_one() == 1
    with pytest.raises(exc.IntegrityError, match="a_decision_needs_a_reason"):
        db_session.execute(text("UPDATE evidence_conflicts SET status = 'unresolvable', resolution_note = NULL WHERE id = :i"), {"i": cid})
        db_session.flush()
    db_session.rollback()
    assert client.post(f"{C}/{cid}/review", headers=org["headers"], json={"status": "under_review"}).status_code == 200


def test_conflicts_are_tenant_isolated(client: TestClient, register_org) -> None:
    a, b = register_org(), register_org()
    _, claim, _ = _conflicting_claim(client, a)
    cid = client.post(f"{C}/detect/{claim['id']}", headers=a["headers"]).json()["conflicts"][0]["id"]
    assert client.get(C, headers=b["headers"]).json()["total"] == 0
    assert client.post(f"{C}/detect/{claim['id']}", headers=b["headers"]).status_code == 404
    assert client.post(f"{C}/{cid}/review", headers=b["headers"], json={"status": "under_review"}).status_code == 404


def test_markdown_export_is_readable_and_carries_provenance(client: TestClient, db_session, register_org) -> None:
    """§7/§22: memory exports as readable Markdown — a representation, with the canonical store named, every record
    present with its provenance, and no credential in the body."""
    org = register_org()
    _seed(db_session, org)
    r = client.get(f"{M}/export.md", headers=org["headers"])
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers["content-disposition"] and r.headers["content-disposition"].endswith('.md"')
    md = r.text
    assert md.startswith("# AI Operating Layer — memory export")
    # it says what it is: a readable representation, not the store
    assert "postgresql" in md and "not the store itself" in md
    # every section and every seeded record is present
    for heading in ("## Working memory", "## Memory profiles", "## Agent handoffs"):
        assert heading in md
    assert md.count("### ") >= 4 and "job-a" in md
    # provenance and versions are carried, and nothing secret is
    assert "**Record id**" in md and "**Created**" in md and "v1" in md
    # the disclaimer names those words, so check for a real credential value instead
    body = md.split("> No credential", 1)[1]
    assert "sk-" not in body and "aiol_dev_pw" not in body and "Bearer " not in body
    # the zip carries the same Markdown
    z = client.get(f"{M}/export.zip", headers=org["headers"])
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    assert zf.read("memory.md").decode().startswith("# AI Operating Layer")


def test_markdown_export_is_admin_only_and_tenant_isolated(client: TestClient, db_session, register_org) -> None:
    a, b = register_org(), register_org()
    _seed(db_session, a)
    assert client.get(f"{M}/export.md").status_code in (401, 403)
    other = client.get(f"{M}/export.md", headers=b["headers"])
    assert other.status_code == 200 and "job-a" not in other.text
