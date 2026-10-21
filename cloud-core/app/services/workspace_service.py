"""
Persistent command workspace (prompt v4.0 §46–§54; ADR-125).

    type → autosave draft (server) → plan (intent + explicit scope + budget, shown before running)
         → run (version frozen, job queued) → worker executes → result + cost + errors on the version
         → close the page at any point: nothing is lost; return → continue / view / restart

WHAT RUNS WHERE
* Deterministic intents (claims on a page, unsupported statements, contradictions, section applicability,
  evidence for a claim, coverage audit) are answered from the knowledge base by `knowledge_query_service`
  and the existing services. No model, no cost.
* `reprocess_document` queues the existing ingestion job (`sync_jobs`).
* `evidence_research`, `synthesis`, `matrix_cell_research` run a budgeted synthesis
  (`synthesis_service`), whose model calls are ordinary `ai_jobs`. There is no second job system.

The parser only PROPOSES an intent from the words typed. The plan step shows it with the scope it will
act on, and the person can correct either before anything runs (§52: scope is explicit before execution).
"""
from __future__ import annotations

import difflib
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.context_assembly import Budgets
from app.models.ai_execution import AIExecution
from app.models.ai_center import AIJob
from app.models.knowledge_object import KnowledgeObject
from app.models.synthesis import SynthesisRun
from app.models.workspace import INTENTS, WorkspaceCommand, WorkspaceCommandVersion
from app.services.audit import record_audit_log

AI_INTENTS = ("evidence_research", "synthesis", "matrix_cell_research")
TERMINAL = ("completed", "completed_with_gaps", "failed", "cancelled")

# Ordered most-specific first. Each rule anchors on a phrase, never on one ambiguous word (the lesson of
# the Phase 6 intent classifier). English and Persian.
RULES: list[tuple[str, re.Pattern]] = [
# Gaps between keywords are bounded (.{0,200}, not .*): an unbounded gap made crafted 20k-character input cost
# ~1 s of CPU per request through quadratic backtracking (security audit SEC-13).
    ("continue_previous", re.compile(r"\b(continue|resume)\b.{0,200}\b(previous|last|earlier)\b|ادامه\s*(کار|تحقیق)?\s*(قبلی)?", re.I)),
    ("claims_from_page", re.compile(r"\bclaims?\b.{0,200}\b(from|on)\s+page\s+\d+|ادعا.{0,200}صفحه\s*[\d۰-۹]+", re.I)),
    ("unsupported_statements", re.compile(r"\bunsupported\b.{0,200}\b(statement|sentence|claim)s?\b|بدون\s*(منبع|پشتوانه)", re.I)),
    ("reprocess_document", re.compile(r"\b(reprocess|re-process|re-extract|extract again)\b|پردازش\s*مجدد", re.I)),
    ("section_applicability", re.compile(r"\b(section)\b.{0,200}\b(appl(y|ies|icable)|all topics)\b|بخش.{0,200}(همه|تمام)\s*(موضوعات|موارد)", re.I)),
    ("matrix_cell_research", re.compile(r"\b(matrix|empty)\s+cell\b|خانه\s*(خالی|ماتریس)", re.I)),
    ("contradictions", re.compile(r"\b(contradict\w*|conflict\w*|disagree\w*)\b|تناقض|تعارض", re.I)),
    ("find_evidence_for_claim", re.compile(r"\b(evidence|support|source)s?\s+for\s+(this|the)\s+claim\b|شواهد.{0,200}ادعا", re.I)),
    ("coverage_audit", re.compile(r"\bcoverage\b|پوشش", re.I)),
    ("evidence_research", re.compile(r"\b(stud(y|ies)|trials?|evidence|research|analy[sz]e)\b|مطالعات|شواهد|تحقیق|بررسی", re.I)),
    ("synthesis", re.compile(r"\b(summar\w+|synthes\w+|write|draft|overview)\b|خلاصه|جمع‌?بندی|بنویس", re.I)),
]
STOP = {"the", "and", "for", "all", "about", "find", "analyze", "analyse", "studies", "study", "show", "this",
        "that", "with", "from", "after", "before", "into", "their", "any", "what", "which", "are", "is", "on", "of",
        "in", "to", "a", "an", "evidence", "research", "compare", "human"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse(text: str) -> dict:
    """Proposed intent + hints, from the words alone. Never authoritative (see module docstring)."""
    t = text or ""
    intent = next((name for name, rx in RULES if rx.search(t)), "unknown")
    hints: dict = {}
    page = re.search(r"page\s+(\d+)|صفحه\s*([\d۰-۹]+)", t, re.I)
    if page:
        raw = page.group(1) or page.group(2)
        hints["page"] = int(raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
    after = re.search(r"\b(after|since|from)\s+((?:19|20)\d{2})\b", t, re.I)
    if after:
        hints["published_after"] = int(after.group(2))
    if re.search(r"\bhuman|clinical|patients?|انسان|بالینی", t, re.I):
        hints["population"] = "human"
    if re.search(r"\b(direct)\b", t, re.I) and not re.search(r"\bindirect\b", t, re.I):
        hints["directness"] = "direct"
    words = [w for w in re.findall(r"[A-Za-z؀-ۿ]{4,}", t) if w.lower() not in STOP]
    hints["terms"] = list(dict.fromkeys(w.lower() for w in words))[:8]
    return {"intent": intent, "hints": hints,
            "note": "Proposed from the words typed. Check the intent and the scope before running."}


# ---------------------------------------------------------------------- ownership
def get_command(db: Session, *, organization_id: UUID, user_id: UUID, command_id: UUID) -> WorkspaceCommand:
    """§64 — a command is visible only to its author. Another user's command is indistinguishable from one
    that does not exist (404), so ids cannot be probed."""
    cmd = db.execute(select(WorkspaceCommand).where(
        WorkspaceCommand.id == command_id, WorkspaceCommand.organization_id == organization_id,
        WorkspaceCommand.user_id == user_id)).scalar_one_or_none()
    if cmd is None:
        raise HTTPException(404, "Command not found.")
    return cmd


def get_version(db: Session, cmd: WorkspaceCommand, version: int | None = None) -> WorkspaceCommandVersion:
    v = db.execute(select(WorkspaceCommandVersion).where(
        WorkspaceCommandVersion.command_id == cmd.id,
        WorkspaceCommandVersion.version == (version or cmd.current_version))).scalar_one_or_none()
    if v is None:
        raise HTTPException(404, "Version not found.")
    return v


def _check_scope_refs(db: Session, organization_id: UUID, *, knowledge_object_id: UUID | None,
                      category_id: UUID | None) -> None:
    from app.models.knowledge_schema import Category

    if knowledge_object_id is not None and db.execute(select(KnowledgeObject.id).where(
            KnowledgeObject.id == knowledge_object_id,
            KnowledgeObject.organization_id == organization_id)).scalar_one_or_none() is None:
        raise HTTPException(404, "Knowledge object not found.")
    if category_id is not None and db.execute(select(Category.id).where(
            Category.id == category_id, Category.organization_id == organization_id)).scalar_one_or_none() is None:
        raise HTTPException(404, "Category not found.")


# ---------------------------------------------------------------------- drafts and versions (§48, §49)
def create(db: Session, *, organization_id: UUID, user_id: UUID, text: str = "", title: str | None = None,
           knowledge_object_id: UUID | None = None, category_id: UUID | None = None,
           scope: dict | None = None) -> WorkspaceCommand:
    _check_scope_refs(db, organization_id, knowledge_object_id=knowledge_object_id, category_id=category_id)
    cmd = WorkspaceCommand(organization_id=organization_id, user_id=user_id, title=(title or text[:80] or None),
                           knowledge_object_id=knowledge_object_id, category_id=category_id, state="draft",
                           current_version=1, last_activity_at=_now())
    db.add(cmd)
    db.flush()
    db.add(WorkspaceCommandVersion(organization_id=organization_id, command_id=cmd.id, version=1, text=text,
                                   draft_revision=1, scope=scope or {}, execution_state="draft",
                                   intent=parse(text)["intent"] if text.strip() else None))
    db.commit()
    db.refresh(cmd)
    return cmd


def save_draft(db: Session, cmd: WorkspaceCommand, *, text: str, base_revision: int | None,
               scope: dict | None = None, selected_source_ids: list | None = None, attachments: list | None = None,
               model_config: dict | None = None, budget: dict | None = None,
               intent: str | None = None) -> WorkspaceCommandVersion:
    """Autosave. Editing a version that has already run starts the next version instead (§49). A draft saved
    from a stale tab (older `base_revision`) is refused with 409 rather than overwriting newer text."""
    if cmd.archived_at is not None:
        raise HTTPException(409, "This command is archived; restore it before editing.")
    if intent is not None and intent not in INTENTS:
        raise HTTPException(422, f"Unknown intent {intent!r}.")
    current = get_version(db, cmd)
    if current.executed_at is not None:
        current = WorkspaceCommandVersion(
            organization_id=cmd.organization_id, command_id=cmd.id, version=cmd.current_version + 1,
            text=current.text, draft_revision=0, scope=dict(current.scope or {}),
            selected_source_ids=list(current.selected_source_ids or []), attachments=list(current.attachments or []),
            model_config_=dict(current.model_config_ or {}), budget=dict(current.budget or {}),
            execution_state="draft", intent=current.intent)
        db.add(current)
        cmd.current_version += 1
        db.flush()
    elif base_revision is not None and base_revision != current.draft_revision:
        raise HTTPException(409, {"message": "This draft was changed elsewhere since you loaded it.",
                                  "server_revision": current.draft_revision, "server_text": current.text})
    current.text = text
    current.draft_revision += 1
    if scope is not None:
        current.scope = scope
    if selected_source_ids is not None:
        current.selected_source_ids = [str(x) for x in selected_source_ids]
    if attachments is not None:
        current.attachments = [str(x) for x in attachments]
    if model_config is not None:
        current.model_config_ = model_config
    if budget is not None:
        current.budget = budget
    current.intent = intent or (parse(text)["intent"] if text.strip() else None)
    current.plan = None                                 # an edited command must be planned again
    cmd.state = "draft" if cmd.state in TERMINAL or cmd.state == "draft" else cmd.state
    cmd.title = cmd.title or text[:80] or None
    cmd.last_activity_at = _now()
    db.commit()
    db.refresh(current)
    return current


def restore(db: Session, cmd: WorkspaceCommand, version: int) -> WorkspaceCommandVersion:
    """Restore = a NEW draft version copying an old one. History is never rewritten."""
    old = get_version(db, cmd, version)
    current = get_version(db, cmd)
    if current.executed_at is None and current.version != version:
        target = current
    else:
        target = WorkspaceCommandVersion(organization_id=cmd.organization_id, command_id=cmd.id,
                                         version=cmd.current_version + 1, draft_revision=0, execution_state="draft")
        db.add(target)
        cmd.current_version += 1
    target.text, target.scope, target.intent = old.text, dict(old.scope or {}), old.intent
    target.selected_source_ids, target.attachments = list(old.selected_source_ids or []), list(old.attachments or [])
    target.model_config_, target.budget = dict(old.model_config_ or {}), dict(old.budget or {})
    target.draft_revision = (target.draft_revision or 0) + 1
    target.plan = None
    cmd.state = "draft"
    cmd.last_activity_at = _now()
    db.commit()
    db.refresh(target)
    return target


def compare(db: Session, cmd: WorkspaceCommand, a: int, b: int) -> dict:
    va, vb = get_version(db, cmd, a), get_version(db, cmd, b)
    diff = list(difflib.unified_diff(va.text.splitlines(), vb.text.splitlines(), f"v{a}", f"v{b}", lineterm=""))
    scope_changes = {k: {"from": (va.scope or {}).get(k), "to": (vb.scope or {}).get(k)}
                     for k in set(va.scope or {}) | set(vb.scope or {}) if (va.scope or {}).get(k) != (vb.scope or {}).get(k)}
    return {"a": a, "b": b, "text_diff": diff, "scope_changes": scope_changes,
            "intent": {"from": va.intent, "to": vb.intent},
            "results": {"a": va.execution_state, "b": vb.execution_state}}


# ---------------------------------------------------------------------- plan (§52, §53)
def plan(db: Session, cmd: WorkspaceCommand) -> WorkspaceCommandVersion:
    """Resolve intent + scope into an explicit plan, saved on the version and shown before anything runs.
    For AI intents this includes the synthesis plan: packs, calls, cost estimate, any blocking budget."""
    from app.services import synthesis_service

    v = get_version(db, cmd)
    if v.executed_at is not None:
        raise HTTPException(409, "This version has already run; edit it to create the next version.")
    parsed = parse(v.text)
    intent = v.intent or parsed["intent"]
    scope = {**parsed["hints"], **(v.scope or {})}
    ko = scope.get("knowledge_object_id") or (str(cmd.knowledge_object_id) if cmd.knowledge_object_id else None)
    if ko:
        scope["knowledge_object_id"] = ko
    if cmd.category_id and not scope.get("category_id"):
        scope["category_id"] = str(cmd.category_id)
    needs = _required_scope(intent)
    missing = [k for k in needs if not scope.get(k)]
    detail: dict = {"intent": intent, "proposed_intent": parsed["intent"], "scope": scope,
                    "missing_scope": missing, "runs_a_model": intent in AI_INTENTS,
                    "description": DESCRIPTIONS.get(intent, "")}
    if intent in AI_INTENTS and not missing:
        budgets = Budgets(**{k: v.budget[k] for k in ("context_tokens", "max_output_tokens", "max_calls", "max_cost")
                             if k in (v.budget or {})})
        dry = synthesis_service.create_run(
            db, organization_id=cmd.organization_id, user_id=cmd.user_id,
            knowledge_object_id=UUID(scope["knowledge_object_id"]), task=v.text, budgets=budgets,
            policy_id=UUID(v.model_config_["policy_id"]) if (v.model_config_ or {}).get("policy_id") else None,
            section_key=scope.get("section_key"), directness=scope.get("directness"),
            terms=_terms(scope), plan_only=True)
        detail["synthesis_plan"] = {"run_id": str(dry.id), "units": dry.input_units, **(dry.plan or {}),
                                    "scope_applied": dry.scope}
    v.intent = intent
    v.scope = scope
    v.plan = detail
    cmd.last_activity_at = _now()
    db.commit()
    db.refresh(v)
    return v


def _terms(scope: dict) -> list[str]:
    terms = list(scope.get("terms") or [])
    if scope.get("population") == "human":
        terms = list(dict.fromkeys([*terms, "human"]))
    return terms


def _required_scope(intent: str) -> list[str]:
    return {"claims_from_page": ["document_id", "page"], "reprocess_document": ["document_id"],
            "unsupported_statements": ["knowledge_object_id"], "contradictions": ["knowledge_object_id"],
            "section_applicability": ["category_id", "section_key"],
            "matrix_cell_research": ["knowledge_object_id", "section_key"],
            "find_evidence_for_claim": ["claim_id"], "coverage_audit": ["knowledge_object_id"],
            "evidence_research": ["knowledge_object_id"], "synthesis": ["knowledge_object_id"],
            "continue_previous": [], "unknown": ["intent"]}.get(intent, [])


DESCRIPTIONS = {
    "claims_from_page": "List every claim whose evidence was recorded as read on that page. No model.",
    "unsupported_statements": "List publication sentences with no validated source. No model.",
    "contradictions": "List recorded conflicts and claims with evidence on both sides. No model.",
    "section_applicability": "Show how a section applies across every topic in the category. No model.",
    "find_evidence_for_claim": "Report the evidence already linked to the claim. No model.",
    "coverage_audit": "Run the six-dimension coverage audit for the topic. No model.",
    "reprocess_document": "Queue a new extraction of the retained original; the current one stays until it succeeds.",
    "evidence_research": "Synthesise the evidence in scope with context packs and a coverage audit. Uses a model.",
    "synthesis": "Synthesise the knowledge in scope with context packs and a coverage audit. Uses a model.",
    "matrix_cell_research": "Synthesise what the topic holds for one matrix section. Uses a model.",
    "continue_previous": "Resume your most recent unfinished command.",
    "unknown": "The intent could not be determined from the text. Choose one before running.",
}


# ---------------------------------------------------------------------- run (§50)
def start(db: Session, cmd: WorkspaceCommand) -> WorkspaceCommandVersion:
    v = get_version(db, cmd)
    if v.executed_at is not None:
        raise HTTPException(409, "This version has already run. Use regenerate to run it again as a new version.")
    if v.plan is None:
        plan(db, cmd)
        v = get_version(db, cmd)
    if v.plan["missing_scope"]:
        raise HTTPException(422, {"message": "The scope is incomplete; it must be explicit before running.",
                                  "missing_scope": v.plan["missing_scope"]})
    v.executed_at = _now()
    v.execution_state = "queued"
    cmd.state = "queued"
    cmd.last_executed_version = v.version
    cmd.error = None
    cmd.last_activity_at = _now()
    record_audit_log(db, organization_id=cmd.organization_id, user_id=cmd.user_id, action="workspace.command_run",
                     resource_type="workspace_command", resource_id=cmd.id,
                     new_value={"version": v.version, "intent": v.intent})
    db.commit()
    db.refresh(v)
    return v


def regenerate(db: Session, cmd: WorkspaceCommand) -> WorkspaceCommandVersion:
    """Run the same request again as a NEW version, so both results stay side by side."""
    last = get_version(db, cmd, cmd.last_executed_version or cmd.current_version)
    nv = WorkspaceCommandVersion(organization_id=cmd.organization_id, command_id=cmd.id,
                                 version=cmd.current_version + 1, text=last.text, draft_revision=1,
                                 scope=dict(last.scope or {}), selected_source_ids=list(last.selected_source_ids or []),
                                 attachments=list(last.attachments or []), model_config_=dict(last.model_config_ or {}),
                                 budget=dict(last.budget or {}), intent=last.intent, execution_state="draft")
    db.add(nv)
    cmd.current_version += 1
    db.commit()
    return start(db, cmd)


def _finish(db: Session, cmd: WorkspaceCommand, v: WorkspaceCommandVersion, state: str, *, result: dict | None = None,
            error: str | None = None) -> dict:
    # results carry datetimes and UUIDs (audit timestamps, run ids); stored as JSON-safe values
    v.execution_state, v.result, v.error = state, jsonable_encoder(result) if result is not None else None, error
    if state in TERMINAL or state == "blocked":
        v.finished_at = _now()
    cmd.state, cmd.error = state, error if state in ("failed", "blocked") else None
    cmd.last_activity_at = _now()
    db.commit()
    return {"command_id": str(cmd.id), "version": v.version, "state": state}


def execute(db: Session, *, command_id: UUID, version: int) -> dict:
    """Worker body. Every outcome — including 'nothing to do' and 'blocked by budget' — is written to the
    version, so a person who closed the page finds exactly what happened."""
    from app.services import (
        coverage_audit_service, ingestion_job_service, ingestion_service, knowledge_query_service as kq,
        synthesis_service,
    )

    cmd = db.get(WorkspaceCommand, command_id)
    if cmd is None:
        return {"skipped": True}
    v = get_version(db, cmd, version)
    if v.execution_state in TERMINAL:
        return {"skipped": True, "state": v.execution_state}
    org, s = cmd.organization_id, v.scope or {}
    v.execution_state, cmd.state = "running", "running"
    db.commit()
    try:
        intent = v.intent
        if intent == "claims_from_page":
            return _finish(db, cmd, v, "completed", result=kq.claims_on_page(
                db, organization_id=org, document_id=UUID(s["document_id"]), page=int(s["page"])))
        if intent == "unsupported_statements":
            return _finish(db, cmd, v, "completed", result=kq.unsupported_statements(
                db, organization_id=org, knowledge_object_id=UUID(s["knowledge_object_id"]),
                publication_id=UUID(s["publication_id"]) if s.get("publication_id") else None))
        if intent == "contradictions":
            return _finish(db, cmd, v, "completed", result=kq.contradictions(
                db, organization_id=org, knowledge_object_id=UUID(s["knowledge_object_id"])))
        if intent == "section_applicability":
            return _finish(db, cmd, v, "completed", result=kq.section_applicability(
                db, organization_id=org, category_id=UUID(s["category_id"]), section_key=s["section_key"]))
        if intent == "find_evidence_for_claim":
            return _finish(db, cmd, v, "completed", result=kq.claim_evidence(
                db, organization_id=org, claim_id=UUID(s["claim_id"])))
        if intent == "coverage_audit":
            audit = coverage_audit_service.run_topic_audit(db, organization_id=org,
                                                           knowledge_object_id=UUID(s["knowledge_object_id"]),
                                                           trigger="workspace")
            return _finish(db, cmd, v, "completed" if audit.status == "succeeded" else "failed",
                           result=coverage_audit_service.audit_out(audit),
                           error=audit.failure_reason if audit.status != "succeeded" else None)
        if intent == "reprocess_document":
            conv = ingestion_service.create_reprocess_conversion(db, organization_id=org,
                                                                 document_id=UUID(s["document_id"]),
                                                                 actor_user_id=cmd.user_id, trigger="workspace")
            job, _ = ingestion_job_service.create_ingestion_job(
                db, organization_id=org, site_id=None, document_id=UUID(s["document_id"]), conversion_id=conv.id,
                source_hash=conv.source_hash, actor_user_id=cmd.user_id, idempotency_key=f"reprocess:{conv.id}")
            v.sync_job_id = job.id
            db.commit()
            from app.workers.tasks import ingest_document_job
            try:
                ingest_document_job.delay(str(job.id))
            except Exception:  # noqa: BLE001 — the job row survives; the sweeper reclaims it
                pass
            db.refresh(job)
            state = "completed" if job.status.value == "succeeded" else "running"
            return _finish(db, cmd, v, state, result={"conversion_id": str(conv.id), "job_id": str(job.id),
                                                      "job_status": job.status.value})
        if intent == "continue_previous":
            prev = db.execute(select(WorkspaceCommand).where(
                WorkspaceCommand.organization_id == org, WorkspaceCommand.user_id == cmd.user_id,
                WorkspaceCommand.id != cmd.id, WorkspaceCommand.state.in_(("blocked", "running", "queued")),
                WorkspaceCommand.archived_at.is_(None)).order_by(WorkspaceCommand.last_activity_at.desc())).scalars().first()
            if prev is None:
                return _finish(db, cmd, v, "completed", result={"resumed": None,
                                                                "note": "You have no unfinished command to continue."})
            outcome = resume(db, prev)
            return _finish(db, cmd, v, "completed", result={"resumed": str(prev.id), "outcome": outcome})
        if intent in AI_INTENTS:
            budgets = Budgets(**{k: v.budget[k] for k in ("context_tokens", "max_output_tokens", "max_calls",
                                                          "max_cost") if k in (v.budget or {})})
            run = synthesis_service.create_run(
                db, organization_id=org, user_id=cmd.user_id, knowledge_object_id=UUID(s["knowledge_object_id"]),
                task=v.text, budgets=budgets,
                policy_id=UUID(v.model_config_["policy_id"]) if (v.model_config_ or {}).get("policy_id") else None,
                section_key=s.get("section_key"), directness=s.get("directness"), terms=_terms(s),
                allow_partial=bool((v.budget or {}).get("allow_partial")))
            v.synthesis_run_id = run.id
            db.commit()
            if run.status == "queued":
                run = synthesis_service.advance(db, run)
            return _sync_from_run(db, cmd, v, run)
        return _finish(db, cmd, v, "blocked", error="The intent could not be determined; choose one and run again.")
    except HTTPException as exc:
        db.rollback()
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return _finish(db, cmd, v, "failed", error=detail[:2000])
    except Exception as exc:  # noqa: BLE001 — a crash is recorded, never left as "running"
        db.rollback()
        return _finish(db, cmd, v, "failed", error=f"{type(exc).__name__}: {exc}"[:2000])


def _run_cost(db: Session, run: SynthesisRun) -> dict:
    total = 0.0
    unknown = 0
    for key in run.ai_job_keys or []:
        job = db.execute(select(AIJob).where(AIJob.organization_id == run.organization_id,
                                             AIJob.job_key == key)).scalar_one_or_none()
        if job is None:
            continue
        for e in db.execute(select(AIExecution).where(AIExecution.ai_job_id == job.id)).scalars():
            if e.estimated_provider_cost is None:
                unknown += 1
            else:
                total += float(e.estimated_provider_cost)
    return {"estimated": round(total, 6), "executions_with_unknown_cost": unknown,
            "note": "Estimated from configured prices; an execution without a known price is counted, not zeroed."}


def _sync_from_run(db: Session, cmd: WorkspaceCommand, v: WorkspaceCommandVersion, run: SynthesisRun) -> dict:
    from app.services import synthesis_service

    v.cost = _run_cost(db, run)
    out = synthesis_service.run_out(run)
    state = {"completed": "completed", "completed_with_gaps": "completed_with_gaps", "blocked": "blocked",
             "failed": "failed", "cancelled": "cancelled"}.get(run.status, "running")
    return _finish(db, cmd, v, state, result=out, error=run.failure_reason if state in ("blocked", "failed") else None)


def resume(db: Session, cmd: WorkspaceCommand) -> dict:
    """§50 — continue a command whose model work stopped (provider limit, budget raised, worker died).
    Completed items are not redone; the synthesis resumes from its last checkpoint."""
    from app.services import synthesis_service

    v = get_version(db, cmd, cmd.last_executed_version or cmd.current_version)
    if v.synthesis_run_id is None:
        if cmd.state in ("queued", "running") and v.executed_at is not None:
            return execute(db, command_id=cmd.id, version=v.version)
        raise HTTPException(409, "Nothing to resume: this command has no unfinished model work.")
    run = db.get(SynthesisRun, v.synthesis_run_id)
    if run.status in ("completed", "completed_with_gaps", "cancelled", "failed"):
        return _sync_from_run(db, cmd, v, run)
    if not run.ai_job_keys:
        raise HTTPException(409, "This run was blocked before any model call (budget or scope); edit and run again.")
    job = db.execute(select(AIJob).where(AIJob.organization_id == run.organization_id,
                                         AIJob.job_key == run.ai_job_keys[-1])).scalar_one()
    if job.status in ("blocked", "paused"):
        job.status = "queued"
    run.status, run.failure_reason = "queued", None
    v.execution_state, cmd.state = "running", "running"
    db.commit()
    run = synthesis_service.advance(db, run)
    return _sync_from_run(db, cmd, v, run)


def cancel(db: Session, cmd: WorkspaceCommand) -> dict:
    from app.services import ai_job_service

    v = get_version(db, cmd, cmd.last_executed_version or cmd.current_version)
    if v.execution_state in TERMINAL:
        raise HTTPException(409, f"This version is already {v.execution_state}.")
    if v.synthesis_run_id is not None:
        run = db.get(SynthesisRun, v.synthesis_run_id)
        for key in run.ai_job_keys or []:
            job = db.execute(select(AIJob).where(AIJob.organization_id == run.organization_id,
                                                 AIJob.job_key == key)).scalar_one_or_none()
            if job is not None and job.status not in ("completed", "completed_with_failures", "cancelled"):
                ai_job_service.request_control(db, job, "cancel")
        if run.status not in ("completed", "completed_with_gaps", "failed"):
            run.status = "cancelled"
    return _finish(db, cmd, v, "cancelled", result=v.result)


# ---------------------------------------------------------------------- serialisation
def version_out(v: WorkspaceCommandVersion) -> dict:
    return {"version": v.version, "text": v.text, "draft_revision": v.draft_revision, "intent": v.intent,
            "scope": v.scope, "selected_source_ids": v.selected_source_ids, "attachments": v.attachments,
            "model_config": v.model_config_, "budget": v.budget, "plan": v.plan,
            "execution_state": v.execution_state, "executed_at": v.executed_at, "finished_at": v.finished_at,
            "result": v.result, "error": v.error, "cost": v.cost,
            "synthesis_run_id": str(v.synthesis_run_id) if v.synthesis_run_id else None,
            "sync_job_id": str(v.sync_job_id) if v.sync_job_id else None, "created_at": v.created_at,
            "updated_at": v.updated_at, "frozen": v.executed_at is not None}


def command_out(db: Session, cmd: WorkspaceCommand, *, with_version: bool = True) -> dict:
    out = {"id": str(cmd.id), "title": cmd.title, "state": cmd.state, "current_version": cmd.current_version,
           "last_executed_version": cmd.last_executed_version, "error": cmd.error,
           "knowledge_object_id": str(cmd.knowledge_object_id) if cmd.knowledge_object_id else None,
           "category_id": str(cmd.category_id) if cmd.category_id else None,
           "archived": cmd.archived_at is not None, "archived_at": cmd.archived_at,
           "last_activity_at": cmd.last_activity_at, "created_at": cmd.created_at, "updated_at": cmd.updated_at,
           "resumable": cmd.state in ("queued", "running", "blocked")}
    if with_version:
        out["current"] = version_out(get_version(db, cmd))
    return out
