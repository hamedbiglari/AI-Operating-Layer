"""
Sentence-level Vancouver citation (ADR-116). Covers every test the prompt names in §81–§88.

Nothing here asserts on a fixture: each sentence is built from a real claim whose evidence links to a
real source, exactly as the publication engine does it.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import exc, text

from app.services.citation_resolver import citation_text, compress

P = "/api/v1/publications"
K = "/api/v1/knowledge"


# ---------------------------------------------------------------- helpers
def _topic(client, org, name="Taranjabin"):
    return client.post(K, headers=org["headers"], json={"canonical_name": name, "object_type": "plant"}).json()


def _source(client, org, title, **meta):
    body = {"title": title, "source_type": "scientific_paper"}
    body.update(meta)
    r = client.post("/api/v1/sources", headers=org["headers"], json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _claim_with_sources(client, org, db, ko, sources, predicate="contains", value="mannitol"):
    """One claim supported by several verified pieces of evidence, one per source."""
    ent = client.post("/api/v1/entities", headers=org["headers"],
                      json={"knowledge_object_id": ko["id"], "entity_type": "ingredient",
                            "canonical_name": f"E{uuid.uuid4().hex[:5]}"}).json()
    claim = client.post("/api/v1/claims", headers=org["headers"],
                        json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"],
                              "predicate": predicate, "object_value": value, "claim_type": "composition"}).json()
    for src in sources:
        ev = client.post("/api/v1/evidence", headers=org["headers"],
                         json={"source_id": src["id"], "summary": f"Finding from {src['title']}",
                               "directness": "direct", "evidence_strength": "moderate"}).json()
        db.execute(text("UPDATE evidence SET status = 'verified' WHERE id = :i"), {"i": ev["id"]})
        db.flush()
        db.expire_all()
        client.post("/api/v1/claim-evidence", headers=org["headers"],
                    json={"claim_id": claim["id"], "evidence_id": ev["id"], "relation": "supports"})
    return claim


def _publication(client, org, ko):
    return client.post(P, headers=org["headers"], json={"knowledge_object_id": ko["id"]}).json()


def _sentence(client, org, pub, text_, claim=None, kind="factual"):
    body = {"text": text_, "kind": kind}
    if claim:
        body["claim_id"] = claim["id"]
    r = client.post(f"{P}/{pub['id']}/sentences", headers=org["headers"], json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- §81 tests 1–10: numbering
def test_1_first_source_is_number_one(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    s1 = _source(client, org, "Paper A")
    claim = _claim_with_sources(client, org, db_session, ko, [s1])
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "Taranjabin contains mannitol.", claim)
    r = client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"]).json()
    assert r["references"] == 1
    body = client.get(f"{P}/{pub['id']}", headers=org["headers"]).json()
    assert body["body"][0]["sentences"][0]["citation_numbers"] == [1]
    assert body["body"][0]["sentences"][0]["rendered"].endswith("mannitol. (1)")


def test_2_second_new_source_is_number_two(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    a, b = _source(client, org, "Paper A"), _source(client, org, "Paper B")
    c1 = _claim_with_sources(client, org, db_session, ko, [a])
    c2 = _claim_with_sources(client, org, db_session, ko, [b], value="fructose")
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "First statement.", c1)
    _sentence(client, org, pub, "Second statement.", c2)
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    out = client.get(f"{P}/{pub['id']}", headers=org["headers"]).json()["body"][0]["sentences"]
    assert out[0]["citation_numbers"] == [1] and out[1]["citation_numbers"] == [2]


def test_3_and_84_a_repeated_source_reuses_its_number(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    sources = [_source(client, org, f"Paper {i}") for i in range(8)]
    first = _claim_with_sources(client, org, db_session, ko, sources[:7])          # takes numbers 1..7
    seventh_only = _claim_with_sources(client, org, db_session, ko, [sources[6]], value="later")
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "An opening statement.", first)
    for i in range(3):
        _sentence(client, org, pub, f"Filler statement {i}.", None, kind="narrative")
    _sentence(client, org, pub, "A much later statement.", seventh_only)
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    out = client.get(f"{P}/{pub['id']}", headers=org["headers"]).json()["body"][0]["sentences"]
    number_for_seventh = out[-1]["citation_numbers"]
    assert len(number_for_seventh) == 1
    assert number_for_seventh[0] in out[0]["citation_numbers"]        # the same number, not a new one
    assert number_for_seventh[0] <= 7


def test_4_and_82_ten_consecutive_sources_compress_to_a_range(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    sources = [_source(client, org, f"Paper {i}") for i in range(10)]
    claim = _claim_with_sources(client, org, db_session, ko, sources)
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "This finding is reported across ten studies.", claim)
    r = client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"]).json()
    assert r["references"] == 10
    s = client.get(f"{P}/{pub['id']}", headers=org["headers"]).json()["body"][0]["sentences"][0]
    assert s["citation_numbers"] == list(range(1, 11))
    assert s["citation_text"] == "(1–10)"                            # §82, not truncated
    assert s["rendered"].endswith("studies. (1–10)")


def test_5_and_83_non_consecutive_numbers_stay_individual() -> None:
    assert citation_text([1, 3, 5, 8, 11]) == "(1,3,5,8,11)"         # §83
    assert compress([1, 3, 5]) == "1,3,5"                            # never 1–5
    assert compress([1, 2, 3, 7, 8]) == "1–3,7,8"                    # only true runs compress
    assert compress([4, 5]) == "4,5"                                 # a run of two is written out
    assert compress([]) == "" and citation_text([]) == ""


def test_6_and_85_order_is_first_appearance_not_alphabetical(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    c_src = _source(client, org, "Zebra study")      # alphabetically last, cited first
    a_src = _source(client, org, "Alpha study")
    b_src = _source(client, org, "Beta study")
    first = _claim_with_sources(client, org, db_session, ko, [c_src])
    second = _claim_with_sources(client, org, db_session, ko, [a_src], value="two")
    third = _claim_with_sources(client, org, db_session, ko, [b_src], value="three")
    fourth = _claim_with_sources(client, org, db_session, ko, [c_src], value="four")   # C again
    pub = _publication(client, org, ko)
    for i, cl in enumerate((first, second, third, fourth)):
        _sentence(client, org, pub, f"Statement {i}.", cl)
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    refs = client.get(f"{P}/{pub['id']}/references", headers=org["headers"]).json()
    assert [r["number"] for r in refs] == [1, 2, 3]
    assert refs[0]["source_id"] == c_src["id"]       # Zebra is 1 because it was cited first
    assert refs[1]["source_id"] == a_src["id"] and refs[2]["source_id"] == b_src["id"]
    out = client.get(f"{P}/{pub['id']}", headers=org["headers"]).json()["body"][0]["sentences"]
    assert out[3]["citation_numbers"] == [1]        # C keeps number 1


def test_7_reference_list_follows_citation_order(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    sources = [_source(client, org, f"Paper {i}") for i in range(5)]
    claim = _claim_with_sources(client, org, db_session, ko, sources)
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "A statement.", claim)
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    refs = client.get(f"{P}/{pub['id']}/references", headers=org["headers"]).json()
    assert [r["number"] for r in refs] == [1, 2, 3, 4, 5]
    assert all(r["first_cited_at_sentence"] == 0 for r in refs)


def test_8_and_9_no_number_is_shared_and_no_source_is_numbered_twice(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    sources = [_source(client, org, f"Paper {i}") for i in range(4)]
    claim = _claim_with_sources(client, org, db_session, ko, sources)
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "A statement.", claim)
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    audit = client.get(f"{P}/{pub['id']}/citation-audit", headers=org["headers"]).json()
    assert audit["checks"]["no_number_belongs_to_two_sources"]
    assert audit["checks"]["no_source_holds_two_numbers"]
    assert audit["sources_with_more_than_one_number"] == []
    refs = client.get(f"{P}/{pub['id']}/references", headers=org["headers"]).json()
    with pytest.raises(exc.IntegrityError, match="uq_reference_number_per_publication"):
        db_session.execute(text(
            "INSERT INTO publication_references (id, organization_id, publication_id, source_id, reference_number, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :o, :p, :s, 1, now(), now())"),
            {"o": str(org["organization"]["id"]), "p": pub["id"], "s": refs[1]["source_id"]})
        db_session.flush()
    db_session.rollback()


def test_10_every_citation_number_resolves_to_a_source(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    claim = _claim_with_sources(client, org, db_session, ko, [_source(client, org, "Paper A")])
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "A statement.", claim)
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    audit = client.get(f"{P}/{pub['id']}/citation-audit", headers=org["headers"]).json()
    assert audit["dangling_numbers"] == [] and audit["checks"]["no_citation_number_is_dangling"]


# ---------------------------------------------------------------- §81 tests 11–20
def test_11_and_87_an_unsupported_factual_sentence_is_marked_not_invented(client: TestClient, register_org) -> None:
    org = register_org()
    ko = _topic(client, org)
    pub = _publication(client, org, ko)
    s = _sentence(client, org, pub, "Taranjabin cures everything.", None)
    assert s["evidence_unavailable"] is True
    r = client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"]).json()
    assert r["references"] == 0 and r["sentences_without_evidence"] == [0]
    out = client.get(f"{P}/{pub['id']}", headers=org["headers"]).json()
    sentence = out["body"][0]["sentences"][0]
    assert sentence["citation_numbers"] is None and sentence["citation_text"] is None
    assert "(1)" not in sentence["rendered"] and "(999)" not in sentence["rendered"]
    assert out["unsupported_sentences"] == [0]
    audit = client.get(f"{P}/{pub['id']}/citation-audit", headers=org["headers"]).json()
    assert audit["sentences_marked_evidence_unavailable"] == 1 and audit["passed"]


def test_12_a_source_that_does_not_support_the_claim_cannot_be_attached(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    supporting = _source(client, org, "Supporting paper")
    unrelated = _source(client, org, "A paper about something else")
    claim = _claim_with_sources(client, org, db_session, ko, [supporting])
    pub = _publication(client, org, ko)
    r = client.post(f"{P}/{pub['id']}/sentences", headers=org["headers"],
                    json={"text": "A statement.", "claim_id": claim["id"],
                          "extra_source_ids": [unrelated["id"]]})
    assert r.status_code == 409 and "does not support this claim" in r.text
    r2 = client.post(f"{P}/{pub['id']}/sentences", headers=org["headers"],
                     json={"text": "A statement.", "extra_source_ids": [unrelated["id"]]})
    assert r2.status_code == 422 and "through the claim" in r2.text


def test_13_indirect_evidence_stays_indirect_in_the_citation(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    src = _source(client, org, "Mannitol trial")
    ent = client.post("/api/v1/entities", headers=org["headers"],
                      json={"knowledge_object_id": ko["id"], "entity_type": "compound",
                            "canonical_name": "Mannitol"}).json()
    claim = client.post("/api/v1/claims", headers=org["headers"],
                        json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"],
                              "predicate": "acts_as", "object_value": "osmotic laxative",
                              "claim_type": "mechanism"}).json()
    ev = client.post("/api/v1/evidence", headers=org["headers"],
                     json={"source_id": src["id"], "summary": "Mannitol in adults",
                           "directness": "indirect", "evidence_strength": "moderate"}).json()
    db_session.execute(text("UPDATE evidence SET status='verified', evidence_route='compound_human' WHERE id=:i"),
                       {"i": ev["id"]})
    db_session.flush()
    db_session.expire_all()
    client.post("/api/v1/claim-evidence", headers=org["headers"],
                json={"claim_id": claim["id"], "evidence_id": ev["id"], "relation": "supports"})
    pub = _publication(client, org, ko)
    s = _sentence(client, org, pub,
                  "Taranjabin contains mannitol, and mannitol has separately been studied; this does not by "
                  "itself establish the same effect for taranjabin.", claim)
    assert s["sources"][0]["directness"] == "indirect"     # carried through, not flattened
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    out = client.get(f"{P}/{pub['id']}", headers=org["headers"]).json()["body"][0]["sentences"][0]
    assert out["citation_numbers"] == [1] and out["sources"][0]["directness"] == "indirect"


def test_14_an_abstract_only_source_is_marked_in_the_reference_list(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    src = _source(client, org, "Abstract-only paper")
    db_session.execute(text("UPDATE sources SET content_access='abstract_only' WHERE id=:i"), {"i": src["id"]})
    db_session.flush()
    db_session.expire_all()
    claim = _claim_with_sources(client, org, db_session, ko, [src])
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "A statement from an abstract.", claim)
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    ref = client.get(f"{P}/{pub['id']}/references", headers=org["headers"]).json()[0]
    assert ref["access_note"] == "abstract only"


def test_15_a_duplicate_ingestion_takes_one_number(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    first = _source(client, org, "Mannitol trial", doi="10.1000/dup")
    second = _source(client, org, "Mannitol trial (re-ingested)", doi="10.1000/dup")
    assert first["id"] != second["id"]
    claim = _claim_with_sources(client, org, db_session, ko, [first, second])
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "A statement supported by one paper ingested twice.", claim)
    r = client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"]).json()
    assert r["references"] == 1                          # §57 — one canonical source, one number
    out = client.get(f"{P}/{pub['id']}", headers=org["headers"]).json()["body"][0]["sentences"][0]
    assert out["citation_numbers"] == [1]


def test_16_resolving_twice_is_deterministic(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    sources = [_source(client, org, f"Paper {i}") for i in range(4)]
    c1 = _claim_with_sources(client, org, db_session, ko, sources[:2])
    c2 = _claim_with_sources(client, org, db_session, ko, sources[2:], value="other")
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "First.", c1)
    _sentence(client, org, pub, "Second.", c2)
    first = client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"]).json()
    refs1 = client.get(f"{P}/{pub['id']}/references", headers=org["headers"]).json()
    second = client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"]).json()
    refs2 = client.get(f"{P}/{pub['id']}/references", headers=org["headers"]).json()
    assert first["references"] == second["references"]
    assert [(r["number"], r["source_id"]) for r in refs1] == [(r["number"], r["source_id"]) for r in refs2]


def test_17_changing_the_order_renumbers_deterministically(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    a, b = _source(client, org, "Paper A"), _source(client, org, "Paper B")
    ca = _claim_with_sources(client, org, db_session, ko, [a])
    cb = _claim_with_sources(client, org, db_session, ko, [b], value="two")
    pub1 = _publication(client, org, ko)
    _sentence(client, org, pub1, "A first.", ca)
    _sentence(client, org, pub1, "B second.", cb)
    client.post(f"{P}/{pub1['id']}/resolve", headers=org["headers"])
    refs1 = client.get(f"{P}/{pub1['id']}/references", headers=org["headers"]).json()
    assert refs1[0]["source_id"] == a["id"]
    pub2 = _publication(client, org, ko)              # a new version, with the order swapped
    _sentence(client, org, pub2, "B first now.", cb)
    _sentence(client, org, pub2, "A second now.", ca)
    client.post(f"{P}/{pub2['id']}/resolve", headers=org["headers"])
    refs2 = client.get(f"{P}/{pub2['id']}/references", headers=org["headers"]).json()
    assert refs2[0]["source_id"] == b["id"] and refs2[1]["source_id"] == a["id"]


def test_18_an_earlier_version_keeps_its_own_numbering(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    a, b = _source(client, org, "Paper A"), _source(client, org, "Paper B")
    ca = _claim_with_sources(client, org, db_session, ko, [a])
    cb = _claim_with_sources(client, org, db_session, ko, [b], value="two")
    v1 = _publication(client, org, ko)
    _sentence(client, org, v1, "A first.", ca)
    client.post(f"{P}/{v1['id']}/resolve", headers=org["headers"])
    v2 = _publication(client, org, ko)
    _sentence(client, org, v2, "B first.", cb)
    client.post(f"{P}/{v2['id']}/resolve", headers=org["headers"])
    old = client.get(f"{P}/{v1['id']}/references", headers=org["headers"]).json()
    assert old[0]["source_id"] == a["id"] and old[0]["number"] == 1       # version 1 is untouched
    assert client.get(f"{P}/{v1['id']}", headers=org["headers"]).json()["publication"]["status"] == "superseded"


def test_19_and_20_and_86_a_paragraph_and_a_sentence_may_cite_more_than_ten(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    first_ten = [_source(client, org, f"First set {i}") for i in range(10)]
    next_four = [_source(client, org, f"Second set {i}") for i in range(4)]
    c1 = _claim_with_sources(client, org, db_session, ko, first_ten)
    c2 = _claim_with_sources(client, org, db_session, ko, next_four, value="second")
    twelve = [_source(client, org, f"Third set {i}") for i in range(12)]
    c3 = _claim_with_sources(client, org, db_session, ko, twelve, value="third")
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "The first finding is supported by several studies.", c1)
    _sentence(client, org, pub, "The second finding is supported by a different evidence set.", c2)
    _sentence(client, org, pub, "A third statement rests on twelve sources.", c3)
    r = client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"]).json()
    assert r["references"] == 26
    out = client.get(f"{P}/{pub['id']}", headers=org["headers"]).json()["body"][0]["sentences"]
    assert out[0]["citation_text"] == "(1–10)"
    assert out[1]["citation_text"] == "(11–14)"        # §86 — sentence-level mapping preserved
    assert len(out[2]["citation_numbers"]) == 12 and out[2]["citation_text"] == "(15–26)"


# ---------------------------------------------------------------- §88 and the integrity audit
def test_88_references_are_built_only_from_stored_metadata(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    rich = _source(client, org, "Mannitol as an osmotic laxative in adults", doi="10.1000/abc",
                   publisher="J Example Gastro")
    bare = _source(client, org, "A paper with nothing else recorded")
    claim = _claim_with_sources(client, org, db_session, ko, [rich, bare])
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "A statement.", claim)
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    refs = {r["source_id"]: r for r in client.get(f"{P}/{pub['id']}/references", headers=org["headers"]).json()}
    r_rich = refs[rich["id"]]
    assert "Mannitol as an osmotic laxative in adults." in r_rich["formatted"]
    assert "doi:10.1000/abc" in r_rich["formatted"]
    assert set(r_rich["fields_used"]) <= {"authors", "title", "container", "year", "volume", "issue", "pages",
                                          "doi", "pmid", "isbn", "url", "accessed_at"}
    # nothing invented for the bare record: no year, no journal, no doi
    r_bare = refs[bare["id"]]
    assert "doi" not in r_bare["formatted"] and r_bare["fields_used"].get("year") is None
    assert r_bare["formatted"].startswith("A paper with nothing else recorded")


def test_the_citation_integrity_audit_separates_presence_validity_and_support(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    claim = _claim_with_sources(client, org, db_session, ko, [_source(client, org, "Paper A")])
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "A supported statement.", claim)
    _sentence(client, org, pub, "An unsupported statement.", None)
    _sentence(client, org, pub, "Introduction", None, kind="heading")
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    a = client.get(f"{P}/{pub['id']}/citation-audit", headers=org["headers"]).json()
    assert a["citation_required_sentences"] == 2 and a["sentences_with_citations"] == 1
    assert a["sentences_marked_evidence_unavailable"] == 1 and a["sentences_missing_a_citation"] == []
    cov = a["coverage"]
    assert cov["citation_presence"] == 50.0 and cov["citation_validity"] == 100.0
    assert "three different questions" in cov["note"]
    failing = {k: v for k, v in a["checks"].items() if not v}
    assert a["passed"], failing
    # a source recorded with only a title is reported, not treated as a failure
    assert a["references_with_only_a_title"] == [1]


def test_the_database_refuses_a_resolved_factual_sentence_without_a_citation(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    ko = _topic(client, org)
    claim = _claim_with_sources(client, org, db_session, ko, [_source(client, org, "Paper A")])
    pub = _publication(client, org, ko)
    s = _sentence(client, org, pub, "A statement.", claim)
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    with pytest.raises(exc.IntegrityError, match="a_factual_sentence_needs_a_citation"):
        db_session.execute(text("UPDATE publication_sentences SET citation_numbers = NULL, "
                                "evidence_unavailable = false WHERE id = :i"), {"i": s["id"]})
        db_session.flush()
    db_session.rollback()


def test_publications_are_tenant_isolated(client: TestClient, register_org, db_session) -> None:
    x, y = register_org(), register_org()
    ko = _topic(client, x)
    claim = _claim_with_sources(client, x, db_session, ko, [_source(client, x, "Paper A")])
    pub = _publication(client, x, ko)
    _sentence(client, x, pub, "A statement.", claim)
    client.post(f"{P}/{pub['id']}/resolve", headers=x["headers"])
    assert client.get(f"{P}/{pub['id']}", headers=y["headers"]).status_code == 404
    assert client.post(f"{P}/{pub['id']}/resolve", headers=y["headers"]).status_code == 404
    assert client.get(f"{P}/{pub['id']}/citation-audit", headers=y["headers"]).status_code == 404
    assert client.get(P, headers=y["headers"]).json()["total"] == 0


def test_sources_first_cited_together_follow_attachment_order(client: TestClient, register_org, db_session) -> None:
    """Ten sources that first appear in one sentence are numbered in the order their evidence was attached,
    so 'Study 1' is reference 1 and 'Study 10' is reference 10 — not an order derived from internal ids."""
    org = register_org()
    ko = _topic(client, org)
    sources = [_source(client, org, f"Study {i + 1}") for i in range(10)]
    claim = _claim_with_sources(client, org, db_session, ko, sources)
    pub = _publication(client, org, ko)
    _sentence(client, org, pub, "Ten studies report it.", claim)
    client.post(f"{P}/{pub['id']}/resolve", headers=org["headers"])
    refs = client.get(f"{P}/{pub['id']}/references", headers=org["headers"]).json()
    assert [r["source_id"] for r in refs] == [s["id"] for s in sources]
    assert refs[0]["formatted"].startswith("Study 1.") and refs[9]["formatted"].startswith("Study 10.")
