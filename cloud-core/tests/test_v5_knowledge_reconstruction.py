"""Prompt v5 Workflow A + E (ADR-134): several workers process different source batches, return Knowledge
Transfer Packages, and the validator + reconciler turn them into one evidence-linked canonical state.

* the same claim from two sources -> one claim with two evidence links (evidence preserved, not deduplicated away);
* a contradicting source -> linked as `contradicts` and recorded as a conflict; nothing chosen, nothing overwritten;
* same subject+predicate, different value -> a separate variant claim pointing at the one it differs from;
* quotes not found in stored text, sources with no text, unknown entities, unsupported assertions and
  evidence about another substance filed as direct are rejected with a reason, never silently accepted;
* malformed or truncated output fails the item visibly; resubmission is idempotent; tenants are isolated.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import func, select

from app.models.ai_center import AIJob, AIJobItem
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.evidence import Evidence
from app.models.evidence_conflict import EvidenceConflict
from app.models.knowledge_transfer import KnowledgeTransferRecord
from app.services import ai_job_service
from tests.test_ai_center import B, Scripted, acct, cred_key, mk_account, mk_policy, mk_provider  # noqa: F401

K = "/api/v1/knowledge-transfer"

S1 = "Analysis of the exudate showed that Toranjebin contains mannitol as its principal sugar alcohol."
S2 = "In our samples Toranjebin contains mannitol, together with smaller amounts of sucrose."
S3 = "No mannitol was detected in any of the twelve Toranjebin samples examined by HPLC."
S4 = "Mannitol acts as an osmotic laxative in adults at oral doses above 20 g."


@pytest.fixture()
def org(register_org):
    return register_org()


@pytest.fixture(autouse=True)
def no_background(monkeypatch):
    import app.api.v1.ai_center as api
    monkeypatch.setattr(api, "_run_in_background", lambda job_id: None)


def _post(client, h, path, body):
    r = client.post(path, headers=h, json=body)
    assert r.status_code in (200, 201, 202), r.text
    return r.json()


@pytest.fixture()
def world(client, org):
    h = org["headers"]
    ko = _post(client, h, "/api/v1/knowledge", {"canonical_name": "Toranjebin", "object_type": "plant"})
    tor = _post(client, h, "/api/v1/entities", {"knowledge_object_id": ko["id"], "entity_type": "substance",
                                               "canonical_name": "Toranjebin", "aliases": ["Taranjabin"]})
    man = _post(client, h, "/api/v1/entities", {"knowledge_object_id": ko["id"], "entity_type": "compound",
                                               "canonical_name": "Mannitol"})
    src, doc = {}, {}
    for name, text_ in (("s1", S1), ("s2", S2), ("s3", S3), ("s4", S4)):
        src[name] = _post(client, h, "/api/v1/sources", {"source_type": "scientific_paper", "title": f"Paper {name}"})
        doc[name] = _post(client, h, f"/api/v1/documents?source_id={src[name]['id']}", {"title": name, "content": text_})
    src["empty"] = _post(client, h, "/api/v1/sources", {"source_type": "scientific_paper", "title": "Title only"})
    return {"h": h, "ko": ko, "tor": tor, "man": man, "src": src, "doc": doc}


def _ev(w, name, quote, **kw):
    return {"source_id": w["src"][name]["id"], "document_id": w["doc"][name]["id"], "quote": quote, **kw}


def _contains(local_id, evidence, value="mannitol"):
    return {"local_id": local_id, "subject": "Toranjebin", "predicate": "contains", "object_value": value,
            "evidence": evidence}


def _pkg(*claims, **extra):
    return json.dumps({"ktp_version": 1, "claims": list(claims), **extra})


def _body(text_, stop="end_turn"):
    return {"id": "msg", "model": "m", "stop_reason": stop, "content": [{"type": "text", "text": text_}],
            "usage": {"input_tokens": 10, "output_tokens": 5}}


def _ktp_job(client, db, w, pol, prompts):
    key = f"ktp-{uuid.uuid4().hex[:8]}"
    _post(client, w["h"], f"{B}/jobs", {"job_key": key, "goal": "reconstruct", "policy_id": pol["id"],
                                        "knowledge_object_id": w["ko"]["id"], "output_contract": "ktp_v1",
                                        "items": [{"key": f"batch-{i}", "prompt": p} for i, p in enumerate(prompts)]})
    return db.execute(select(AIJob).where(AIJob.job_key == key)).scalar_one()


def test_workflow_a_two_workers_reconcile_into_one_evidence_linked_state(client, db_session, world):
    w, h = world, world["h"]
    p = mk_provider(client, h)
    a, b = mk_account(client, h, p["id"], "worker-A"), mk_account(client, h, p["id"], "worker-B")
    pol_a = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    pol_b = mk_policy(client, h, "manual_single", [{"account_id": b["id"], "model": "m"}])
    # Worker A reads batch 1 (S1); worker B reads batch 2 (S2 agrees, S3 disagrees, S4 is about mannitol only).
    out_a = _pkg(_contains("c1", [_ev(w, "s1", "Toranjebin contains mannitol as its principal sugar alcohol")]),
                 gaps=["no quantitative mannitol content reported"])
    out_b = _pkg(_contains("c1", [_ev(w, "s2", "Toranjebin contains mannitol"),
                                  _ev(w, "s3", "No mannitol was detected in any of the twelve Toranjebin samples",
                                      relation="contradicts")]),
                 {"local_id": "c2", "subject": "Toranjebin", "predicate": "may_act_as", "object_value": "laxative",
                  "evidence": [_ev(w, "s4", "Mannitol acts as an osmotic laxative", directness="indirect",
                                   route="compound_human", about="Mannitol")]})
    job_a = _ktp_job(client, db_session, w, pol_a, ["batch 1"])
    job_b = _ktp_job(client, db_session, w, pol_b, ["batch 2"])
    ra = ai_job_service.run_job(db_session, job_a, adapters={acct(db_session, a).id: Scripted(lambda n: (200, _body(out_a))).adapter()})
    rb = ai_job_service.run_job(db_session, job_b, adapters={acct(db_session, b).id: Scripted(lambda n: (200, _body(out_b))).adapter()})
    assert ra["status"] == rb["status"] == "completed"

    ko_id = uuid.UUID(w["ko"]["id"])
    claims = db_session.execute(select(Claim).where(Claim.knowledge_object_id == ko_id)).scalars().all()
    contains = [c for c in claims if c.predicate == "contains"]
    assert len(contains) == 1                                       # one canonical claim, not two
    links = db_session.execute(select(ClaimEvidence).where(ClaimEvidence.claim_id == contains[0].id)).scalars().all()
    rel = sorted(str(getattr(l.relation, "value", l.relation)) for l in links)
    assert rel == ["contradicts", "supports", "supports"]           # every independent source kept
    conflicts = db_session.execute(select(EvidenceConflict).where(EvidenceConflict.claim_id == contains[0].id)).scalars().all()
    assert len(conflicts) == 2 and all(c.status == "unreviewed" for c in conflicts)   # both pairs on file, no side chosen
    assert all(c.status.value == "draft" and c.source_generated for c in claims)      # workers never approve knowledge
    lax = next(c for c in claims if c.predicate == "may_act_as")
    lax_ev = db_session.execute(select(Evidence).join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
                                .where(ClaimEvidence.claim_id == lax.id)).scalar_one()
    assert lax_ev.directness.value == "indirect" and lax_ev.evidence_about == "Mannitol"   # §35 labelled, not transferred

    pkgs = client.get(f"{K}/packages?knowledge_object_id={ko_id}", headers=h).json()
    assert pkgs["total"] == 2 and {x["status"] for x in pkgs["items"]} == {"reconciled"}
    outcomes = {o["outcome"] for x in pkgs["items"] for o in x["reconciliation"]["claims"]}
    assert outcomes == {"new_claim", "duplicate"}
    assert any(x["reconciliation"]["gaps"] for x in pkgs["items"])  # gaps are not lost on the way in
    # the knowledge is queryable through the existing claims API
    listed = client.get(f"/api/v1/claims?knowledge_object_id={ko_id}", headers=h).json()
    assert listed["total"] == 2


def test_variant_is_kept_beside_the_claim_it_differs_from(client, db_session, world):
    w = world
    first = client.post(f"{K}/packages", headers=w["h"], json={"knowledge_object_id": w["ko"]["id"], "package": _pkg(
        _contains("c1", [_ev(w, "s2", "Toranjebin contains mannitol")]))}).json()
    second = client.post(f"{K}/packages", headers=w["h"], json={"knowledge_object_id": w["ko"]["id"], "package": _pkg(
        _contains("c1", [_ev(w, "s2", "together with smaller amounts of sucrose")], value="sucrose"))}).json()
    assert first["status"] == second["status"] == "reconciled"
    out = second["reconciliation"]["claims"][0]
    assert out["outcome"] == "variant" and out["variant_of"] == [first["reconciliation"]["claims"][0]["claim_id"]]


def test_rejections_are_explicit(client, db_session, world):
    w = world
    pkg = _pkg(
        _contains("mismatch", [_ev(w, "s1", "Toranjebin cures every known disease of the liver")]),
        _contains("no-text", [{"source_id": w["src"]["empty"]["id"], "quote": "Toranjebin contains mannitol here"}]),
        {"local_id": "unknown", "subject": "Shirkhesht", "predicate": "contains", "object_value": "x",
         "evidence": [_ev(w, "s1", "Toranjebin contains mannitol")]},
        _contains("bare", []),
        {"local_id": "transfer", "subject": "Toranjebin", "predicate": "acts_as", "object_value": "laxative",
         "evidence": [_ev(w, "s4", "Mannitol acts as an osmotic laxative", about="Mannitol")]},
        _contains("ok", [_ev(w, "s1", "toranjebin   CONTAINS mannitol")]),    # whitespace/case-insensitive match
    )
    r = client.post(f"{K}/packages", headers=w["h"], json={"knowledge_object_id": w["ko"]["id"], "package": pkg}).json()
    assert r["status"] == "partially_reconciled"
    v = {c["local_id"]: c for c in r["validation"]["claims"]}
    assert v["mismatch"]["reason"] == "NO_VERIFIABLE_EVIDENCE" and v["mismatch"]["rejected_evidence"][0]["code"] == "CITATION_MISMATCH"
    assert v["no-text"]["rejected_evidence"][0]["code"] == "SOURCE_TEXT_UNAVAILABLE"
    assert v["unknown"]["reason"] == "UNKNOWN_ENTITY" and r["reconciliation"]["entity_candidates"] == ["Shirkhesht"]
    assert v["bare"]["reason"] == "UNSUPPORTED_ASSERTION"
    assert v["transfer"]["rejected_evidence"][0]["code"] == "EVIDENCE_ABOUT_OTHER_ENTITY_MARKED_DIRECT"
    assert v["ok"]["accepted"] is True


def test_malformed_and_truncated_output_fail_the_item(client, db_session, world):
    w, h = world, world["h"]
    p = mk_provider(client, h)
    a = mk_account(client, h, p["id"], "A")
    pol = mk_policy(client, h, "manual_single", [{"account_id": a["id"], "model": "m"}])
    good = _pkg(_contains("c1", [_ev(w, "s1", "Toranjebin contains mannitol")]))
    replies = [_body("Here is a summary: Toranjebin is sweet."), _body(good[: len(good) // 2], stop="max_tokens"),
               _body("```json\n" + good + "\n```")]
    job = _ktp_job(client, db_session, w, pol, ["b0", "b1", "b2"])
    res = ai_job_service.run_job(db_session, job, adapters={acct(db_session, a).id: Scripted(lambda n: (200, replies[n - 1])).adapter()})
    assert res["status"] == "completed_with_failures" and res["completed"] == 1 and res["failed"] == 2
    items = {i.item_key: i for i in db_session.execute(select(AIJobItem).where(AIJobItem.job_id == job.id)).scalars()}
    assert items["batch-0"].failure_reason.startswith("OUTPUT_INVALID: MALFORMED")
    assert items["batch-1"].failure_reason.startswith("OUTPUT_INVALID: OUTPUT_TRUNCATED")
    assert items["batch-2"].status == "completed"                   # a fenced JSON block is still read


def test_resubmission_is_idempotent(client, db_session, world):
    w = world
    body = {"knowledge_object_id": w["ko"]["id"], "package": _pkg(_contains("c1", [_ev(w, "s1", "Toranjebin contains mannitol")]))}
    one = client.post(f"{K}/packages", headers=w["h"], json=body).json()
    n_ev = db_session.execute(select(func.count()).select_from(Evidence)).scalar_one()
    two = client.post(f"{K}/packages", headers=w["h"], json=body).json()
    assert one["id"] == two["id"]
    assert db_session.execute(select(func.count()).select_from(Evidence)).scalar_one() == n_ev
    assert db_session.execute(select(func.count()).select_from(KnowledgeTransferRecord)).scalar_one() == 1


def test_tenant_isolation(client, db_session, register_org, world):
    w = world
    rec = client.post(f"{K}/packages", headers=w["h"], json={"knowledge_object_id": w["ko"]["id"], "package": _pkg(
        _contains("c1", [_ev(w, "s1", "Toranjebin contains mannitol")]))}).json()
    other = register_org()
    assert client.get(f"{K}/packages/{rec['id']}", headers=other["headers"]).status_code == 404
    assert client.get(f"{K}/packages", headers=other["headers"]).json()["total"] == 0
    # another tenant cannot write into this topic
    assert client.post(f"{K}/packages", headers=other["headers"], json={
        "knowledge_object_id": w["ko"]["id"], "package": _pkg()}).status_code == 404
    # nor cite this tenant's sources from its own topic
    ko2 = _post(client, other["headers"], "/api/v1/knowledge", {"canonical_name": "Toranjebin", "object_type": "plant"})
    _post(client, other["headers"], "/api/v1/entities", {"knowledge_object_id": ko2["id"], "entity_type": "substance",
                                                         "canonical_name": "Toranjebin"})
    r = client.post(f"{K}/packages", headers=other["headers"], json={"knowledge_object_id": ko2["id"], "package": _pkg(
        _contains("c1", [_ev(w, "s1", "Toranjebin contains mannitol")]))}).json()
    assert r["status"] == "nothing_accepted"
    assert r["validation"]["claims"][0]["rejected_evidence"][0]["code"] == "SOURCE_REFERENCE_INVALID"


def test_a_contract_job_needs_a_topic_in_the_callers_tenant(client, db_session, register_org, world):
    w = world
    other = register_org()
    p = mk_provider(client, other["headers"])
    a = mk_account(client, other["headers"], p["id"], "A")
    pol = mk_policy(client, other["headers"], "manual_single", [{"account_id": a["id"], "model": "m"}])
    body = {"job_key": "x", "goal": "g", "policy_id": pol["id"], "output_contract": "ktp_v1", "items": [{"key": "k", "prompt": "p"}]}
    assert client.post(f"{B}/jobs", headers=other["headers"], json=body).status_code == 422
    body["knowledge_object_id"] = w["ko"]["id"]
    assert client.post(f"{B}/jobs", headers=other["headers"], json=body).status_code == 404
