"""
§43 — the whole workflow on one scientific example, through the production code path.

Taranjabin / ترنجبین / Alhagi maurorum. Provider responses are the documented-format fixtures from
tests/test_federated_research.py (the live hosts are blocked in this sandbox); everything else — the
services, the database constraints, the review gates — is the real code. No scientific conclusion is
invented here: the test asserts how the system *handles* evidence, not what the evidence says.
"""
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.integrations.research import scholarly
from app.services import federated_research_service as fsvc
from app.services import ingestion_service
from tests.test_federated_research import _handler

R = "/api/v1/research"
FULL_TEXT = ("Taranjabin in functional constipation: a randomised controlled trial. "
             "Adults received taranjabin syrup or placebo for four weeks; stool frequency increased. " * 45).encode()


@pytest.fixture()
def providers(monkeypatch):
    monkeypatch.setattr(fsvc, "default_providers", lambda transport=None: scholarly.default_providers(httpx.MockTransport(_handler())))


def test_the_whole_taranjabin_workflow(client: TestClient, register_org, providers, db_session) -> None:
    org = register_org()
    h = org["headers"]
    org_id = str(org["organization"]["id"])

    # 1. keyword cluster ------------------------------------------------------------------
    ko = client.post("/api/v1/knowledge", headers=h,
                     json={"canonical_name": "Taranjabin", "object_type": "ingredient"}).json()
    kws = [{"keyword": "Taranjabin", "type": "primary"}, {"keyword": "ترنجبین", "type": "language_variant"},
           {"keyword": "Persian manna", "type": "common_name"}, {"keyword": "Alhagi maurorum", "type": "scientific_name"},
           {"keyword": "Alhagi manna", "type": "synonym"}, {"keyword": "mannitol", "type": "compound"},
           {"keyword": "fructose", "type": "compound"}, {"keyword": "laxative", "type": "clinical_outcome"},
           {"keyword": "Alhagi persarum", "type": "related_entity"}]
    assert client.post(f"/api/v1/knowledge/{ko['id']}/keywords", headers=h, json=kws).status_code in (200, 201)
    by_word = {k["keyword"]: k for k in client.get(f"/api/v1/knowledge/{ko['id']}/keywords?limit=50", headers=h).json()["items"]}
    qs = client.post(f"{R}/query-sets", headers=h, json={
        "knowledge_object_id": ko["id"], "name": "Taranjabin laxative evidence", "mode": "agent",
        "keyword_ids": [by_word["Taranjabin"]["id"], by_word["laxative"]["id"]]})
    assert qs.status_code == 201, qs.text

    # 2–3. discovery and deduplication ----------------------------------------------------
    run = client.post(f"{R}/query-sets/{qs.json()['id']}/run", headers=h).json()["run"]
    assert run["unique_sources"] >= 3 and run["merged_duplicates"] >= 1          # DOI / PMID / title merges
    again = client.post(f"{R}/query-sets/{qs.json()['id']}/run", headers=h).json()["run"]
    assert again["new_sources"] == 0

    # 4–5. abstract-only and title-only states, recorded honestly --------------------------
    details = {sid: client.get(f"{R}/sources/{sid}/detail", headers=h).json() for sid in run["source_ids"]}
    assert any(d["content_access"] == "abstract_only" for d in details.values())
    assert any(d["content_access"] == "metadata_only" for d in details.values())
    assert all(not d["full_text_accessed"] for d in details.values())
    paywalled = list(details)[0]
    client.post(f"{R}/sources/{paywalled}/access-state", headers=h,
                json={"state": "title_only", "reason": "publisher page shows the title only"})
    assert client.get(f"{R}/sources/{paywalled}/detail", headers=h).json()["content_access"] == "title_only"

    # 6–8. the user obtains the article legally and uploads it ----------------------------
    trial = next(sid for sid, d in details.items() if d["pmid"] == "222")
    assert client.get(f"{R}/sources/{trial}/detail", headers=h).json()["open_access_links"]     # a legitimate location
    up = client.post("/api/v1/documents/upload", headers=h, files={"file": ("trial.txt", FULL_TEXT, "text/plain")},
                     data={"source_id": trial, "title": "Taranjabin trial", "enable_ocr": "false"})
    assert up.status_code == 202, up.text
    doc_id = up.json()["document_id"]
    from app.models.document_artifact import DocumentConversion
    from sqlalchemy import select as _select
    conv = db_session.execute(_select(DocumentConversion).where(DocumentConversion.document_id == uuid.UUID(doc_id))).scalars().first()
    ingestion_service.process_pending_conversion(db_session, organization_id=uuid.UUID(org_id),
                                                 document_id=uuid.UUID(doc_id), conversion_id=conv.id, enable_ocr=False)
    attached = client.post(f"{R}/sources/{trial}/attach-full-text", headers=h, json={"document_id": doc_id}).json()
    assert attached["attached"] is True and attached["full_text_origin"] == "user_upload"
    d = client.get(f"{R}/sources/{trial}/detail", headers=h).json()
    assert d["content_access"] == "full_text_available" and d["access_history"]     # 11. earlier provenance kept

    # 9–10. a question, its routes, and candidates that only a person may verify -----------
    q = client.post(f"{R}/questions", headers=h, json={
        "knowledge_object_id": ko["id"], "subject": "Taranjabin", "compounds": ["Mannitol", "Fructose"],
        "related_species": ["Alhagi persarum"], "outcome": "laxative", "population": "human"}).json()
    qid = q["research_question_id"]
    assert {"direct_subject", "compound_human", "combination", "indirect_analogous_species"} <= set(q["routes"])
    ex = client.post(f"{R}/questions/{qid}/extract-candidates", headers=h).json()
    assert ex["status"] == "pending_review" and ex["created_candidates"] > 0
    m = client.get(f"{R}/questions/{qid}/evidence-map", headers=h).json()
    assert all(c["directness"] == "indirect" for c in m["awaiting_review"] if c["route"] != "direct_subject")

    # 12–14. review: direct only for the subject, compound evidence stays indirect ---------
    direct = next(c for c in m["awaiting_review"] if c["route"] == "direct_subject")
    r1 = client.post(f"{R}/evidence-candidates/{direct['id']}/review", headers=h,
                     json={"decision": "approve", "subject_tested": "Taranjabin syrup"}).json()
    assert r1["directness"] == "direct"
    compound = next(c for c in m["awaiting_review"] if c["route"] == "compound_human")
    r2 = client.post(f"{R}/evidence-candidates/{compound['id']}/review", headers=h,
                     json={"decision": "approve", "subject_tested": "Mannitol"}).json()
    assert r2["directness"] == "indirect"
    g = client.get(f"{R}/questions/{qid}/evidence-graph", headers=h).json()
    assert g["direct_paths_to_subject"] == 1
    assert any(e["label"] == "studied_in" and e["from"].startswith("compound:") and e["directness"] == "indirect"
               for e in g["edges"])

    # 12. evidence strength and extraction confidence are separate ------------------------
    db_session.execute(text("UPDATE evidence SET extraction_confidence = 0.75, extraction_note = 'abstract wording' "
                            "WHERE id = :i"), {"i": r2["id"]})
    db_session.flush()
    db_session.expire_all()
    row = db_session.execute(text("SELECT evidence_strength, extraction_confidence FROM evidence WHERE id = :i"),
                             {"i": r2["id"]}).one()
    assert row[0] is not None and float(row[1]) == 0.75

    # 15. conflict detection --------------------------------------------------------------
    ent = client.post("/api/v1/entities", headers=h, json={"knowledge_object_id": ko["id"], "entity_type": "ingredient",
                      "canonical_name": "Taranjabin"}).json()
    claim = client.post("/api/v1/claims", headers=h, json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"],
                        "predicate": "relieves", "object_value": "constipation", "claim_type": "efficacy"}).json()
    for eid, rel in ((r1["id"], "supports"), (r2["id"], "contradicts")):
        assert client.post("/api/v1/claim-evidence", headers=h,
                           json={"claim_id": claim["id"], "evidence_id": eid, "relation": rel}).status_code in (200, 201)
    conflicts = client.post(f"/api/v1/evidence-conflicts/detect/{claim['id']}", headers=h).json()
    assert conflicts["created"] == 1 and conflicts["conflicts"][0]["status"] == "unreviewed"

    # 20. source dependency: how many independent findings ---------------------------------
    ids = list(details)
    client.post(f"{R}/sources/{ids[1]}/dependencies", headers=h,
                json={"depends_on_source_id": ids[0], "relation": "reviews"})
    dep = client.get(f"{R}/questions/{qid}/dependency-graph", headers=h).json()
    assert dep["independent_evidence_count"] < dep["sources"]

    # 16–17. a knowledge gap becomes a completion task, and Find More runs -----------------
    gap = client.post("/api/v1/knowledge-gaps", headers=h, json={
        "knowledge_object_id": ko["id"], "gap_type": "evidence_gap",
        "description": "human clinical evidence for Taranjabin is thin", "priority": "high"}).json()
    task = client.post("/api/v1/evidence-completion-tasks", headers=h, json={
        "knowledge_object_id": ko["id"], "knowledge_gap_id": gap["id"], "claim_id": claim["id"],
        "what_is_missing": "a second human trial of Taranjabin itself", "required_route": "direct_subject",
        "required_directness": "direct"}).json()
    assert task["status"] == "open"
    more = client.post(f"{R}/knowledge-gaps/{gap['id']}/find-more", headers=h)
    assert more.status_code == 201
    # the gap is NOT resolved just because related evidence exists
    assert client.get(f"/api/v1/knowledge-gaps/{gap['id']}", headers=h).json()["status"] == "open"

    # 18–19. iterations and an honest stopping condition ------------------------------------
    client.post(f"{R}/questions/{qid}/find-more", headers=h, json={"route": "direct_subject", "extra_terms": ["Alhagi manna"]})
    sat = client.get(f"{R}/questions/{qid}/saturation", headers=h).json()
    assert sat["iterations_run"] >= 5 and sat["reason"] in (
        "duplicate_sources_only", "low_marginal_yield", "query_variants_exhausted", "not_saturated")
    assert "not a claim that the literature has been exhausted" in sat["note"]

    # 20. the knowledge object is updated by a person, never by the research engine ---------
    before = client.get(f"/api/v1/knowledge/{ko['id']}", headers=h).json()
    assert before["version"] == 1                       # untouched by everything above
    updated = client.patch(f"/api/v1/knowledge/{ko['id']}", headers=h,
                           json={"description": "Manna of Alhagi maurorum; one reviewed human trial on file."})
    assert updated.status_code == 200 and updated.json()["version"] == 2
    # and the completion task closes only against the evidence that satisfies it
    bad = client.patch(f"/api/v1/evidence-completion-tasks/{task['id']}", headers=h,
                       json={"status": "satisfied", "satisfied_by_evidence_id": r2["id"]})
    assert bad.status_code == 409                       # the compound finding is indirect
    ok = client.patch(f"/api/v1/evidence-completion-tasks/{task['id']}", headers=h,
                      json={"status": "satisfied", "satisfied_by_evidence_id": r1["id"]})
    assert ok.status_code == 200 and ok.json()["status"] == "satisfied"

    # the chain holds end to end: keyword -> query -> provider -> source -> evidence -> claim -> KO
    chain = client.get(f"{R}/keywords/{by_word['Taranjabin']['id']}/chain", headers=h).json()
    assert chain["complete_to_claim"] is True
