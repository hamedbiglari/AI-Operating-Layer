"""
AI jobs: long multi-item workloads that survive provider limits
(REQ-AIC-004/005, ADR-090). Example: 100 documents, account A stops at 50 →
checkpoint + handoff persisted → account B continues the remaining 50.

Canonical progress lives in ai_job_items (relational, queryable). The
checkpoint and handoff package are written to shared working memory BEFORE any
switch, so the next resource never starts from zero. Every provider call goes
through the locked invocation wrapper and is exactly one AIExecution; a switch
creates a NEW execution linked with previous_execution_id.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.invocation import InvocationContext, ModelTarget, invoke_once
from app.ai.pricing import ConfiguredPricing, reservation_upper_bound
from app.integrations.llm.base import ModelRequest
from app.models.ai_center import AIJob, AIJobItem, AIProvider, AIProviderAccount, AIRoutingPolicy, AIRoutingStep
from app.models.ai_execution import AIExecution
from app.models.enums import AIAttemptReason, AIParentType
from app.services import ai_center_service, ai_memory_service as memory
from app.services.ai_routing_service import decide

# A stop that means "this resource can't continue" -> checkpoint, handoff, switch.
SWITCH_STOPS = {"RATE_LIMIT", "QUOTA_EXHAUSTED", "AUTHENTICATION_FAILED", "PROVIDER_UNAVAILABLE",
                "PROVIDER_TIMEOUT", "PROVIDER_INTERNAL_ERROR", "SPEND_LIMIT"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(db: Session, *, organization_id: UUID, job_key: str, goal: str, policy_id: UUID, items: list[dict],
               stage: str | None = None, user_id: UUID | None = None, knowledge_object_id: UUID | None = None,
               max_output_tokens: int = 400, task_type: str | None = None) -> tuple[AIJob, bool]:
    """Idempotent on (organization, job_key)."""
    existing = db.execute(select(AIJob).where(AIJob.organization_id == organization_id, AIJob.job_key == job_key)).scalar_one_or_none()
    if existing is not None:
        return existing, False
    ai_center_service.get_or_404(db, AIRoutingPolicy, policy_id, organization_id)
    job = AIJob(organization_id=organization_id, job_key=job_key, goal=goal, stage=stage, policy_id=policy_id,
                task_type=task_type,
                status="queued", created_by_user_id=user_id, knowledge_object_id=knowledge_object_id,
                max_output_tokens=max_output_tokens)
    db.add(job)
    db.flush()
    for i, it in enumerate(items):
        db.add(AIJobItem(organization_id=organization_id, job_id=job.id, item_key=str(it["key"]), position=i,
                         prompt=it["prompt"], source_id=it.get("source_id"), document_id=it.get("document_id")))
    memory.write(db, organization_id=organization_id, job_key=job_key, kind="job_state", created_by=f"user:{user_id}",
                 stage=stage, commit=False, content={"status": "queued", "goal": goal, "total_items": len(items)})
    db.commit()
    return job, True


def _counts(db: Session, job: AIJob) -> dict:
    rows = db.execute(select(AIJobItem.status, func.count()).where(AIJobItem.job_id == job.id).group_by(AIJobItem.status)).all()
    c = {"pending": 0, "completed": 0, "failed": 0}
    c.update({s: n for s, n in rows})
    c["total"] = sum(c.values())
    return c


def _job_cost(db: Session, job: AIJob) -> Decimal:
    return Decimal(db.execute(select(func.sum(AIExecution.estimated_provider_cost)).where(
        AIExecution.organization_id == job.organization_id, AIExecution.ai_job_id == job.id)).scalar_one() or 0)


def build_handoff(db: Session, job: AIJob, *, last: AIExecution | None, failure_reason: str | None,
                  excluded: set) -> dict:
    items = db.execute(select(AIJobItem).where(AIJobItem.job_id == job.id).order_by(AIJobItem.position)).scalars().all()
    execs = db.execute(select(AIExecution.id).where(AIExecution.organization_id == job.organization_id,
                                                    AIExecution.ai_job_id == job.id).order_by(AIExecution.started_at)).scalars().all()
    findings, _ = memory.list_items(db, organization_id=job.organization_id, job_key=job.job_key, kind="intermediate_finding", limit=10000)
    c = _counts(db, job)
    return {
        "goal": job.goal, "current_stage": job.stage,
        "completed_items": [i.item_key for i in items if i.status == "completed"],
        "pending_items": [i.item_key for i in items if i.status == "pending"],
        "failed_items": [{"item": i.item_key, "reason": i.failure_reason} for i in items if i.status == "failed"],
        "processed_count": c["completed"] + c["failed"], "total_count": c["total"],
        "finding_memory_ids": [str(f.id) for f in findings],
        "previous_executions": [str(e) for e in execs],
        "last_provider": last.provider if last else None, "last_model": last.model if last else None,
        "last_account_id": str(last.provider_account_id) if last and last.provider_account_id else None,
        "failure_reason": failure_reason, "excluded_accounts": sorted(str(a) for a in excluded),
        "job_cost_estimated": str(_job_cost(db, job)),
        "next_actions": ["continue pending items with the next routed resource"] if c["pending"] else ["synthesize"],
        "checkpoint_time": _now().isoformat(),
    }


def _count_event(job, reason: str) -> None:
    """§32 observability: how often this job had to switch resource or retry."""
    if reason == "manual switch":
        job.switch_count = (job.switch_count or 0) + 1
    else:
        job.switch_count = (job.switch_count or 0) + 1
        job.retry_count = (job.retry_count or 0) + 1   # the work is re-attempted on the next resource


def _checkpoint(db: Session, job: AIJob, *, last: AIExecution | None, reason: str | None, excluded: set,
                handoff: bool) -> dict:
    _count_event(job, reason)
    pkg = build_handoff(db, job, last=last, failure_reason=reason, excluded=excluded)
    memory.write(db, organization_id=job.organization_id, job_key=job.job_key, kind="processing_checkpoint",
                 created_by="system", stage=job.stage, content=pkg, commit=False)
    if handoff:
        memory.write(db, organization_id=job.organization_id, job_key=job.job_key, kind="ai_handoff",
                     created_by="system", stage=job.stage, content=pkg, commit=False)
    db.commit()
    return pkg


def request_control(db: Session, job: AIJob, action: str, *, account_id: UUID | None = None) -> AIJob:
    """pause | cancel | switch — takes effect at the next item boundary, after a checkpoint."""
    if action == "pause":
        job.status = "pause_requested" if job.status == "running" else ("paused" if job.status == "queued" else job.status)
    elif action == "cancel":
        job.status = "cancel_requested" if job.status == "running" else "cancelled"
    elif action == "switch":
        step = db.execute(select(AIRoutingStep).where(AIRoutingStep.policy_id == job.policy_id,
                                                      AIRoutingStep.account_id == account_id)).scalar_one_or_none()
        if step is None:
            raise ValueError("that account is not part of this job's routing policy")
        job.forced_account_id = account_id
    memory.write(db, organization_id=job.organization_id, job_key=job.job_key, kind="next_action", created_by="user",
                 content={"action": action, "account_id": str(account_id) if account_id else None, "at": _now().isoformat()},
                 commit=False)
    db.commit()
    return job


def run_job(db: Session, job: AIJob, *, adapters: dict | None = None, pricing=None,  # noqa: ANN001
            restrict_to_accounts: set | None = None) -> dict:
    """Process pending items until done, blocked, paused or cancelled.
    `adapters` maps account_id -> adapter (tests only); production resolves
    each account's own encrypted credential."""
    org = job.organization_id
    policy = db.get(AIRoutingPolicy, job.policy_id)
    ckpt = memory.latest(db, organization_id=org, job_key=job.job_key, kind="processing_checkpoint")
    # On resume, an account stays excluded only while it is still unusable
    # (e.g. a rotated credential or an elapsed rate-limit window re-admits it).
    excluded = set()
    for a in (ckpt.content.get("excluded_accounts", []) if ckpt else []):
        acc = db.get(AIProviderAccount, UUID(a))
        if acc is not None and (acc.health_status in ("auth_failed", "disconnected")
                                or (acc.unavailable_until and acc.unavailable_until > _now())):
            excluded.add(acc.id)
    # ── ADR-095 worker enforcement: background work obeys the tenant's policy ──
    forbidden: set = set()
    bg_cost_cap: Decimal | None = None
    if job.task_type:
        from app.services.background_policy_service import check_background_policy
        pd = check_background_policy(db, organization_id=org, task_type=job.task_type)
        if not pd.allowed:
            code = pd.reason.split(" ")[0][:40]
            job.status, job.stop_reason = "blocked", code
            memory.write(db, organization_id=org, job_key=job.job_key, kind="job_state", commit=False,
                         created_by="worker:background_policy",
                         content={"status": "blocked", "stop_reason": code, "detail": pd.reason,
                                  "task_type": job.task_type})
            db.commit()
            return {"status": "blocked", "stop_reason": code, **_counts(db, job)}
        from app.models.background_policy import BackgroundTaskPolicy as _BTP
        bgp = db.execute(select(_BTP).where(_BTP.organization_id == org, _BTP.task_type == job.task_type)).scalar_one()
        if bgp.routing_policy_id is not None:
            chosen_policy = db.get(AIRoutingPolicy, bgp.routing_policy_id)
            if chosen_policy is not None and chosen_policy.organization_id == org:
                policy = chosen_policy          # the tenant's background routing choice wins
        if bgp.max_cost_per_run is not None:
            bg_cost_cap = Decimal(str(bgp.max_cost_per_run))
        allowed = set(pd.allowed_account_ids)
        forbidden = {a for a in db.execute(select(AIProviderAccount.id).where(
            AIProviderAccount.organization_id == org)).scalars() if a not in allowed}
        if job.forced_account_id is not None and job.forced_account_id in forbidden:
            # A manual switch can never select a resource the policy forbids.
            job.forced_account_id = None
    if restrict_to_accounts is not None:
        # e.g. an Agent may only use the AI resources it declares (ADR-096)
        forbidden |= {a for a in db.execute(select(AIProviderAccount.id).where(
            AIProviderAccount.organization_id == org)).scalars() if a not in restrict_to_accounts}
    job.status = "running"
    db.commit()
    trigger = "resume" if ckpt else "initial"
    last: AIExecution | None = None

    def route(trigger_: str):  # noqa: ANN202
        return decide(db, organization_id=org, policy=policy, stage=job.stage, excluded=excluded, job_key=job.job_key,
                      job_cost_so_far=_job_cost(db, job), trigger=trigger_, forbidden=forbidden)

    decision = route(trigger)
    while True:
        db.refresh(job)
        if job.status in ("pause_requested", "cancel_requested"):
            job.status = "paused" if job.status == "pause_requested" else "cancelled"
            _checkpoint(db, job, last=last, reason=f"user {job.status}", excluded=excluded, handoff=False)
            db.commit()
            return {"status": job.status, **_counts(db, job)}
        if job.forced_account_id is not None:
            forced = job.forced_account_id
            job.forced_account_id = None
            excluded.discard(forced)
            _checkpoint(db, job, last=last, reason="manual switch", excluded=excluded, handoff=True)
            others = {s.account_id for s in db.execute(select(AIRoutingStep).where(
                AIRoutingStep.policy_id == policy.id, AIRoutingStep.account_id != forced)).scalars()}
            decision = decide(db, organization_id=org, policy=policy, stage=job.stage, excluded=excluded | others,
                              job_key=job.job_key, job_cost_so_far=_job_cost(db, job), trigger="manual_switch",
                              forbidden=forbidden)
        item = db.execute(select(AIJobItem).where(AIJobItem.job_id == job.id, AIJobItem.status == "pending")
                          .order_by(AIJobItem.position).limit(1)).scalar_one_or_none()
        if item is None:
            break
        if decision.chosen is None:
            job.status, job.stop_reason = "blocked", decision.stop_reason
            _checkpoint(db, job, last=last, reason=decision.stop_reason, excluded=excluded, handoff=True)
            return {"status": "blocked", "stop_reason": decision.stop_reason, **_counts(db, job)}
        c = decision.chosen
        # Cost gate BEFORE spending (REQ-AIC-012): worst-case estimate for this
        # item must fit the job budget; an unknown price under a budget stops.
        caps = [Decimal(str(policy.max_cost_per_job))] if policy.max_cost_per_job is not None else []
        if bg_cost_cap is not None:
            caps.append(bg_cost_cap)          # background policy's max cost per run (ADR-095)
        if caps:
            limit = min(caps)
            price = (pricing or ConfiguredPricing()).price(c.provider.adapter_key or c.provider.canonical_name, c.step.model)
            bound = reservation_upper_bound(price, prompt=item.prompt, max_output_tokens=job.max_output_tokens, attempts=1)
            if bound is None or _job_cost(db, job) + bound > limit:
                job.status, job.stop_reason = "blocked", "SPEND_LIMIT"
                _checkpoint(db, job, last=last, reason="SPEND_LIMIT" if bound is not None else "SPEND_LIMIT: price unknown",
                            excluded=excluded, handoff=True)
                return {"status": "blocked", "stop_reason": "SPEND_LIMIT", **_counts(db, job)}
        adapter = (adapters or {}).get(c.account.id)
        if adapter is None:
            adapter, why = ai_center_service.adapter_for(db, c.account)
            if adapter is None:
                excluded.add(c.account.id)
                decision = route(f"switch:{why}")
                continue
        prev = None
        reason = None
        if item.last_execution_id is not None:
            prev = db.get(AIExecution, item.last_execution_id)
            if prev is not None and prev.status == "succeeded":
                prev = None
        if prev is not None:
            if prev.provider != (c.provider.adapter_key or c.provider.canonical_name):
                reason = AIAttemptReason.PROVIDER_FALLBACK
            elif prev.provider_account_id != c.account.id:
                reason = AIAttemptReason.ACCOUNT_FALLBACK
            elif prev.model != c.step.model:
                reason = AIAttemptReason.MODEL_FALLBACK
            else:
                reason = AIAttemptReason.RETRY
        ctx = InvocationContext(organization_id=org, parent_type=AIParentType.AI_JOB, parent_id=job.id,
                                knowledge_object_id=job.knowledge_object_id, stage=job.stage, budget_cleared=True)
        out = invoke_once(db, ctx, ModelTarget(c.provider.adapter_key or c.provider.canonical_name, c.step.model),
                          ModelRequest(prompt=item.prompt, max_output_tokens=job.max_output_tokens),
                          adapter=adapter, pricing=pricing or ConfiguredPricing(), previous=prev, attempt_reason=reason,
                          provider_account_id=c.account.id)
        ex = out.execution
        last = ex
        item.last_execution_id = ex.id
        c.account.last_used_at = _now()
        if out.succeeded:
            item.status, item.completed_by_account_id, item.failure_reason = "completed", c.account.id, None
            if c.account.health_status != "healthy":
                ai_center_service.record_health(db, c.account, health="healthy", source="execution", execution_id=ex.id)
            memory.write(db, organization_id=org, job_key=job.job_key, kind="intermediate_finding",
                         created_by=f"execution:{ex.id}", stage=job.stage, item_key=item.item_key,
                         source_id=item.source_id, document_id=item.document_id, commit=False,
                         content={"item": item.item_key, "result": (out.result.text or "")[:4000]},
                         provenance={"execution_id": str(ex.id), "provider": ex.provider, "model": ex.model,
                                     "account_id": str(c.account.id)})
            db.commit()
            continue
        stop = ex.stop_reason or "UNKNOWN"
        if stop in SWITCH_STOPS:
            health, avoid = ai_center_service.HEALTH_FOR_STOP.get(stop, ("degraded", 60))
            ai_center_service.record_health(db, c.account, health=health, source="execution", code=ex.error_code,
                                            message=ex.error_message, execution_id=ex.id, avoid_seconds=avoid)
            excluded.add(c.account.id)
            # Persist everything BEFORE switching (REQ-AIC-005).
            _checkpoint(db, job, last=ex, reason=stop, excluded=excluded, handoff=True)
            decision = route(f"switch:{stop}")
            continue
        item.status, item.failure_reason = "failed", f"{stop}: {ex.error_message or ''}"[:300]
        db.commit()

    job.status, job.stop_reason = "completed", "COMPLETED"
    findings, n = memory.list_items(db, organization_id=org, job_key=job.job_key, kind="intermediate_finding", limit=10000)
    memory.write(db, organization_id=org, job_key=job.job_key, kind="current_synthesis", created_by="system", commit=False,
                 content={"method": "mechanical merge of per-item findings (not an AI synthesis)",
                          "items_with_findings": sorted({f.item_key for f in findings}), "finding_count": n})
    _checkpoint(db, job, last=last, reason=None, excluded=excluded, handoff=False)
    return {"status": "completed", **_counts(db, job)}
