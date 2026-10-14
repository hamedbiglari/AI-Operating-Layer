"""
Agent Network API (ADR-096). Tenant-scoped, admin writes, authenticated reads.
No agent can escalate its own permissions. All messages are durable.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.security.dependencies import get_current_user, require_roles
from app.models.agent_network import (AgentDefinition, AgentHandoff, AgentMemoryBinding,
                                       AgentMessage, AgentSession, AgentTask)
from app.models.background_policy import BackgroundTaskPolicy, MemoryProfile
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams

router = APIRouter(prefix="/agent-network", tags=["agent-network"])

ADMIN_ROLES = (UserRole.OWNER, UserRole.ADMIN)
Editor = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))
Reader = Depends(get_current_user)

def _org(user: User): return user.organization_id
def _404(db: Session, model, obj_id, org_id):
    row = db.execute(select(model).where(model.id == obj_id, model.organization_id == org_id)).scalar_one_or_none()
    if not row: raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return row

# ─── Agents ────────────────────────────────────────────────────────────────

class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    agent_type: str = Field(min_length=1, max_length=50)
    protocol: str = Field(default="internal", pattern="^(internal|rest|mcp|webhook|a2a|local)$")
    endpoint_url: str | None = Field(default=None, max_length=2048)
    auth_method: str | None = Field(default=None, max_length=30)
    trust_level: str = "tenant"
    capabilities: list[str] | None = None
    allowed_tools: list[str] | None = None
    allowed_ai_accounts: list[UUID] | None = None
    notes: str | None = None


class AgentPatch(BaseModel):
    name: str | None = None; description: str | None = None
    status: str | None = Field(default=None, pattern="^(draft|active|disabled)$")
    endpoint_url: str | None = None; capabilities: list[str] | None = None
    allowed_tools: list[str] | None = None; allowed_ai_accounts: list[UUID] | None = None; notes: str | None = None


def _safe_endpoint(url: str | None) -> None:
    """Remote agent endpoints pass the same SSRF guard as URL ingestion:
    credentials in URLs, odd ports, private/loopback/metadata targets refused."""
    if not url:
        return
    from app.ingestion.url_source import UrlRejected, resolve_and_validate, validate_url
    try:
        host, port, _ = validate_url(url)
        resolve_and_validate(host, port)
    except UrlRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Agent endpoint rejected: {exc}") from None


def _own_accounts(db: Session, org, ids) -> list[str] | None:
    if ids is None:
        return None
    from app.models.ai_center import AIProviderAccount
    found = set(db.execute(select(AIProviderAccount.id).where(AIProviderAccount.organization_id == org,
                AIProviderAccount.id.in_(list(ids)))).scalars())
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown AI accounts: {', '.join(missing)}")
    return [str(i) for i in ids]


def _agent_out(r: AgentDefinition) -> dict:
    return {k: getattr(r, k) for k in ("id", "name", "description", "agent_type", "status", "protocol", "endpoint_url",
                                       "auth_method", "trust_level", "capabilities", "allowed_tools",
                                       "allowed_ai_accounts", "notes", "created_at", "updated_at")}


@router.get("/agents", response_model=Page[dict])
def list_agents(p: PaginationParams = Depends(), sort: SortParams = Depends(), user: User = Reader,
                db: Session = Depends(get_db)):
    from app.schemas.common import SortDirection, apply_sort
    q = select(AgentDefinition).where(AgentDefinition.organization_id == _org(user))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    q = apply_sort(q, AgentDefinition, sort, default_field="name", default_dir=SortDirection.ASC)
    rows = db.execute(q.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[_agent_out(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/agents", status_code=201)
def create_agent(body: AgentIn, user: User = Editor, db: Session = Depends(get_db)):
    if db.execute(select(AgentDefinition).where(AgentDefinition.organization_id == _org(user),
                  AgentDefinition.name == body.name)).scalar_one_or_none():
        raise HTTPException(409, "An agent with that name already exists.")
    _safe_endpoint(body.endpoint_url)
    data = body.model_dump()
    data["allowed_ai_accounts"] = _own_accounts(db, _org(user), body.allowed_ai_accounts)
    row = AgentDefinition(organization_id=_org(user), **data)
    db.add(row); db.commit(); db.refresh(row)
    return _agent_out(row)


@router.get("/agents/{agent_id}")
def get_agent(agent_id: UUID, user: User = Reader, db: Session = Depends(get_db)):
    r = _404(db, AgentDefinition, agent_id, _org(user))
    out = _agent_out(r)
    out["memory_bindings"] = [{"memory_profile_id": b.memory_profile_id, "access_level": b.access_level}
                              for b in db.execute(select(AgentMemoryBinding).where(
                                  AgentMemoryBinding.organization_id == _org(user),
                                  AgentMemoryBinding.agent_definition_id == r.id)).scalars()]
    return out


@router.patch("/agents/{agent_id}")
def patch_agent(agent_id: UUID, body: AgentPatch, user: User = Editor, db: Session = Depends(get_db)):
    r = _404(db, AgentDefinition, agent_id, _org(user))
    data = body.model_dump(exclude_none=True)
    if "endpoint_url" in data:
        _safe_endpoint(data["endpoint_url"])
    if "allowed_ai_accounts" in data:
        data["allowed_ai_accounts"] = _own_accounts(db, _org(user), body.allowed_ai_accounts)
    for k, v in data.items():
        setattr(r, k, v)
    db.commit(); db.refresh(r)
    return _agent_out(r)


class BindingIn(BaseModel):
    memory_profile_id: UUID
    access_level: str = Field(default="read", pattern="^(read|write|admin)$")


@router.put("/agents/{agent_id}/memory-bindings")
def bind_memory(agent_id: UUID, body: BindingIn, user: User = Editor, db: Session = Depends(get_db)):
    """Only a tenant admin (a human, via user auth) grants memory access; an agent
    has no credential that could call this, so it cannot raise its own permissions."""
    _404(db, AgentDefinition, agent_id, _org(user))
    _404(db, MemoryProfile, body.memory_profile_id, _org(user))
    b = db.execute(select(AgentMemoryBinding).where(AgentMemoryBinding.organization_id == _org(user),
                   AgentMemoryBinding.agent_definition_id == agent_id,
                   AgentMemoryBinding.memory_profile_id == body.memory_profile_id)).scalar_one_or_none()
    if b is None:
        b = AgentMemoryBinding(organization_id=_org(user), agent_definition_id=agent_id,
                               memory_profile_id=body.memory_profile_id)
        db.add(b)
    b.access_level = body.access_level
    db.commit()
    return {"agent_id": str(agent_id), "memory_profile_id": str(body.memory_profile_id), "access_level": b.access_level}


# ─── Sessions / tasks / handoffs ───────────────────────────────────────────

class SessionIn(BaseModel):
    session_key: str = Field(min_length=1, max_length=200)
    goal: str | None = None
    memory_profile_id: UUID | None = None


@router.post("/sessions", status_code=201)
def create_session(body: SessionIn, user: User = Editor, db: Session = Depends(get_db)):
    if db.execute(select(AgentSession).where(AgentSession.organization_id == _org(user),
                  AgentSession.session_key == body.session_key)).scalar_one_or_none():
        raise HTTPException(409, "Session key already exists.")
    ctx = None
    if body.memory_profile_id:
        _404(db, MemoryProfile, body.memory_profile_id, _org(user))
        ctx = {"memory_profile_id": str(body.memory_profile_id)}
    row = AgentSession(organization_id=_org(user), session_key=body.session_key, goal=body.goal, context=ctx)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "session_key": row.session_key, "status": row.status}


@router.get("/sessions/{session_id}")
def get_session(session_id: UUID, user: User = Reader, db: Session = Depends(get_db)):
    r = _404(db, AgentSession, session_id, _org(user))
    return {"id": r.id, "session_key": r.session_key, "goal": r.goal, "status": r.status, "context": r.context,
            "created_at": r.created_at}


class TaskIn(BaseModel):
    task_type: str = Field(min_length=1, max_length=50)
    task_key: str = Field(min_length=1, max_length=200)
    input_ref: dict | None = None
    depends_on: list[UUID] | None = None


@router.post("/sessions/{session_id}/tasks", status_code=201)
def create_task(session_id: UUID, body: TaskIn, user: User = Editor, db: Session = Depends(get_db)):
    _404(db, AgentSession, session_id, _org(user))
    for dep in body.depends_on or []:
        _404(db, AgentTask, dep, _org(user))
    row = AgentTask(organization_id=_org(user), session_id=session_id, task_type=body.task_type, task_key=body.task_key,
                    input_ref=body.input_ref, depends_on=[str(d) for d in body.depends_on or []], status="created")
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "task_key": row.task_key, "status": row.status}


@router.get("/sessions/{session_id}/tasks")
def list_tasks(session_id: UUID, user: User = Reader, db: Session = Depends(get_db)):
    _404(db, AgentSession, session_id, _org(user))
    rows = db.execute(select(AgentTask).where(AgentTask.organization_id == _org(user), AgentTask.session_id == session_id)
                      .order_by(AgentTask.created_at)).scalars().all()
    return [{"id": r.id, "task_type": r.task_type, "task_key": r.task_key, "status": r.status,
             "assigned_agent_id": r.assigned_agent_id, "ai_execution_ids": r.ai_execution_ids or [],
             "output_ref": r.output_ref} for r in rows]


class RunIn(BaseModel):
    agent_id: UUID
    routing_policy_id: UUID
    prompt: str = Field(min_length=1, max_length=50_000)
    handoff_id: UUID | None = None


@router.post("/sessions/{session_id}/tasks/{task_id}/run")
def run_task(session_id: UUID, task_id: UUID, body: RunIn, user: User = Editor, db: Session = Depends(get_db)):
    from app.models.ai_center import AIRoutingPolicy
    from app.services.agent_execution_service import AgentExecutionService, IllegalTransition, MemoryAccessDenied
    s = _404(db, AgentSession, session_id, _org(user)); t = _404(db, AgentTask, task_id, _org(user))
    _404(db, AIRoutingPolicy, body.routing_policy_id, _org(user))
    h = _404(db, AgentHandoff, body.handoff_id, _org(user)) if body.handoff_id else None
    svc = AgentExecutionService(db, _org(user))
    try:
        r = svc.run_task(s, t, body.agent_id, routing_policy_id=body.routing_policy_id, prompt=body.prompt, handoff=h)
    except MemoryAccessDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from None
    except (PermissionError, IllegalTransition) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.") from None
    return {"task_id": str(r.task_id), "status": r.status, "stop_reason": r.stop_reason,
            "ai_execution_ids": r.ai_execution_ids, "findings": r.findings}


class HandoffIn(BaseModel):
    from_agent_id: UUID
    to_agent_id: UUID
    reason: str = Field(default="task_complete", max_length=100)


@router.post("/sessions/{session_id}/tasks/{task_id}/handoff", status_code=201)
def handoff_task(session_id: UUID, task_id: UUID, body: HandoffIn, user: User = Editor, db: Session = Depends(get_db)):
    from app.services.agent_execution_service import AgentExecutionService, AgentTaskResult, IllegalTransition
    s = _404(db, AgentSession, session_id, _org(user)); t = _404(db, AgentTask, task_id, _org(user))
    if t.session_id != s.id:
        raise HTTPException(404, "Not found.")
    out = t.output_ref or {}
    result = AgentTaskResult(task_id=t.id, agent_id=body.from_agent_id, status=t.status,
                             findings=out.get("findings", {}), ai_execution_ids=t.ai_execution_ids or [])
    try:
        h = AgentExecutionService(db, _org(user)).handoff(s, t, body.from_agent_id, body.to_agent_id, result,
                                                          reason=body.reason)
    except IllegalTransition as exc:
        raise HTTPException(409, str(exc)) from None
    except LookupError:
        raise HTTPException(404, "Not found.") from None
    return {"id": h.id, "status": h.status, "working_memory_id": h.working_memory_id}


@router.post("/handoffs/{handoff_id}/accept")
def accept_handoff(handoff_id: UUID, body: dict, user: User = Editor, db: Session = Depends(get_db)):
    from app.services.agent_execution_service import AgentExecutionService, MemoryAccessDenied
    h = _404(db, AgentHandoff, handoff_id, _org(user))
    try:
        AgentExecutionService(db, _org(user)).accept_handoff(h, UUID(str(body.get("agent_id"))))
    except MemoryAccessDenied as exc:
        raise HTTPException(403, str(exc)) from None
    except (PermissionError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from None
    return {"id": h.id, "status": h.status}


@router.get("/sessions/{session_id}/handoffs")
def list_handoffs(session_id: UUID, user: User = Reader, db: Session = Depends(get_db)):
    _404(db, AgentSession, session_id, _org(user))
    rows = db.execute(select(AgentHandoff).where(AgentHandoff.organization_id == _org(user),
                      AgentHandoff.session_id == session_id).order_by(AgentHandoff.created_at)).scalars().all()
    return [{"id": r.id, "from_agent_id": r.from_agent_id, "to_agent_id": r.to_agent_id, "reason": r.reason,
             "status": r.status, "working_memory_id": r.working_memory_id, "created_at": r.created_at} for r in rows]


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: UUID, user: User = Reader, db: Session = Depends(get_db)):
    _404(db, AgentSession, session_id, _org(user))
    rows = db.execute(select(AgentMessage).where(AgentMessage.organization_id == _org(user),
                      AgentMessage.session_id == session_id).order_by(AgentMessage.created_at)).scalars().all()
    return [{"id": r.id, "from_agent_id": r.from_agent_id, "to_agent_id": r.to_agent_id, "type": r.message_type,
             "status": r.status, "payload_reference": r.payload_reference, "memory_references": r.memory_references,
             "delivered_at": r.delivered_at, "acknowledged_at": r.acknowledged_at} for r in rows]


# ─── Memory Profiles ───────────────────────────────────────────────────────

@router.get("/memory-profiles")
def list_memory_profiles(user: User = Reader, db: Session = Depends(get_db)):
    rows = db.execute(select(MemoryProfile).where(MemoryProfile.organization_id == _org(user)).order_by(MemoryProfile.name)).scalars().all()
    return [{"id": r.id, "name": r.name, "namespace": r.namespace, "scope": r.scope,
             "semantic_backend": r.semantic_backend, "is_default": r.is_default, "canonical_store": "postgresql"} for r in rows]

@router.post("/memory-profiles", status_code=201)
def create_memory_profile(body: dict, user: User = Editor, db: Session = Depends(get_db)):
    row = MemoryProfile(organization_id=_org(user), name=body["name"],
                        namespace=body.get("namespace", body["name"].lower().replace(" ","-")),
                        scope=body.get("scope","project"), semantic_backend=body.get("semantic_backend","native"),
                        description=body.get("description"), retention_days=body.get("retention_days"))
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name, "namespace": row.namespace, "canonical_store": "postgresql"}

# ─── Background Processing Policies ────────────────────────────────────────

@router.get("/background-policies")
def list_background_policies(user: User = Reader, db: Session = Depends(get_db)):
    rows = db.execute(select(BackgroundTaskPolicy).where(BackgroundTaskPolicy.organization_id == _org(user)).order_by(BackgroundTaskPolicy.task_type)).scalars().all()
    return [{"id": r.id, "task_type": r.task_type, "enabled": r.enabled,
             "allowed_account_ids": r.allowed_account_ids or [],
             "routing_mode": r.routing_mode, "max_cost_per_run": r.max_cost_per_run,
             "auto_switch_on_failure": r.auto_switch_on_failure} for r in rows]

@router.put("/background-policies/{task_type}")
def upsert_background_policy(task_type: str, body: dict, user: User = Editor, db: Session = Depends(get_db)):
    row = db.execute(select(BackgroundTaskPolicy).where(BackgroundTaskPolicy.organization_id == _org(user),
                     BackgroundTaskPolicy.task_type == task_type)).scalar_one_or_none()
    if row is None:
        row = BackgroundTaskPolicy(organization_id=_org(user), task_type=task_type)
        db.add(row)
    if "allowed_account_ids" in body and body["allowed_account_ids"] is not None:
        body["allowed_account_ids"] = _own_accounts(db, _org(user), [UUID(str(a)) for a in body["allowed_account_ids"]])
    if body.get("routing_policy_id"):
        from app.models.ai_center import AIRoutingPolicy
        _404(db, AIRoutingPolicy, UUID(str(body["routing_policy_id"])), _org(user))
    for k in ("enabled","allowed_account_ids","routing_policy_id","routing_mode","max_cost_per_run",
              "max_cost_currency","required_capabilities","auto_switch_on_failure","pause_on_cost_limit","notes"):
        if k in body: setattr(row, k, body[k])
    db.commit(); db.refresh(row)
    return {"task_type": row.task_type, "enabled": row.enabled, "allowed_account_ids": row.allowed_account_ids}
