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

import os
import socket
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.ai import prompt_safety
from app.core.config import settings
from app.services.audit import record_audit_log
from app.ai.invocation import InvocationContext, ModelTarget, invoke_once
from app.ai.pricing import ConfiguredPricing, reservation_upper_bound
from app.integrations.llm.base import ModelRequest
from app.models.ai_center import AIJob, AIJobItem, AIProvider, AIProviderAccount, AIRoutingPolicy, AIRoutingStep
from app.models.ai_execution import AIExecution
from app.models.enums import AIAttemptReason, AIParentType
from app.services import ai_center_service, ai_memory_service as memory
from app.services.ai_routing_service import decide, request_fit
from app.ai.context_assembly import estimate_tokens

# A stop that means "this resource can't continue" -> checkpoint, handoff, switch.
SWITCH_STOPS = {"RATE_LIMIT", "QUOTA_EXHAUSTED", "AUTHENTICATION_FAILED", "PROVIDER_UNAVAILABLE",
                "PROVIDER_TIMEOUT", "PROVIDER_INTERNAL_ERROR", "SPEND_LIMIT"}



def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(db: Session, *, organization_id: UUID, job_key: str, goal: str, policy_id: UUID, items: list[dict],
               stage: str | None = None, user_id: UUID | None = None, knowledge_object_id: UUID | None = None,
               max_output_tokens: int = 400, task_type: str | None = None,
               output_contract: str | None = None) -> tuple[AIJob, bool]:
    """Idempotent on (organization, job_key)."""
    existing = db.execute(select(AIJob).where(AIJob.organization_id == organization_id, AIJob.job_key == job_key)).scalar_one_or_none()
    if existing is not None:
        return existing, False
    if output_contract is not None and knowledge_object_id is None:
        raise ValueError("a job with an output contract must name the knowledge object its findings belong to")
    validate_dependencies(items)
    ai_center_service.get_or_404(db, AIRoutingPolicy, policy_id, organization_id)
    job = AIJob(organization_id=organization_id, job_key=job_key, goal=goal, stage=stage, policy_id=policy_id,
                task_type=task_type, output_contract=output_contract,
                status="queued", created_by_user_id=user_id, knowledge_object_id=knowledge_object_id,
                max_output_tokens=max_output_tokens)
    db.add(job)
    db.flush()
    for i, it in enumerate(items):
        db.add(AIJobItem(organization_id=organization_id, job_id=job.id, item_key=str(it["key"]), position=i,
                         prompt=it["prompt"], source_id=it.get("source_id"), document_id=it.get("document_id"),
                         depends_on=[str(d) for d in it.get("depends_on") or []]))
    memory.write(db, organization_id=organization_id, job_key=job_key, kind="job_state", created_by=f"user:{user_id}",
                 stage=stage, commit=False, content={"status": "queued", "goal": goal, "total_items": len(items)})
    db.commit()
    return job, True


def validate_dependencies(items: list[dict]) -> None:
    """ADR-135: keys unique; every dependency names another item of the same job; no cycle (Kahn)."""
    keys = [str(it["key"]) for it in items]
    if len(set(keys)) != len(keys):
        raise ValueError("item keys must be unique within a job")
    deps = {str(it["key"]): {str(d) for d in it.get("depends_on") or []} for it in items}
    for k, ds in deps.items():
        if k in ds:
            raise ValueError(f"item {k!r} depends on itself")
        if unknown := sorted(ds - deps.keys()):
            raise ValueError(f"item {k!r} depends on unknown item(s) {unknown}")
    remaining = {k: set(ds) for k, ds in deps.items()}
    while ready := [k for k, ds in remaining.items() if not ds]:
        for k in ready:
            del remaining[k]
        for ds in remaining.values():
            ds.difference_update(ready)
    if remaining:
        raise ValueError(f"item dependencies form a cycle among {sorted(remaining)}")


def _next_item(db: Session, job: AIJob) -> AIJobItem | None:
    """The lowest-position pending item whose dependencies have all completed (ADR-135).

    A pending item with a failed dependency can never run: it is failed with DEPENDENCY_FAILED, transitively,
    so the job ends `completed_with_failures` instead of waiting for ever. Because the graph is acyclic, while
    any item is pending at least one of them is runnable or gets failed here."""
    status = dict(db.execute(select(AIJobItem.item_key, AIJobItem.status).where(AIJobItem.job_id == job.id)).all())
    pending = db.execute(select(AIJobItem).where(AIJobItem.job_id == job.id, AIJobItem.status == "pending")
                         .order_by(AIJobItem.position)).scalars().all()
    changed = True
    while changed:
        changed = False
        for it in pending:
            failed = [d for d in it.depends_on if status.get(d) == "failed"]
            if it.status == "pending" and failed:
                it.status, it.failure_reason = "failed", f"DEPENDENCY_FAILED: {', '.join(failed)}"[:300]
                status[it.item_key], changed = "failed", True
    if any(it.status == "failed" for it in pending):
        db.commit()
    return next((it for it in pending if it.status == "pending"
                 and all(status.get(d) == "completed" for d in it.depends_on)), None)


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
    done = {i.item_key for i in items if i.status == "completed"}
    return {
        "goal": job.goal, "current_stage": job.stage,
        "completed_items": [i.item_key for i in items if i.status == "completed"],
        "pending_items": [i.item_key for i in items if i.status == "pending"],
        # ADR-135: which pending items still wait for which dependencies (only those that have any).
        "waiting_on": {i.item_key: [d for d in i.depends_on if d not in done]
                       for i in items if i.status == "pending" and any(d not in done for d in i.depends_on)},
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


# Health states that only pass with time; any other unusable state needs the user (e.g. a new credential).
_WAITABLE_HEALTH = ("rate_limited", "quota_exhausted", "unavailable", "timeout", "degraded")


def _lease_until() -> datetime:
    return _now() + timedelta(seconds=settings.AI_JOB_LEASE_SECONDS)


def _claim_lease(db: Session, job: AIJob, owner: str) -> bool:
    """Atomic: succeeds only if no other worker holds a live lease on this job (ADR-131)."""
    got = db.execute(update(AIJob).where(
        AIJob.id == job.id,
        or_(AIJob.lease_owner.is_(None), AIJob.lease_expires_at < _now(), AIJob.lease_owner == owner),
    ).values(lease_owner=owner, lease_expires_at=_lease_until()).returning(AIJob.id)
        .execution_options(synchronize_session=False)).first()
    db.commit()
    db.refresh(job)
    return got is not None


def _release_lease(db: Session, job: AIJob, owner: str) -> None:
    db.execute(update(AIJob).where(AIJob.id == job.id, AIJob.lease_owner == owner)
               .values(lease_owner=None, lease_expires_at=None).execution_options(synchronize_session=False))
    db.commit()
    db.refresh(job)


def _capacity_resume_time(db: Session, policy: AIRoutingPolicy, forbidden: set) -> datetime | None:
    """When the only thing stopping the job is a temporary provider limit, the earliest moment one of the
    policy's permitted resources is usable again. None means a person has to act."""
    return db.execute(select(func.min(AIProviderAccount.unavailable_until)).join(
        AIRoutingStep, AIRoutingStep.account_id == AIProviderAccount.id).where(
        AIRoutingStep.policy_id == policy.id, AIProviderAccount.enabled.is_(True),
        AIProviderAccount.health_status.in_(_WAITABLE_HEALTH), AIProviderAccount.unavailable_until > _now(),
        AIProviderAccount.id.notin_(forbidden) if forbidden else True)).scalar_one()


def run_job(db: Session, job: AIJob, *, adapters: dict | None = None, pricing=None,  # noqa: ANN001
            restrict_to_accounts: set | None = None) -> dict:
    """Process pending items until done, blocked, paused or cancelled.
    `adapters` maps account_id -> adapter (tests only); production resolves
    each account's own encrypted credential.

    ADR-131: the run holds a worker lease. A second worker on the same job is refused instead of
    processing items twice; a worker that dies leaves a lease that expires and `recover_jobs` re-queues."""
    owner = f"{socket.gethostname()}:{os.getpid()}:{_uuid.uuid4().hex[:8]}"
    if not _claim_lease(db, job, owner):
        return {"status": job.status, "stop_reason": "LEASED_BY_ANOTHER_WORKER", "lease_owner": job.lease_owner,
                **_counts(db, job)}
    try:
        result = _run_leased(db, job, owner, adapters=adapters, pricing=pricing,
                             restrict_to_accounts=restrict_to_accounts)
    except BaseException as exc:
        db.rollback()   # never commit a crashed item's half-done work along with the release
        # A code error is not a provider limit: retrying it automatically would loop, so a person decides.
        db.execute(update(AIJob).where(AIJob.id == job.id, AIJob.lease_owner == owner).values(
            status="blocked", stop_reason="WORKER_ERROR", resume_after=None).execution_options(synchronize_session=False))
        memory.write(db, organization_id=job.organization_id, job_key=job.job_key, kind="job_state",
                     created_by="system", commit=False,
                     content={"status": "blocked", "stop_reason": "WORKER_ERROR", "error": type(exc).__name__,
                              "at": _now().isoformat()})
        _release_lease(db, job, owner)
        raise
    _release_lease(db, job, owner)
    return result


def _run_leased(db: Session, job: AIJob, owner: str, *, adapters: dict | None, pricing,  # noqa: ANN001
                restrict_to_accounts: set | None) -> dict:
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
    job.status, job.resume_after = "running", None
    db.commit()
    trigger = "resume" if ckpt else "initial"
    last: AIExecution | None = None

    def route(trigger_: str):  # noqa: ANN202
        return decide(db, organization_id=org, policy=policy, stage=job.stage, excluded=excluded, job_key=job.job_key,
                      job_cost_so_far=_job_cost(db, job), trigger=trigger_, forbidden=forbidden)

    decision = route(trigger)
    while True:
        db.refresh(job)
        job.lease_expires_at = _lease_until()   # renewed before every item; the owner is unchanged
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
        item = _next_item(db, job)
        if item is None:
            break
        if decision.chosen is None:
            job.status, job.stop_reason = "blocked", decision.stop_reason
            # v5 §9/Workflow D: blocked only by a temporary provider limit -> resume by itself at the reset.
            job.resume_after = (_capacity_resume_time(db, policy, forbidden)
                                if decision.stop_reason == "PROVIDER_UNAVAILABLE" else None)
            _checkpoint(db, job, last=last, reason=decision.stop_reason, excluded=excluded, handoff=True)
            return {"status": "blocked", "stop_reason": decision.stop_reason,
                    "resume_after": job.resume_after.isoformat() if job.resume_after else None, **_counts(db, job)}
        c = decision.chosen
        # Prompt-injection defence (ADR-126): trusted rules travel in the SYSTEM channel with a per-call canary;
        # the item prompt may carry fenced untrusted data and is never trusted as instructions. The system text is
        # real input the provider bills, so the cost gate below counts it.
        canary = prompt_safety.new_canary()
        system = prompt_safety.system_policy(canary=canary) if settings.AI_SYSTEM_POLICY_ENABLED else None
        # Cost gate BEFORE spending (REQ-AIC-012): worst-case estimate for this
        # item must fit the job budget; an unknown price under a budget stops.
        caps = [Decimal(str(policy.max_cost_per_job))] if policy.max_cost_per_job is not None else []
        if bg_cost_cap is not None:
            caps.append(bg_cost_cap)          # background policy's max cost per run (ADR-095)
        if caps:
            limit = min(caps)
            price = (pricing or ConfiguredPricing()).price(c.provider.adapter_key or c.provider.canonical_name, c.step.model)
            bound = reservation_upper_bound(price, prompt=(system or "") + item.prompt,
                                            max_output_tokens=job.max_output_tokens, attempts=1)
            if bound is None or _job_cost(db, job) + bound > limit:
                job.status, job.stop_reason = "blocked", "SPEND_LIMIT"
                _checkpoint(db, job, last=last, reason="SPEND_LIMIT" if bound is not None else "SPEND_LIMIT: price unknown",
                            excluded=excluded, handoff=True)
                return {"status": "blocked", "stop_reason": "SPEND_LIMIT", **_counts(db, job)}
        # ADR-136: an item that cannot fit the routed model's registered limits is failed visibly before any
        # call; it is never truncated to fit. Unknown limits block nothing.
        misfit = request_fit(db, c, input_tokens=estimate_tokens((system or "") + item.prompt),
                             output_tokens=job.max_output_tokens)
        if misfit:
            item.status, item.failure_reason = "failed", misfit[:300]
            db.commit()
            continue
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
                          ModelRequest(prompt=item.prompt, max_output_tokens=job.max_output_tokens, system=system),
                          adapter=adapter, pricing=pricing or ConfiguredPricing(), previous=prev, attempt_reason=reason,
                          provider_account_id=c.account.id)
        ex = out.execution
        last = ex
        item.last_execution_id = ex.id
        c.account.last_used_at = _now()
        check = prompt_safety.check_output(out.result.text if out.succeeded else None, canary=canary,
                                           allowed_urls=set(prompt_safety.urls_in(item.prompt)))
        if out.succeeded and check.rejected:
            # The answer revealed the confidential system marker: the model was steered by injected text.
            # Nothing of it is stored or chained; the item fails visibly and the event is audited.
            item.status = "failed"
            item.failure_reason = "OUTPUT_REJECTED: prompt-safety check failed (system instructions leaked)"
            record_audit_log(db, organization_id=org, user_id=None, action="ai.output_rejected_prompt_safety",
                             resource_type="ai_job", resource_id=job.id,
                             new_value={"item": item.item_key, "execution_id": str(ex.id), **check.as_dict()})
            db.commit()
            continue
        if out.succeeded and check.needs_review:
            record_audit_log(db, organization_id=org, user_id=None, action="ai.prompt_safety_finding",
                             resource_type="ai_job", resource_id=job.id,
                             new_value={"item": item.item_key, "execution_id": str(ex.id), **check.as_dict()})
        if out.succeeded:
            item.status, item.completed_by_account_id, item.failure_reason = "completed", c.account.id, None
            if c.account.health_status != "healthy":
                ai_center_service.record_health(db, c.account, health="healthy", source="execution", execution_id=ex.id)
            finding = memory.write(db, organization_id=org, job_key=job.job_key, kind="intermediate_finding",
                         created_by=f"execution:{ex.id}", stage=job.stage, item_key=item.item_key,
                         source_id=item.source_id, document_id=item.document_id, commit=False,
                         # v4 §13: the whole answer is kept. This used to be `[:4000]`, which silently
                         # discarded the tail of every long result.
                         content={"item": item.item_key, "result": check.text,
                                  "result_chars": len(check.text),
                                  **({"safety": check.as_dict()} if check.needs_review else {})},
                         provenance={"execution_id": str(ex.id), "provider": ex.provider, "model": ex.model,
                                     "account_id": str(c.account.id)})
            db.commit()
            if job.output_contract == "ktp_v1":
                # ADR-134: structured output goes through the validator and reconciler, never straight into
                # knowledge. An unreadable or truncated package fails the item visibly (its raw text stays in
                # memory above) so it can be retried; per-claim rejections are recorded on the package.
                from app.services import knowledge_reconciliation_service as reconciler
                rec = reconciler.ingest(db, organization_id=org, knowledge_object_id=job.knowledge_object_id,
                                        raw=check.text, submitted_by=f"execution:{ex.id}", execution_id=ex.id,
                                        job_key=job.job_key, item_key=item.item_key,
                                        truncated=ex.stop_reason == "TOKEN_LIMIT")
                if rec.status == "invalid":
                    item.status, item.failure_reason = "failed", f"OUTPUT_INVALID: {rec.invalid_reason}"[:300]
                elif rec.status in ("reconciled", "partially_reconciled") and finding.status == "created":
                    memory.transition(db, finding, "validated", actor="system:validator", commit=False,
                                      reason=f"knowledge transfer package {rec.id}: {rec.status}")
                db.commit()
            continue
        stop = ex.stop_reason or "UNKNOWN"
        if stop in SWITCH_STOPS:
            health, avoid = ai_center_service.HEALTH_FOR_STOP.get(stop, ("degraded", 60))
            # The provider's Retry-After, when it sent one, outranks the fixed avoid window (ADR-132).
            ai_center_service.record_health(db, c.account, health=health, source="execution", code=ex.error_code,
                                            message=ex.error_message, execution_id=ex.id, avoid_seconds=avoid,
                                            retry_after=out.error.retry_after_seconds if out.error else None)
            excluded.add(c.account.id)
            # Persist everything BEFORE switching (REQ-AIC-005).
            _checkpoint(db, job, last=ex, reason=stop, excluded=excluded, handoff=True)
            decision = route(f"switch:{stop}")
            continue
        item.status, item.failure_reason = "failed", f"{stop}: {ex.error_message or ''}"[:300]
        db.commit()

    # v4 §66: a job whose items failed is not "completed". It used to end completed/COMPLETED regardless.
    counts = _counts(db, job)
    if counts["failed"]:
        job.status, job.stop_reason = "completed_with_failures", "ITEMS_FAILED"
    else:
        job.status, job.stop_reason = "completed", "COMPLETED"
    findings, n = memory.list_items(db, organization_id=org, job_key=job.job_key, kind="intermediate_finding", limit=10000)
    memory.write(db, organization_id=org, job_key=job.job_key, kind="current_synthesis", created_by="system", commit=False,
                 content={"method": "mechanical merge of per-item findings (not an AI synthesis)",
                          "items_with_findings": sorted({f.item_key for f in findings}), "finding_count": n,
                          "failed_items": counts["failed"]})
    _checkpoint(db, job, last=last, reason=None, excluded=excluded, handoff=False)
    return {"status": job.status, "stop_reason": job.stop_reason, **_counts(db, job)}


def recover_jobs(db: Session) -> dict:
    """ADR-131 recovery sweep (run by Celery beat). Returns the ids of jobs that should be run again.

    * running + expired lease  -> the worker died: re-queued; finished items stay finished.
    * blocked + resume_after passed -> the provider limit has reset: re-queued, at most
      AI_JOB_MAX_AUTO_RESUMES times; after that it stays blocked (AUTO_RESUME_LIMIT) for a person.
    Every transition is written to the job's memory, so the history says why it moved."""
    now = _now()
    requeue: list[UUID] = []
    stale = db.execute(select(AIJob).where(AIJob.status == "running", AIJob.lease_expires_at < now)
                       .with_for_update(skip_locked=True)).scalars().all()
    for job in stale:
        memory.write(db, organization_id=job.organization_id, job_key=job.job_key, kind="job_state",
                     created_by="system:recovery", commit=False,
                     content={"status": "queued", "reason": "worker lease expired", "previous_lease_owner": job.lease_owner,
                              "lease_expired_at": job.lease_expires_at.isoformat(), "at": now.isoformat()})
        job.status, job.lease_owner, job.lease_expires_at = "queued", None, None
        job.retry_count = (job.retry_count or 0) + 1
        requeue.append(job.id)
    due = db.execute(select(AIJob).where(AIJob.status == "blocked", AIJob.resume_after <= now)
                     .with_for_update(skip_locked=True)).scalars().all()
    for job in due:
        if job.auto_resume_count >= settings.AI_JOB_MAX_AUTO_RESUMES:
            job.resume_after, job.stop_reason = None, "AUTO_RESUME_LIMIT"
            memory.write(db, organization_id=job.organization_id, job_key=job.job_key, kind="job_state",
                         created_by="system:recovery", commit=False,
                         content={"status": "blocked", "stop_reason": "AUTO_RESUME_LIMIT",
                                  "auto_resumes": job.auto_resume_count, "at": now.isoformat()})
            continue
        memory.write(db, organization_id=job.organization_id, job_key=job.job_key, kind="job_state",
                     created_by="system:recovery", commit=False,
                     content={"status": "queued", "reason": f"provider limit reset ({job.stop_reason})",
                              "auto_resume": job.auto_resume_count + 1, "at": now.isoformat()})
        job.status, job.resume_after = "queued", None
        job.auto_resume_count += 1
        requeue.append(job.id)
    db.commit()
    return {"requeued": requeue, "stale_leases": len(stale), "resumed_after_limit": len(requeue) - len(stale)}
