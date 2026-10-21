"""
Budget-aware, coverage-audited synthesis (prompt v4.0 §14–§21, §53, §58–§60; ADR-124).

    collect units from the knowledge base (claims + evidence + conflicts + source locations)
      → score and pack (app/ai/context_assembly.py)  — every unit placed, nothing truncated
      → plan against three budgets                    — blocked, or explicitly partial, never silently cut
      → MAP stage: one ai_job, one item per pack      — existing job system, routing, budget gate
      → REDUCE stages: ai_jobs until one text remains — hierarchical, markers carried through
      → AUDIT path: deterministic coverage comparator — the model never certifies its own completeness
      → optional: publication sentences → Vancouver resolver, sources from the units' own evidence

The knowledge base is read, never written: a synthesis produces text and a ledger, not claims. A model
that "learns" something new in a synthesis has produced an unsupported sentence, which the comparator and
the citation audit will both show.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import prompt_safety
from app.core.config import settings
from app.ai import context_assembly as ca
from app.ai.pricing import ConfiguredPricing
from app.models.ai_center import AIJob, AIJobItem, AIProvider, AIProviderAccount, AIRoutingPolicy, AIRoutingStep
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.entity import Entity
from app.models.evidence import Evidence
from app.models.evidence_conflict import EvidenceConflict
from app.models.knowledge_object import KnowledgeObject
from app.models.source import Source
from app.models.synthesis import SynthesisRun, SynthesisUnit
from app.services import ai_job_service, ai_memory_service as memory

logger = logging.getLogger(__name__)
NEGATIVE_PREDICATES = ("does_not", "not_", "no_effect", "lacks", "absent", "negative", "null")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _v(x):  # enum or str → str
    return str(getattr(x, "value", x)) if x is not None else None


# ---------------------------------------------------------------------- collecting units
def collect_units(db: Session, *, organization_id: UUID, knowledge_object_id: UUID, section_key: str | None = None,
                  claim_ids: list[UUID] | None = None, directness: str | None = None,
                  terms: list[str] | None = None, include_unverified: bool = True) -> tuple[list[ca.Unit], dict]:
    """Every claim in scope becomes a unit with ALL of its evidence — supporting and contradicting — and
    the location each piece was read from. `terms` and `directness` narrow which claims are in scope; the
    filters applied are returned so the scope is explicit (§52)."""
    stmt = select(Claim).where(Claim.organization_id == organization_id,
                               Claim.knowledge_object_id == knowledge_object_id)
    if section_key:
        stmt = stmt.where(Claim.section_key == section_key)
    if claim_ids:
        stmt = stmt.where(Claim.id.in_(claim_ids))
    claims = db.execute(stmt.order_by(Claim.created_at)).scalars().all()
    entities = {e.id: e for e in db.execute(select(Entity).where(
        Entity.organization_id == organization_id, Entity.knowledge_object_id == knowledge_object_id)).scalars()}
    links = db.execute(select(ClaimEvidence).where(
        ClaimEvidence.organization_id == organization_id,
        ClaimEvidence.claim_id.in_([c.id for c in claims] or [None]))).scalars().all()
    ev_ids = {l.evidence_id for l in links}
    evidence = {e.id: e for e in db.execute(select(Evidence).where(Evidence.id.in_(ev_ids or [None]))).scalars()}
    sources = {s.id: s for s in db.execute(select(Source).where(
        Source.id.in_({e.source_id for e in evidence.values()} or [None]))).scalars()}
    conflicts = db.execute(select(EvidenceConflict).where(
        EvidenceConflict.organization_id == organization_id,
        EvidenceConflict.claim_id.in_([c.id for c in claims] or [None]),
        EvidenceConflict.status.in_(("unreviewed", "under_review", "partially_resolved", "unresolvable")))).scalars().all()
    conflicts_by_claim: dict = {}
    for k in conflicts:
        conflicts_by_claim.setdefault(k.claim_id, []).append(str(k.id))

    term_set = [t.lower() for t in (terms or []) if t.strip()]
    # Prompt-injection defence (ADR-126): every free-text field that came from a source is cleaned (hidden
    # characters, forged markers) and scored before it can enter a prompt. High-risk text is withheld and listed
    # here, so the run shows exactly what was kept from the model and why.
    quarantine = settings.PROMPT_INJECTION_QUARANTINE
    flagged: list[dict] = []

    def _safe(value, *, claim, field, evidence_id=None):  # noqa: ANN001, ANN202
        if not value:
            return value
        p = prompt_safety.prepare_untrusted(str(value), quarantine=quarantine)
        if p.assessment.risk != "none" or p.neutralized:
            flagged.append({"claim_id": str(claim.id), "evidence_id": evidence_id, "field": field,
                            "risk": p.assessment.risk, "withheld": p.withheld, "neutralized_tokens": p.neutralized,
                            "signals": p.assessment.signals, "hidden_characters": p.assessment.hidden_characters})
        return p.text

    units: list[ca.Unit] = []
    excluded = {"by_terms": 0, "by_directness": 0}
    for c in claims:
        subject = entities.get(c.subject_entity_id)
        obj = c.object_value or (entities[c.object_entity_id].canonical_name
                                 if c.object_entity_id in entities else str(c.object_entity_id))
        text = _safe(f"{subject.canonical_name if subject else '?'} — {c.predicate.replace('_', ' ')} — {obj}",
                     claim=c, field="claim")
        evs = []
        for l in (l for l in links if l.claim_id == c.id):
            e = evidence.get(l.evidence_id)
            if e is None:
                continue
            if not include_unverified and _v(e.status) != "verified":
                continue
            src = sources.get(e.source_id)
            evs.append({"evidence_id": str(e.id), "source_id": str(e.source_id), "relation": _v(l.relation),
                        "summary": _safe(e.summary, claim=c, field="evidence.summary", evidence_id=str(e.id)),
                        "directness": _v(e.directness),
                        "study_type": _safe(e.study_type, claim=c, field="evidence.study_type", evidence_id=str(e.id)),
                        "sample_size": e.sample_size,
                        "population": _safe(e.population, claim=c, field="evidence.population", evidence_id=str(e.id)),
                        "status": _v(e.status),
                        "evidence_strength": _v(e.evidence_strength), "basis": e.basis,
                        "evidence_route": e.evidence_route, "page": e.page_number,
                        "access": src.content_access if src else None})
        haystack = (text + " " + " ".join((e["summary"] or "") + " " + (e["population"] or "") for e in evs)).lower()
        if term_set and not any(t in haystack for t in term_set):
            excluded["by_terms"] += 1
            continue
        if directness and not any(e["directness"] == directness for e in evs):
            excluded["by_directness"] += 1
            continue
        units.append(ca.Unit(
            key=len(units) + 1, claim_id=str(c.id), text=text, section_key=c.section_key, evidence=evs,
            conflict_ids=conflicts_by_claim.get(c.id, []),
            contradicted=any(e["relation"] == "contradicts" for e in evs) or bool(conflicts_by_claim.get(c.id)),
            negative=any(p in c.predicate.lower() for p in NEGATIVE_PREDICATES),
            source_ids=sorted({e["source_id"] for e in evs})))
    scope = {"knowledge_object_id": str(knowledge_object_id), "section_key": section_key,
             "claim_ids": [str(c) for c in (claim_ids or [])], "directness": directness, "terms": term_set,
             "include_unverified": include_unverified, "claims_in_topic_scope": len(claims),
             "claims_excluded_by_filters": excluded, "units": len(units),
             "prompt_safety": {"policy": prompt_safety.POLICY_VERSION, "quarantine": quarantine,
                               "flagged": flagged, "withheld": sum(1 for x in flagged if x["withheld"])}}
    return units, scope


# ---------------------------------------------------------------------- planning
def _price_for_policy(db: Session, organization_id: UUID, policy_id: UUID | None):
    if policy_id is None:
        return None, None
    step = db.execute(select(AIRoutingStep).where(AIRoutingStep.policy_id == policy_id,
                                                  AIRoutingStep.organization_id == organization_id)
                      .order_by(AIRoutingStep.position).limit(1)).scalar_one_or_none()
    if step is None:
        return None, None
    acc = db.get(AIProviderAccount, step.account_id)
    prov = db.get(AIProvider, acc.provider_id) if acc else None
    price = ConfiguredPricing().price((prov.adapter_key or prov.canonical_name) if prov else "", step.model)
    if price is None:
        return None, step.model
    return (float(price.input_per_mtok) / 1000, float(price.output_per_mtok) / 1000), step.model


def resolve_policy(db: Session, organization_id: UUID, policy_id: UUID | None) -> UUID:
    if policy_id is not None:
        pol = db.execute(select(AIRoutingPolicy).where(AIRoutingPolicy.id == policy_id,
                                                       AIRoutingPolicy.organization_id == organization_id)).scalar_one_or_none()
        if pol is None:
            raise HTTPException(404, "Routing policy not found.")
        return pol.id
    pols = db.execute(select(AIRoutingPolicy.id).where(AIRoutingPolicy.organization_id == organization_id)).scalars().all()
    if len(pols) == 1:
        return pols[0]
    raise HTTPException(422, "Choose a routing policy: " + ("none exists yet — create one in AI Center."
                                                             if not pols else f"{len(pols)} exist."))


def create_run(db: Session, *, organization_id: UUID, user_id: UUID | None, knowledge_object_id: UUID, task: str,
               budgets: ca.Budgets, policy_id: UUID | None = None, section_key: str | None = None,
               claim_ids: list[UUID] | None = None, directness: str | None = None, terms: list[str] | None = None,
               allow_partial: bool = False, plan_only: bool = False) -> SynthesisRun:
    topic = db.execute(select(KnowledgeObject).where(KnowledgeObject.id == knowledge_object_id,
                                                     KnowledgeObject.organization_id == organization_id)).scalar_one_or_none()
    if topic is None:
        raise HTTPException(404, "Knowledge object not found.")
    units, scope = collect_units(db, organization_id=organization_id, knowledge_object_id=topic.id,
                                 section_key=section_key, claim_ids=claim_ids, directness=directness, terms=terms)
    ca.score(units, query=" ".join([task, *(terms or [])]), section_key=section_key)
    resolved_policy = None if plan_only and policy_id is None else resolve_policy(db, organization_id, policy_id)
    prices, model = _price_for_policy(db, organization_id, resolved_policy)
    run = SynthesisRun(organization_id=organization_id, knowledge_object_id=topic.id, section_key=section_key,
                       task=task, scope=scope, budgets=budgets.__dict__, allow_partial=allow_partial,
                       policy_id=resolved_policy, knowledge_version=topic.version,
                       prompt_version=ca.PROMPT_VERSION, created_by_user_id=user_id, input_units=len(units),
                       pending_units=len(units), status="planned", ai_job_keys=[])
    db.add(run)
    db.flush()
    if not units:
        run.status, run.failure_reason = "blocked", "No knowledge units in scope — nothing to synthesise."
        run.plan = {"packs": 0}
        db.commit()
        return run
    pl = ca.plan(units, budgets, price_per_1k_input=prices[0] if prices else None,
                 price_per_1k_output=prices[1] if prices else None)
    pack_of = {u.key: p.index for p in pl.packs for u in p.units}
    for u in units:
        db.add(SynthesisUnit(organization_id=organization_id, run_id=run.id, unit_key=u.key,
                             claim_id=UUID(u.claim_id), text=u.text, pack_index=pack_of.get(u.key),
                             token_estimate=u.tokens, importance=u.importance, scores=u.scores,
                             contested=u.contradicted, status="pending",
                             evidence_ids=[e["evidence_id"] for e in u.evidence], source_ids=u.source_ids))
    selected = list(range(len(pl.packs)))
    if not pl.feasible and allow_partial and "financial_budget_unknown_price" not in pl.blocked_by:
        selected = _packs_within(pl, budgets, prices)
    run.plan = {"packs": len(pl.packs), "levels": pl.levels, "calls": pl.calls, "input_tokens": pl.input_tokens,
                "output_tokens": pl.output_tokens, "estimated_cost": pl.estimated_cost, "model": model,
                "feasible": pl.feasible, "blocked_by": pl.blocked_by, "notes": pl.notes,
                "selected_packs": selected,
                "pack_sizes": [{"index": p.index, "units": [u.key for u in p.units], "tokens": p.tokens,
                                "split_units": [list(x) for x in p.parts]} for p in pl.packs]}
    if plan_only:
        db.commit()
        return run
    if not pl.feasible and (not allow_partial or not selected):
        run.status = "blocked"
        run.failure_reason = ("Budget insufficient: " + "; ".join(pl.notes) +
                              ". Nothing was truncated. Raise the budget, narrow the scope, or allow a partial "
                              "run (unprocessed units stay pending, not omitted).")
        db.commit()
        return run
    _start_map_stage(db, run, task, pl.packs, selected, budgets)
    db.commit()
    return run


def _packs_within(pl: ca.Plan, budgets: ca.Budgets, prices) -> list[int]:
    """§23 graceful degradation: the most important packs first, as many as the budgets allow, leaving a
    reduce call's worth of room. The rest stay pending and are reported as such."""
    chosen: list[int] = []
    cost = 0.0
    for p in pl.packs:                                  # packs are already in importance order
        calls_if = len(chosen) + 1 + (1 if len(chosen) + 1 > 1 else 0)
        if budgets.max_calls is not None and calls_if > budgets.max_calls:
            break
        if budgets.max_cost is not None and prices:
            step = (p.tokens + 600) / 1000 * prices[0] + budgets.max_output_tokens / 1000 * prices[1]
            if cost + step > budgets.max_cost:
                break
            cost += step
        chosen.append(p.index)
    return chosen


def _job_key(run: SynthesisRun, stage: str) -> str:
    return f"synthesis-{run.id}-{stage}"


def _start_map_stage(db: Session, run: SynthesisRun, task: str, packs: list[ca.Pack], selected: list[int],
                     budgets: ca.Budgets) -> None:
    items = [{"key": f"pack-{p.index}", "prompt": ca.pack_prompt(task, p, total_packs=len(packs))}
             for p in packs if p.index in selected]
    key = _job_key(run, "map")
    ai_job_service.create_job(db, organization_id=run.organization_id, job_key=key, goal=f"synthesis map: {task}"[:1000],
                              policy_id=run.policy_id, items=items, stage="synthesis",
                              user_id=run.created_by_user_id, knowledge_object_id=run.knowledge_object_id,
                              max_output_tokens=budgets.max_output_tokens)
    run.ai_job_keys = [*run.ai_job_keys, key]
    run.status, run.current_stage, run.started_at = "queued", "map", _now()


# ---------------------------------------------------------------------- execution (worker)
def _outputs(db: Session, run: SynthesisRun, key: str) -> dict[str, str]:
    items, _ = memory.list_items(db, organization_id=run.organization_id, job_key=key,
                                 kind="intermediate_finding", limit=100000)
    out: dict[str, str] = {}
    for it in sorted(items, key=lambda i: i.version):
        out[it.item_key] = (it.content or {}).get("result", "")
    return out


def advance(db: Session, run: SynthesisRun, *, adapters: dict | None = None, pricing=None) -> SynthesisRun:  # noqa: ANN001
    """Drive the run to its end in one worker call: run the current stage's job, then the next stage, then
    audit. Safe to call again after an interruption — completed job items are never re-run (ADR-090)."""
    if run.status in ("completed", "completed_with_gaps", "failed", "cancelled", "blocked"):
        return run
    run.status = "running"
    db.commit()
    budgets = ca.Budgets(**run.budgets)
    level = 0
    while True:
        key = run.ai_job_keys[-1]
        job = db.execute(select(AIJob).where(AIJob.organization_id == run.organization_id,
                                             AIJob.job_key == key)).scalar_one()
        if job.status not in ("completed", "completed_with_failures"):
            res = ai_job_service.run_job(db, job, adapters=adapters, pricing=pricing)
            db.refresh(job)
            if res["status"] not in ("completed", "completed_with_failures"):
                run.status = "blocked" if res["status"] == "blocked" else "running"
                if run.status == "blocked":
                    run.failure_reason = f"AI job {key} stopped: {res.get('stop_reason')}. Resume continues from its checkpoint."
                db.commit()
                return run
        outputs = _outputs(db, run, key)
        items = db.execute(select(AIJobItem).where(AIJobItem.job_id == job.id).order_by(AIJobItem.position)).scalars().all()
        texts = [outputs[i.item_key] for i in items if i.status == "completed" and i.item_key in outputs]
        failed_items = [i.item_key for i in items if i.status == "failed"]
        if failed_items:
            run.audit = {**(run.audit or {}), f"failed_items_{key}": failed_items}
        if len(texts) <= 1:
            final = texts[0] if texts else ""
            break
        level += 1
        per = max(2, (budgets.context_tokens - 600) // max(1, budgets.max_output_tokens))
        groups = [texts[i:i + per] for i in range(0, len(texts), per)]
        keys = sorted({int(k) for t in texts for k in ca.MARKER_RE.findall(t)})
        rkey = _job_key(run, f"reduce{level}")
        ai_job_service.create_job(db, organization_id=run.organization_id, job_key=rkey,
                                  goal=f"synthesis reduce {level}: {run.task}"[:1000], policy_id=run.policy_id,
                                  items=[{"key": f"group-{n}", "prompt": ca.reduce_prompt(run.task, g, keys)}
                                         for n, g in enumerate(groups)],
                                  stage="synthesis", user_id=run.created_by_user_id,
                                  knowledge_object_id=run.knowledge_object_id,
                                  max_output_tokens=budgets.max_output_tokens)
        run.ai_job_keys = [*run.ai_job_keys, rkey]
        run.current_stage = f"reduce{level}"
        db.commit()
    return audit(db, run, final)


def _units_for(db: Session, run: SynthesisRun) -> tuple[list[ca.Unit], list[SynthesisUnit]]:
    rows = db.execute(select(SynthesisUnit).where(SynthesisUnit.run_id == run.id)
                      .order_by(SynthesisUnit.unit_key)).scalars().all()
    units = [ca.Unit(key=r.unit_key, claim_id=str(r.claim_id), text=r.text, contradicted=r.contested,
                     source_ids=r.source_ids) for r in rows]
    return units, rows


def _safety_report(db: Session, run: SynthesisRun) -> dict:
    """Everything the prompt-injection defences saw during this run (ADR-126): source text withheld or cleaned
    before sending, and every model answer that was rejected, cleaned, or reported an injection attempt."""
    outputs: list[dict] = []
    for key in run.ai_job_keys or []:
        items, _ = memory.list_items(db, organization_id=run.organization_id, job_key=key,
                                     kind="intermediate_finding", limit=100000)
        for it in items:
            s = (it.content or {}).get("safety")
            if s:
                outputs.append({"stage": key.rsplit("-", 1)[-1], "item": it.item_key, **s})
        job = db.execute(select(AIJob).where(AIJob.organization_id == run.organization_id,
                                             AIJob.job_key == key)).scalar_one_or_none()
        if job is not None:
            for i in db.execute(select(AIJobItem).where(AIJobItem.job_id == job.id,
                                                        AIJobItem.failure_reason.like("OUTPUT_REJECTED%"))).scalars():
                outputs.append({"stage": key.rsplit("-", 1)[-1], "item": i.item_key, "rejected": True,
                                "findings": [{"category": "output_rejected", "detail": i.failure_reason}],
                                "notices": [], "needs_review": True})
    source = (run.scope or {}).get("prompt_safety") or {}
    review = bool(source.get("flagged")) or any(o.get("needs_review") for o in outputs)
    return {"policy": prompt_safety.POLICY_VERSION, "source_text": source, "model_outputs": outputs,
            "review_required": review}


def audit(db: Session, run: SynthesisRun, final_text: str) -> SynthesisRun:
    """§20–§21 — the audit path, independent of the generation path."""
    units, rows = _units_for(db, run)
    selected = set((run.plan or {}).get("selected_packs") or [])
    unprocessed = {r.unit_key for r in rows if r.pack_index is not None and r.pack_index not in selected}
    failed = set()
    for k, v in (run.audit or {}).items():
        if k.startswith("failed_items_") and k.endswith("-map"):
            failed |= {int(x.split("-")[1]) for x in v}
    unprocessed |= {r.unit_key for r in rows if r.pack_index in failed}
    result = ca.compare(units, final_text, unprocessed=unprocessed)
    for r in rows:
        r.status = result.statuses[r.unit_key]
        r.status_reason = result.reasons.get(r.unit_key)
        r.merged_into_key = result.merged_into.get(r.unit_key)
        r.omission_reason = result.reasons.get(r.unit_key) if r.status == "omitted" else None
        if r.unit_key in unprocessed and r.pack_index in failed:
            r.status_reason = "its pack failed at the provider; still pending"
    c = result.counts
    run.result_text = final_text
    run.represented_units, run.merged_units = c["represented"], c["merged"]
    run.transformed_units, run.unresolved_units = c["transformed"], c["unresolved"]
    run.contradictory_units, run.omitted_units, run.pending_units = c["contradictory"], c["omitted"], c["pending"]
    run.information_loss_rate = result.information_loss_rate
    safety = _safety_report(db, run)
    run.audit = {**(run.audit or {}), "findings": result.findings, "counts": c, "prompt_safety": safety,
                 "method": "deterministic coverage comparator over [[U..]] markers and the ledger",
                 "note": ("Represented means cited in the text. Whether the sentence says what the unit says is "
                          "checked by people, and by the citation audit when the text is published.")}
    run.status = "completed" if result.complete else "completed_with_gaps"
    run.current_stage, run.finished_at = "audited", _now()
    db.commit()
    return run


# ---------------------------------------------------------------------- publishing (§39–§41)
def to_publication(db: Session, run: SynthesisRun, *, title: str | None = None,
                   security_reviewed_by=None) -> dict:  # noqa: ANN001
    """Turn the synthesis into publication sentences. Each sentence's sources come from the claims behind
    the units it cited — the resolver then numbers them. A sentence that cited no unit is added as
    factual and therefore marked evidence-unavailable: an uncited statement is shown, never hidden and
    never given an invented number."""
    from app.services import citation_resolver, publication_service

    if run.status not in ("completed", "completed_with_gaps") or not run.result_text:
        raise HTTPException(409, "Only an audited synthesis can be published.")
    if run.publication_id is not None:
        raise HTTPException(409, "This synthesis has already been turned into a publication.")
    safety = (run.audit or {}).get("prompt_safety") or {}
    if safety.get("review_required"):
        # ADR-126: text touched by a possible prompt injection never becomes a publication on a model's word.
        # An owner or admin must read the flagged items and confirm explicitly; the confirmation is audited.
        if security_reviewed_by is None:
            raise HTTPException(409, {"message": "Possible prompt injection was detected in this run's sources or "
                                                 "model output. An owner or admin must review the flagged items "
                                                 "(audit.prompt_safety) and publish with security_reviewed=true.",
                                      "prompt_safety": safety})
        from app.services.audit import record_audit_log

        record_audit_log(db, organization_id=run.organization_id, user_id=security_reviewed_by.id,
                         action="synthesis.prompt_safety_review_confirmed", resource_type="synthesis_run",
                         resource_id=run.id, new_value={"flagged_sources": len((safety.get("source_text") or {})
                                                                               .get("flagged") or []),
                                                         "flagged_outputs": len(safety.get("model_outputs") or [])})
    body, _ = ca.split_output(run.result_text)
    claim_of = {r.unit_key: r.claim_id for r in db.execute(select(SynthesisUnit).where(
        SynthesisUnit.run_id == run.id)).scalars()}
    pub = publication_service.create_publication(db, organization_id=run.organization_id,
                                                 knowledge_object_id=run.knowledge_object_id, title=title)
    section = publication_service.add_section(db, organization_id=run.organization_id, publication_id=pub.id,
                                              title=title or "Synthesis", section_key=run.section_key)
    uncited = 0
    for paragraph, (text, keys) in enumerate(ca.sentences_with_units(body)):
        claims = [claim_of[k] for k in keys if claim_of.get(k)]
        if not claims:
            uncited += 1
        publication_service.add_sentence(db, organization_id=run.organization_id, publication_id=pub.id,
                                         text=text, kind="factual", claim_id=claims[0] if claims else None,
                                         additional_claim_ids=claims[1:], paragraph=paragraph,
                                         section_id=section.id)
    resolved = citation_resolver.resolve(db, organization_id=run.organization_id, publication_id=pub.id)
    run.publication_id = pub.id
    db.commit()
    return {"publication_id": str(pub.id), "resolved": resolved, "sentences_without_units": uncited}


def run_out(run: SynthesisRun) -> dict:
    return {"id": str(run.id), "knowledge_object_id": str(run.knowledge_object_id) if run.knowledge_object_id else None,
            "section_key": run.section_key, "task": run.task, "scope": run.scope, "status": run.status,
            "failure_reason": run.failure_reason, "budgets": run.budgets, "plan": run.plan,
            "allow_partial": run.allow_partial, "current_stage": run.current_stage, "ai_job_keys": run.ai_job_keys,
            "knowledge_version": run.knowledge_version, "prompt_version": run.prompt_version,
            "coverage": {"input": run.input_units, "represented": run.represented_units, "merged": run.merged_units,
                         "transformed": run.transformed_units, "unresolved": run.unresolved_units,
                         "contradictory": run.contradictory_units, "omitted": run.omitted_units,
                         "pending": run.pending_units, "information_loss_rate": run.information_loss_rate},
            "audit": run.audit, "result_text": run.result_text,
            "publication_id": str(run.publication_id) if run.publication_id else None,
            "created_at": run.created_at, "started_at": run.started_at, "finished_at": run.finished_at}


def unit_out(u: SynthesisUnit) -> dict:
    return {"unit_key": u.unit_key, "claim_id": str(u.claim_id) if u.claim_id else None, "text": u.text,
            "pack_index": u.pack_index, "token_estimate": u.token_estimate, "importance": u.importance,
            "scores": u.scores, "contested": u.contested, "status": u.status,
            "merged_into_key": u.merged_into_key, "omission_reason": u.omission_reason,
            "status_reason": u.status_reason, "evidence_ids": u.evidence_ids, "source_ids": u.source_ids}
