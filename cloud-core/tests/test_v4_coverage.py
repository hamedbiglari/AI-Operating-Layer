"""v4 coverage-audit repairs (§36, §37): extracted documents are counted, the publication dimension reads
the publication layer, and a data change after an audit is reported as such — never as a fresh audit."""
from __future__ import annotations

from sqlalchemy import text

from tests.test_v4_document_intelligence import FIX, _source, _upload
from tests.pdf_writer import two_column_paper

K = "/api/v1/knowledge"


def _topic_with_document(client, h, db_session, pdf=None):
    src = _source(client, h)
    body = _upload(client, h, "paper.pdf", pdf or two_column_paper(1)[0], src, db_session)
    ko = client.post(K, headers=h, json={"canonical_name": "Taranjabin", "object_type": "plant"}).json()
    ent = client.post("/api/v1/entities", headers=h, json={"knowledge_object_id": ko["id"], "entity_type": "plant",
                                                            "canonical_name": "Taranjabin"}).json()
    claim = client.post("/api/v1/claims", headers=h, json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"],
                                                           "predicate": "contains", "object_value": "mannitol"}).json()
    ev = client.post("/api/v1/evidence", headers=h, json={"source_id": src, "document_id": body["document_id"],
                                                          "summary": "42.1 g per 100 g"}).json()
    db_session.execute(text("UPDATE evidence SET status = 'verified' WHERE id = :i"), {"i": ev["id"]})
    db_session.flush()
    db_session.expire_all()
    client.post("/api/v1/claim-evidence", headers=h, json={"claim_id": claim["id"], "evidence_id": ev["id"],
                                                           "relation": "supports"})
    return ko, claim, body


def test_an_extracted_document_is_counted_as_extracted(client, register_org, db_session):
    """Regression: the processing dimension counted 'succeeded'/'completed', which no document ever has
    (they are stored 'extracted'), so every processed topic reported 0 %."""
    h = register_org()["headers"]
    ko, _, _ = _topic_with_document(client, h, db_session)
    p = client.post(f"{K}/{ko['id']}/coverage/run", headers=h).json()["dimensions"]["processing"]
    assert p["documents"] == 1 and p["extracted"] == 1 and p["percent_extracted"] == 100.0
    s = p["structure"]
    assert s["documents_with_canonical_representation"] == 1 and s["without_canonical_representation"] == 0
    assert s["elements_by_type"]["table"] == 1 and s["needs_review"] == 1     # the equation candidate flags it


def test_publication_dimension_reads_the_publication_layer(client, register_org, db_session):
    h = register_org()["headers"]
    ko, claim, _ = _topic_with_document(client, h, db_session)
    pub = client.post("/api/v1/publications", headers=h, json={"knowledge_object_id": ko["id"]}).json()
    client.post(f"/api/v1/publications/{pub['id']}/sentences", headers=h,
                json={"text": "Taranjabin contains mannitol.", "claim_id": claim["id"]})
    client.post(f"/api/v1/publications/{pub['id']}/sentences", headers=h, json={"text": "An unsupported fact."})
    client.post(f"/api/v1/publications/{pub['id']}/resolve", headers=h)
    d = client.post(f"{K}/{ko['id']}/coverage/run", headers=h).json()["dimensions"]["publication"]
    assert d["publication_version"] == 1 and d["citation_required_sentences"] == 2
    assert d["sentences_with_citations"] == 1 and d["sentences_marked_evidence_unavailable"] == 1
    assert d["citation_coverage"] == 50.0 and "no publication" not in d["note"].lower()


def test_last_data_update_and_last_verified_audit_are_separate(client, register_org, db_session):
    h = register_org()["headers"]
    ko, claim, _ = _topic_with_document(client, h, db_session)
    client.post(f"{K}/{ko['id']}/coverage/run", headers=h)
    view = client.get(f"{K}/{ko['id']}/coverage", headers=h).json()
    assert view["state"] == "current" and view["freshness"]["data_changed_since_audit"] is False
    assert view["freshness"]["last_data_update"] and view["freshness"]["last_verified_audit"]
    # a source changes after the audit: the audit is not silently treated as covering it
    db_session.execute(text("UPDATE claims SET updated_at = now() + interval '1 minute' WHERE id = :i"), {"i": claim["id"]})
    db_session.flush()
    view = client.get(f"{K}/{ko['id']}/coverage", headers=h).json()
    assert view["state"] == "outdated" and view["freshness"]["data_changed_since_audit"] is True
    assert "not as it is now" in view["message"]
