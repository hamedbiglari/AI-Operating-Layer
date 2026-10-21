"""v4 context assembly, budgets, coverage-preserving synthesis and the information-loss audit (ADR-124),
plus the two AI-job defects fixed on the way (§13 truncation, §66 false completion).

Provider HTTP is a mock transport that READS each prompt and answers with real [[U..]] markers, so the
packing, the map/reduce hierarchy, the ledger and the comparator are all exercised for real."""
from __future__ import annotations

import json
import re
import uuid

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import exc, select, text

from app.ai import context_assembly as ca
from app.core.config import settings
from app.integrations.llm.anthropic import AnthropicAdapter
from app.models.ai_center import AIJob, AIJobItem, AIProviderAccount, AIWorkingMemory
from app.models.synthesis import SynthesisRun, SynthesisUnit
from app.services import ai_job_service, synthesis_service as svc

B = "/api/v1/ai-center"
S = "/api/v1/synthesis"


# ---------------------------------------------------------------------- pure engine
def _units(n, *, summary_len=200):
    return [ca.Unit(key=i, claim_id=str(uuid.uuid4()), text=f"Taranjabin contains compound {i}",
                    evidence=[{"summary": "s" * summary_len, "status": "verified", "evidence_strength": "moderate",
                               "directness": "direct"}], source_ids=[f"src{i}"]) for i in range(1, n + 1)]


def test_every_unit_is_packed_and_nothing_is_truncated():
    units = _units(60)
    ca.score(units, query="compound")
    packs = ca.pack(units, budget_tokens=900)
    placed = [u.key for p in packs for u in p.units]
    assert sorted(placed) == list(range(1, 61)) and len(packs) > 1
    assert all(p.tokens <= 900 for p in packs)


def test_a_unit_larger_than_the_context_is_split_never_shortened():
    big = ca.Unit(key=1, claim_id="c", text="huge", evidence=[{"summary": "x" * 9000}, {"summary": "y" * 9000}])
    packs = ca.pack([big], budget_tokens=1500)
    parts = [u for p in packs for u in p.units]
    assert len(parts) > 2 and all(u.key == 1 for u in parts)
    assert "".join(e["summary"] for u in parts for e in u.evidence) == "x" * 9000 + "y" * 9000
    assert all(p.parts and p.parts[0][2] == len(packs) for p in packs)


def test_both_sides_of_a_conflict_land_in_the_same_pack():
    units = _units(30)
    units[0].conflict_ids = ["k"]
    units[29].conflict_ids = ["k"]
    ca.score(units)
    packs = ca.pack(units, budget_tokens=700)
    home = [p.index for p in packs for u in p.units if u.key in (1, 30)]
    assert len(set(home)) == 1


def test_rarity_raises_importance_it_never_removes():
    units = _units(3)
    units[1].source_ids = ["shared"]
    units[2].source_ids = ["shared", "other"]
    ca.score(units)
    assert units[0].scores["rarity"] == 1.0 and units[2].scores["rarity"] == 0.3


def test_three_budgets_are_reported_separately():
    units = _units(40)
    ca.score(units)
    pl = ca.plan(units, ca.Budgets(context_tokens=1500, max_output_tokens=200, max_calls=3, max_cost=0.0001),
                 price_per_1k_input=1.0, price_per_1k_output=1.0)
    assert {"reasoning_budget", "financial_budget"} <= set(pl.blocked_by) and not pl.feasible
    unknown = ca.plan(units, ca.Budgets(max_cost=5.0))
    assert unknown.blocked_by == ["financial_budget_unknown_price"]          # a limit with no price is not a guess


def test_comparator_tells_consolidation_from_loss():
    units = _units(6)
    units[4].conflict_ids = units[5].conflict_ids = ["k"]
    out = ("A. [[U1]] B. [[U2]] C. [[U5]]\n---LEDGER---\nU3 merged_into U1: same finding\n"
           "U4 unresolved: abstract only\n")
    r = ca.compare(units, out)
    assert r.statuses == {1: "represented", 2: "represented", 3: "merged", 4: "unresolved", 5: "contradictory",
                          6: "omitted"}
    assert "silently dropped" in r.reasons[6] and r.information_loss_rate == round(1 / 6, 4)
    assert any(f.startswith("contradiction_collapsed") for f in r.findings) and not r.complete


def test_a_merge_into_nothing_is_a_loss_and_invented_units_are_reported():
    units = _units(2)
    r = ca.compare(units, "Only this. [[U1]] [[U9]]\n---LEDGER---\nU2 merged_into U7: same\n")
    assert r.statuses[2] == "omitted" and "U7" in r.reasons[2]
    assert any("never supplied" in f and "U9" in f for f in r.findings)


def test_sentences_keep_their_markers_even_after_the_full_stop():
    pairs = ca.sentences_with_units("Mannitol is 42.1 g. [[U1]] Glucose too [[U2]][[U3]]. Plain sentence.")
    assert pairs == [("Mannitol is 42.1 g.", [1]), ("Glucose too.", [2, 3]), ("Plain sentence.", [])]


# ---------------------------------------------------------------------- DB + model fixtures
@pytest.fixture(autouse=True)
def cred_key(monkeypatch):
    monkeypatch.setattr(settings, "AI_CREDENTIAL_KEY", SecretStr(Fernet.generate_key().decode()))


class Echo:
    """A provider that reads the prompt it was sent and cites the units in it. Knobs make it misbehave."""

    def __init__(self, *, drop: set[int] | None = None, fail_status: int | None = None, ledger: bool = True):
        self.drop, self.fail_status, self.ledger, self.calls = drop or set(), fail_status, ledger, 0

    def adapter(self):
        def handler(req: httpx.Request):
            self.calls += 1
            if self.fail_status:
                return httpx.Response(self.fail_status, json={"error": {"type": "x"}})
            prompt = json.loads(req.content)["messages"][0]["content"]
            keys = sorted({int(k) for k in re.findall(r"\[\[U(\d+)\]\]", prompt)})
            body = " ".join(f"Finding {k} holds. [[U{k}]]" for k in keys if k not in self.drop)
            if self.ledger:
                body += "\n---LEDGER---\n"
            return httpx.Response(200, json={"id": "m", "model": "m", "stop_reason": "end_turn",
                                             "content": [{"type": "text", "text": body}],
                                             "usage": {"input_tokens": 10, "output_tokens": 5}})
        return AnthropicAdapter(transport=httpx.MockTransport(handler), api_key="sk-test-NOT-REAL-v4")


def _policy(client, h):
    p = client.post(f"{B}/providers", headers=h, json={"name": "Anthropic", "adapter_key": "anthropic",
                                                       "official_url": "https://example.com"}).json()
    a = client.post(f"{B}/accounts", headers=h, json={"provider_id": p["id"], "label": "A"}).json()
    client.put(f"{B}/accounts/{a['id']}/credential", headers=h, json={"secret": "sk-test-NOT-REAL-v4-A"})
    pol = client.post(f"{B}/routing-policies", headers=h, json={"name": f"p{uuid.uuid4().hex[:5]}", "mode": "manual_single",
                                                                "steps": [{"account_id": a["id"], "model": "m"}]})
    assert pol.status_code == 201, pol.text
    return pol.json(), a


def _topic_with_claims(client, h, db, n=6, contested=1):
    ko = client.post("/api/v1/knowledge", headers=h, json={"canonical_name": "Taranjabin", "object_type": "plant"}).json()
    ent = client.post("/api/v1/entities", headers=h, json={"knowledge_object_id": ko["id"], "entity_type": "plant",
                                                            "canonical_name": "Taranjabin"}).json()
    claims = []
    for i in range(n):
        c = client.post("/api/v1/claims", headers=h, json={
            "knowledge_object_id": ko["id"], "subject_entity_id": ent["id"], "predicate": "contains",
            "object_value": f"compound {i}", "section_key": "composition"}).json()
        src = client.post("/api/v1/sources", headers=h, json={"title": f"Study {i}", "source_type": "scientific_paper",
                                                              "doi": f"10.1/v4.{uuid.uuid4().hex[:6]}"}).json()
        ev = client.post("/api/v1/evidence", headers=h, json={"source_id": src["id"],
                                                              "summary": f"human study {i}: " + "measured content. " * 40,
                                                              "evidence_strength": "moderate"}).json()
        db.execute(text("UPDATE evidence SET status = 'verified' WHERE id = :i"), {"i": ev["id"]})
        db.flush()
        db.expire_all()
        client.post("/api/v1/claim-evidence", headers=h, json={"claim_id": c["id"], "evidence_id": ev["id"],
                                                               "relation": "supports"})
        if i < contested:
            src2 = client.post("/api/v1/sources", headers=h, json={"title": f"Counter {i}",
                                                                   "source_type": "scientific_paper"}).json()
            ev2 = client.post("/api/v1/evidence", headers=h, json={"source_id": src2["id"], "summary": "found none"}).json()
            client.post("/api/v1/claim-evidence", headers=h, json={"claim_id": c["id"], "evidence_id": ev2["id"],
                                                                   "relation": "contradicts"})
        claims.append(c)
    return ko, claims


def _adapters(db, a, echo):
    return {db.get(AIProviderAccount, uuid.UUID(a["id"])).id: echo.adapter()}


def _run(db, org, ko, pol, **kw):
    budgets = kw.pop("budgets", ca.Budgets(context_tokens=1000, max_output_tokens=300))
    return svc.create_run(db, organization_id=uuid.UUID(org["organization"]["id"]), user_id=None,
                          knowledge_object_id=uuid.UUID(ko["id"]), task="Summarise composition", budgets=budgets,
                          policy_id=uuid.UUID(pol["id"]) if pol else None, **kw)


@pytest.fixture()
def org(register_org):
    return register_org()


def test_plan_shows_packs_and_budgets_without_calling_a_model(client, db_session, org):
    h = org["headers"]
    ko, _ = _topic_with_claims(client, h, db_session, n=8)
    r = client.post(f"{S}/plan", headers=h, json={"knowledge_object_id": ko["id"], "task": "Summarise",
                                                  "budgets": {"context_tokens": 1000, "max_output_tokens": 300}})
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["status"] == "planned" and plan["coverage"]["input"] == 8 and plan["plan"]["packs"] >= 2
    assert plan["scope"]["units"] == 8 and plan["ai_job_keys"] == []
    placed = sorted(k for p in plan["plan"]["pack_sizes"] for k in p["units"])
    assert placed == list(range(1, 9))


def test_a_blocked_budget_starts_nothing_and_truncates_nothing(client, db_session, org):
    h = org["headers"]
    pol, _ = _policy(client, h)
    ko, _ = _topic_with_claims(client, h, db_session, n=8)
    run = _run(db_session, org, ko, pol, budgets=ca.Budgets(context_tokens=1000, max_output_tokens=300, max_calls=1))
    assert run.status == "blocked" and "Nothing was truncated" in run.failure_reason
    assert run.ai_job_keys == [] and run.pending_units == 8
    assert db_session.execute(select(AIJob).where(AIJob.job_key.like(f"synthesis-{run.id}%"))).first() is None


def test_full_run_map_reduce_audit_everything_accounted_for(client, db_session, org):
    h = org["headers"]
    pol, a = _policy(client, h)
    ko, _ = _topic_with_claims(client, h, db_session, n=8, contested=1)
    run = _run(db_session, org, ko, pol)
    assert run.status == "queued" and run.plan["packs"] >= 2
    echo = Echo()
    run = svc.advance(db_session, run, adapters=_adapters(db_session, a, echo))
    assert run.status == "completed", run.audit
    assert run.ai_job_keys[0].endswith("-map") and any(k.endswith("reduce1") for k in run.ai_job_keys)
    assert run.omitted_units == 0 and run.pending_units == 0 and run.information_loss_rate == 0.0
    assert run.contradictory_units == 1 and run.represented_units == 7
    contested = db_session.execute(select(SynthesisUnit).where(SynthesisUnit.run_id == run.id,
                                                               SynthesisUnit.contested.is_(True))).scalar_one()
    assert contested.status == "contradictory"
    units = client.get(f"{S}/runs/{run.id}/units", headers=h).json()
    assert units["total"] == 8


def test_a_silently_dropped_unit_is_caught_and_the_run_is_not_complete(client, db_session, org):
    h = org["headers"]
    pol, a = _policy(client, h)
    ko, _ = _topic_with_claims(client, h, db_session, n=4, contested=0)
    run = _run(db_session, org, ko, pol, budgets=ca.Budgets(context_tokens=24000, max_output_tokens=400))
    run = svc.advance(db_session, run, adapters=_adapters(db_session, a, Echo(drop={3})))
    assert run.status == "completed_with_gaps" and run.omitted_units == 1
    lost = client.get(f"{S}/runs/{run.id}/units?unit_status=omitted", headers=h).json()["items"]
    assert [u["unit_key"] for u in lost] == [3] and "silently dropped" in lost[0]["omission_reason"]
    assert run.information_loss_rate == 0.25
    # and the database refuses to call it complete
    with pytest.raises(exc.IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE synthesis_runs SET status = 'completed' WHERE id = :i"), {"i": run.id})
    with pytest.raises(exc.IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE synthesis_units SET omission_reason = NULL WHERE run_id = :i "
                                    "AND status = 'omitted'"), {"i": run.id})


def test_partial_run_leaves_the_rest_pending_not_omitted(client, db_session, org):
    h = org["headers"]
    pol, a = _policy(client, h)
    ko, _ = _topic_with_claims(client, h, db_session, n=10, contested=0)
    run = _run(db_session, org, ko, pol, allow_partial=True,
               budgets=ca.Budgets(context_tokens=1000, max_output_tokens=300, max_calls=2))
    assert run.status == "queued" and len(run.plan["selected_packs"]) < run.plan["packs"]
    run = svc.advance(db_session, run, adapters=_adapters(db_session, a, Echo()))
    assert run.status == "completed_with_gaps" and run.pending_units > 0 and run.omitted_units == 0
    pending = client.get(f"{S}/runs/{run.id}/units?unit_status=pending", headers=h).json()["items"]
    assert pending and all("budget" in u["status_reason"] for u in pending)


def test_provider_stop_blocks_and_resume_finishes_without_redoing_work(client, db_session, org):
    h = org["headers"]
    pol, a = _policy(client, h)
    ko, _ = _topic_with_claims(client, h, db_session, n=3, contested=0)
    run = _run(db_session, org, ko, pol, budgets=ca.Budgets(context_tokens=24000, max_output_tokens=400))
    run = svc.advance(db_session, run, adapters=_adapters(db_session, a, Echo(fail_status=429)))
    assert run.status == "blocked" and "Resume" in run.failure_reason
    acc = db_session.get(AIProviderAccount, uuid.UUID(a["id"]))
    acc.health_status, acc.unavailable_until = "healthy", None
    job = db_session.execute(select(AIJob).where(AIJob.job_key == run.ai_job_keys[-1])).scalar_one()
    job.status = "queued"
    run.status, run.failure_reason = "queued", None
    db_session.commit()
    good = Echo()
    run = svc.advance(db_session, run, adapters=_adapters(db_session, a, good))
    assert run.status == "completed" and good.calls == 1


def test_publishing_numbers_citations_from_the_units_own_sources(client, db_session, org):
    h = org["headers"]
    pol, a = _policy(client, h)
    ko, _ = _topic_with_claims(client, h, db_session, n=3, contested=0)
    run = _run(db_session, org, ko, pol, budgets=ca.Budgets(context_tokens=24000, max_output_tokens=400))
    run = svc.advance(db_session, run, adapters=_adapters(db_session, a, Echo()))
    run.result_text = run.result_text.replace("---LEDGER---", "An uncited claim of fact.\n---LEDGER---")
    db_session.commit()
    out = client.post(f"{S}/runs/{run.id}/publish", headers=h)
    assert out.status_code == 201, out.text
    pub = out.json()["publication_id"]
    doc = client.get(f"/api/v1/publications/{pub}", headers=h).json()
    rendered = [s["rendered"] for sec in doc["body"] for s in sec["sentences"]]
    assert rendered[:3] == ["Finding 1 holds. (1)", "Finding 2 holds. (2)", "Finding 3 holds. (3)"]
    assert rendered[3] == "An uncited claim of fact." and doc["unsupported_sentences"] == [3]
    assert [r["number"] for r in doc["references"]] == [1, 2, 3]
    assert client.post(f"{S}/runs/{run.id}/publish", headers=h).status_code == 409


def test_runs_are_tenant_scoped(client, db_session, org, register_org):
    h = org["headers"]
    ko, _ = _topic_with_claims(client, h, db_session, n=2)
    plan = client.post(f"{S}/plan", headers=h, json={"knowledge_object_id": ko["id"], "task": "summarise"}).json()
    other = register_org()["headers"]
    assert client.get(f"{S}/runs/{plan['id']}", headers=other).status_code == 404
    assert client.get(f"{S}/runs", headers=other).json()["total"] == 0
    assert client.post(f"{S}/plan", headers=other, json={"knowledge_object_id": ko["id"], "task": "summarise"}).status_code == 404


# ---------------------------------------------------------------------- the two AI-job defects
def _job(db, org, pol, n):
    job, _ = ai_job_service.create_job(db, organization_id=uuid.UUID(org["organization"]["id"]),
                                       job_key=f"j-{uuid.uuid4().hex[:6]}", goal="g", policy_id=uuid.UUID(pol["id"]),
                                       items=[{"key": f"i{k}", "prompt": f"p{k}"} for k in range(n)])
    return job


def test_long_results_are_stored_whole_not_cut_at_4000_characters(client, db_session, org):
    h = org["headers"]
    pol, a = _policy(client, h)
    job = _job(db_session, org, pol, 1)
    long_text = "x" * 9000

    def handler(req):
        return httpx.Response(200, json={"id": "m", "model": "m", "stop_reason": "end_turn",
                                         "content": [{"type": "text", "text": long_text}],
                                         "usage": {"input_tokens": 1, "output_tokens": 1}})
    adapters = {db_session.get(AIProviderAccount, uuid.UUID(a["id"])).id:
                AnthropicAdapter(transport=httpx.MockTransport(handler), api_key="sk-test-NOT-REAL")}
    ai_job_service.run_job(db_session, job, adapters=adapters)
    mem = db_session.execute(select(AIWorkingMemory).where(AIWorkingMemory.job_key == job.job_key,
                                                           AIWorkingMemory.kind == "intermediate_finding")).scalar_one()
    assert mem.content["result"] == long_text and mem.content["result_chars"] == 9000


def test_a_job_with_failed_items_is_not_reported_completed(client, db_session, org):
    h = org["headers"]
    pol, a = _policy(client, h)
    job = _job(db_session, org, pol, 3)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 2:
            return httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
        return httpx.Response(200, json={"id": "m", "model": "m", "stop_reason": "end_turn",
                                         "content": [{"type": "text", "text": "ok"}],
                                         "usage": {"input_tokens": 1, "output_tokens": 1}})
    adapters = {db_session.get(AIProviderAccount, uuid.UUID(a["id"])).id:
                AnthropicAdapter(transport=httpx.MockTransport(handler), api_key="sk-test-NOT-REAL")}
    res = ai_job_service.run_job(db_session, job, adapters=adapters)
    assert res["status"] == "completed_with_failures" and res["stop_reason"] == "ITEMS_FAILED"
    assert res["failed"] == 1 and res["completed"] == 2
    db_session.refresh(job)
    assert job.status == "completed_with_failures"


def test_the_instructions_contain_no_citable_marker():
    """Regression: the rules once showed '[[U3]]' as an example, which a model could copy as a citation of a
    unit it was never given."""
    assert ca.MARKER_RE.findall(ca.SYSTEM_RULES) == []
    p = ca.pack(_units(2), budget_tokens=2000)[0]
    assert sorted({int(k) for k in ca.MARKER_RE.findall(ca.pack_prompt("t", p, total_packs=1))}) == [1, 2]
