"""
AI Center API (REQ-AIC-*, REQ-KW-*). Tenant-scoped everywhere. Reads: any
member. Writes to the resource registry / routing / credentials: OWNER/ADMIN.
Credentials are write-only: no response model contains the secret or its
ciphertext — only `credential_set`, `credential_last4` and timestamps.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.memory import walrus
from app.models.ai_center import (
    CAPABILITY_SOURCES, DISCOVERY_STATUSES, ROUTING_MODES, AIDiscoveryEntry, AIHealthEvent, AIJob, AIJobItem, AIModel, AIProvider,
    AIProviderAccount, AIRoutingDecision, AIRoutingPolicy, AIRoutingStep, AIWorkingMemory, KnowledgeKeyword,
)
from app.models.enums import ADMIN_ROLES, KNOWLEDGE_EDITOR_ROLES
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import ai_center_service as svc
from app.services import ai_job_service, ai_memory_service, keyword_service
from app.services.ai_discovery_seed import BASIS, ENTRIES, SOURCE
from app.services.ai_routing_service import decide
from app.services.audit import record_audit_log

router = APIRouter(prefix="/ai-center", tags=["ai-center"])
kw_router = APIRouter(prefix="/knowledge", tags=["knowledge-keywords"])
Admin = Depends(require_roles(*ADMIN_ROLES))


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# ---------------- providers ----------------
class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    official_url: str | None = Field(default=None, max_length=500)
    api_base_url: str | None = Field(default=None, max_length=500)
    documentation_url: str | None = Field(default=None, max_length=500)
    adapter_key: str | None = Field(default=None, max_length=60)
    credential_method: str | None = Field(default=None, max_length=60)
    notes: str | None = None


class ProviderOut(_Out):
    id: UUID; name: str; canonical_name: str; official_url: str | None; api_base_url: str | None
    documentation_url: str | None; adapter_key: str | None; adapter_implemented: bool = False
    credential_method: str | None; verification_status: str; notes: str | None; created_at: datetime


def _provider_out(p: AIProvider) -> ProviderOut:
    o = ProviderOut.model_validate(p)
    o.adapter_implemented = svc.adapter_class(p.adapter_key) is not None
    return o


def _url_ok(u: str | None) -> None:
    if u and not u.lower().startswith("https://"):
        raise HTTPException(status_code=422, detail="Provider URLs must be https:// (they are stored, never fetched by this call)")


@router.get("/providers", response_model=Page[ProviderOut])
def list_providers(p: PaginationParams = Depends(), sort: SortParams = Depends(), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(AIProvider).where(AIProvider.organization_id == user.organization_id)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(apply_sort(q, AIProvider, sort, default_field="name", default_dir=SortDirection.ASC).limit(p.limit).offset(p.offset)).scalars().all()
    return Page[ProviderOut](items=[_provider_out(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/providers", response_model=ProviderOut, status_code=201)
def create_provider(body: ProviderIn, user: User = Admin, db: Session = Depends(get_db)):
    for u in (body.official_url, body.api_base_url, body.documentation_url):
        _url_ok(u)
    row = AIProvider(organization_id=user.organization_id, canonical_name=svc.canonical(body.name),
                     verification_status="identified" if body.official_url else "discovered", **body.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A provider with this name already exists") from None
    return _provider_out(row)


@router.get("/providers/{provider_id}", response_model=ProviderOut)
def get_provider(provider_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _provider_out(svc.get_or_404(db, AIProvider, provider_id, user.organization_id))


# ---------------- accounts & credentials ----------------
class AccountIn(BaseModel):
    provider_id: UUID
    label: str = Field(min_length=1, max_length=120)
    plan_name: str | None = Field(default=None, max_length=120)
    spend_limit: float | None = Field(default=None, ge=0)
    spend_limit_currency: str | None = Field(default=None, min_length=3, max_length=3)


class AccountPatch(BaseModel):
    enabled: bool | None = None
    plan_name: str | None = None
    spend_limit: float | None = Field(default=None, ge=0)


class AccountOut(_Out):
    id: UUID; provider_id: UUID; label: str; plan_name: str | None; enabled: bool
    credential_set: bool = False; credential_last4: str | None; credential_set_at: datetime | None
    credential_last_tested_at: datetime | None; health_status: str; health_checked_at: datetime | None
    unavailable_until: datetime | None; failure_count: int; last_used_at: datetime | None
    remaining_requests: int | None; remaining_tokens: int | None; quota_reset_at: datetime | None
    spend_limit: float | None; spend_limit_currency: str | None; created_at: datetime


def _account_out(a: AIProviderAccount) -> AccountOut:
    o = AccountOut.model_validate(a)
    o.credential_set = bool(a.credential_ciphertext)
    return o


@router.get("/accounts", response_model=Page[AccountOut])
def list_accounts(p: PaginationParams = Depends(), sort: SortParams = Depends(), provider_id: UUID | None = None, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    q = select(AIProviderAccount).where(AIProviderAccount.organization_id == user.organization_id)
    if provider_id:
        q = q.where(AIProviderAccount.provider_id == provider_id)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(apply_sort(q, AIProviderAccount, sort, default_field="label", default_dir=SortDirection.ASC).limit(p.limit).offset(p.offset)).scalars().all()
    return Page[AccountOut](items=[_account_out(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(body: AccountIn, user: User = Admin, db: Session = Depends(get_db)):
    svc.get_or_404(db, AIProvider, body.provider_id, user.organization_id)
    row = AIProviderAccount(organization_id=user.organization_id, health_status="unknown", **body.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This provider already has an account with that label") from None
    return _account_out(row)


@router.get("/accounts/{account_id}", response_model=AccountOut)
def get_account(account_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _account_out(svc.get_or_404(db, AIProviderAccount, account_id, user.organization_id))


@router.patch("/accounts/{account_id}", response_model=AccountOut)
def patch_account(account_id: UUID, body: AccountPatch, user: User = Admin, db: Session = Depends(get_db)):
    a = svc.get_or_404(db, AIProviderAccount, account_id, user.organization_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.commit()
    return _account_out(a)


class CredentialIn(BaseModel):
    secret: str = Field(min_length=8, max_length=4096)


@router.put("/accounts/{account_id}/credential", response_model=AccountOut)
def set_credential(account_id: UUID, body: CredentialIn, user: User = Admin, db: Session = Depends(get_db)):
    """Add or rotate. The secret is encrypted at rest and never returned."""
    a = svc.get_or_404(db, AIProviderAccount, account_id, user.organization_id)
    return _account_out(svc.set_credential(db, a, body.secret))


@router.delete("/accounts/{account_id}/credential", response_model=AccountOut)
def delete_credential(account_id: UUID, user: User = Admin, db: Session = Depends(get_db)):
    a = svc.get_or_404(db, AIProviderAccount, account_id, user.organization_id)
    a.credential_ciphertext = a.credential_last4 = None
    a.health_status = "disconnected"
    db.commit()
    return _account_out(a)


@router.post("/accounts/{account_id}/test")
def test_account(account_id: UUID, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    return svc.test_connection(db, svc.get_or_404(db, AIProviderAccount, account_id, user.organization_id))


class HealthOut(_Out):
    id: UUID; status: str; source: str; http_status: int | None; provider_code: str | None; message: str | None
    retry_after_seconds: int | None; execution_id: UUID | None; observed_at: datetime


@router.get("/accounts/{account_id}/health-events", response_model=Page[HealthOut])
def health_events(account_id: UUID, p: PaginationParams = Depends(), sort: SortParams = Depends(), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc.get_or_404(db, AIProviderAccount, account_id, user.organization_id)
    q = select(AIHealthEvent).where(AIHealthEvent.organization_id == user.organization_id, AIHealthEvent.account_id == account_id)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(apply_sort(q, AIHealthEvent, sort, default_field="observed_at", default_dir=SortDirection.DESC).limit(p.limit).offset(p.offset)).scalars().all()
    return Page[HealthOut](items=[HealthOut.model_validate(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.get("/accounts/{account_id}/usage")
def account_usage(account_id: UUID, period: Literal["today", "7d", "30d", "all"] = "30d",
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    a = svc.get_or_404(db, AIProviderAccount, account_id, user.organization_id)
    now = datetime.now(timezone.utc)
    since = {"today": now.replace(hour=0, minute=0, second=0, microsecond=0), "7d": now - timedelta(days=7),
             "30d": now - timedelta(days=30), "all": None}[period]
    u = svc.usage(db, a, since=since)
    if user.role not in ADMIN_ROLES:
        u["estimated_cost"] = None
        u["cost_visible"] = False
    return {"period": period, **u}


# ---------------- models ----------------
class ModelIn(BaseModel):
    provider_id: UUID
    name: str = Field(min_length=1, max_length=160)
    version: str | None = None
    capabilities: list[str] = Field(default_factory=list, max_length=20)
    modalities: list[str] = Field(default_factory=list, max_length=10)
    context_window: int | None = Field(default=None, ge=1)
    license: str | None = None
    # ADR-136: NULL = unknown. Enter what the provider documents; say where it came from.
    max_input_tokens: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)
    supports_structured_output: bool | None = None
    supports_tools: bool | None = None
    capability_source: Literal[CAPABILITY_SOURCES] | None = None  # type: ignore[valid-type]


class ModelPatch(BaseModel):
    context_window: int | None = Field(default=None, ge=1)
    max_input_tokens: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    rpm_limit: int | None = Field(default=None, ge=1)
    tpm_limit: int | None = Field(default=None, ge=1)
    supports_structured_output: bool | None = None
    supports_tools: bool | None = None
    capability_source: Literal[CAPABILITY_SOURCES] | None = None  # type: ignore[valid-type]


class ModelOut(_Out):
    id: UUID; provider_id: UUID; name: str; version: str | None; capabilities: list[str]; modalities: list[str]
    context_window: int | None; license: str | None; status: str; last_verified_at: datetime | None
    max_input_tokens: int | None = None; max_output_tokens: int | None = None; rpm_limit: int | None = None
    tpm_limit: int | None = None; supports_structured_output: bool | None = None; supports_tools: bool | None = None
    capability_source: str | None = None


@router.get("/models", response_model=Page[ModelOut])
def list_models(p: PaginationParams = Depends(), sort: SortParams = Depends(), provider_id: UUID | None = None, capability: str | None = None,
                search: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(AIModel).where(AIModel.organization_id == user.organization_id)
    if provider_id:
        q = q.where(AIModel.provider_id == provider_id)
    if capability:
        q = q.where(AIModel.capabilities.any(capability))
    if search:
        q = q.where(AIModel.name.ilike(f"%{search}%"))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(apply_sort(q, AIModel, sort, default_field="name", default_dir=SortDirection.ASC).limit(p.limit).offset(p.offset)).scalars().all()
    return Page[ModelOut](items=[ModelOut.model_validate(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/models", response_model=ModelOut, status_code=201)
def create_model(body: ModelIn, user: User = Admin, db: Session = Depends(get_db)):
    svc.get_or_404(db, AIProvider, body.provider_id, user.organization_id)
    row = AIModel(organization_id=user.organization_id, status="discovered", **body.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Model already registered for this provider") from None
    return ModelOut.model_validate(row)


@router.patch("/models/{model_id}", response_model=ModelOut)
def update_model_limits(model_id: UUID, body: ModelPatch, user: User = Admin, db: Session = Depends(get_db)):
    """ADR-136: limits change; a person corrects them here. Only the fields sent are changed (null clears one
    back to unknown), and the old and new values are audit-logged."""
    row = svc.get_or_404(db, AIModel, model_id, user.organization_id)
    changes = body.model_dump(exclude_unset=True)
    old = {k: getattr(row, k) for k in changes}
    for k, v in changes.items():
        setattr(row, k, v)
    record_audit_log(db, organization_id=user.organization_id, user_id=user.id, action="ai_model.limits_updated",
                     resource_type="ai_model", resource_id=row.id, old_value=old, new_value=changes)
    db.commit()
    return ModelOut.model_validate(row)


# ---------------- routing ----------------
class StepIn(BaseModel):
    account_id: UUID
    model: str = Field(min_length=1, max_length=160)
    stage: str | None = Field(default=None, max_length=60)
    required_capability: str | None = Field(default=None, max_length=40)


class PolicyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    mode: Literal[ROUTING_MODES]  # type: ignore[valid-type]
    steps: list[StepIn] = Field(min_length=1, max_length=50)
    max_cost_per_job: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class StepOut(_Out):
    position: int; stage: str | None; account_id: UUID; model: str; required_capability: str | None


class PolicyOut(_Out):
    id: UUID; name: str; mode: str; max_cost_per_job: float | None; currency: str | None; steps: list[StepOut] = []


def _policy_out(db: Session, pol: AIRoutingPolicy) -> PolicyOut:
    o = PolicyOut.model_validate(pol)
    o.steps = [StepOut.model_validate(s) for s in db.execute(select(AIRoutingStep).where(
        AIRoutingStep.policy_id == pol.id).order_by(AIRoutingStep.position)).scalars()]
    return o


def _validate_policy(mode: str, steps: list) -> None:
    """The mode's own rules. Applied identically on create and on every edit, so a policy can never be
    edited into a shape that could not have been created."""
    if not steps:
        raise HTTPException(status_code=422, detail="a routing policy needs at least one step")
    if len(steps) > 50:
        raise HTTPException(status_code=422, detail="a routing policy takes at most 50 steps")
    if mode == "manual_single" and len(steps) != 1:
        raise HTTPException(status_code=422, detail="manual_single takes exactly one step")
    if mode == "stage_manual" and any(s.stage is None for s in steps):
        raise HTTPException(status_code=422, detail="stage_manual requires a stage on every step")


def _steps_of(db: Session, policy_id: UUID) -> list[AIRoutingStep]:
    return list(db.execute(select(AIRoutingStep).where(AIRoutingStep.policy_id == policy_id)
                           .order_by(AIRoutingStep.position)).scalars())


def _renumber(db: Session, steps: list[AIRoutingStep]) -> None:
    """Positions stay 0..n-1 with no gaps. Two passes with a flush between them, because
    (policy_id, position) is unique: moving straight to the final numbers would collide with a row that has
    not moved yet, and without the flush both passes would be sent as one statement."""
    for i, s in enumerate(steps):
        s.position = -(i + 1)
    db.flush()
    for i, s in enumerate(steps):
        s.position = i
    db.flush()


@router.post("/routing-policies", response_model=PolicyOut, status_code=201)
def create_policy(body: PolicyIn, user: User = Admin, db: Session = Depends(get_db)):
    _validate_policy(body.mode, body.steps)
    for s in body.steps:
        svc.get_or_404(db, AIProviderAccount, s.account_id, user.organization_id)
    pol = AIRoutingPolicy(organization_id=user.organization_id, name=body.name, mode=body.mode,
                          max_cost_per_job=body.max_cost_per_job, currency=body.currency)
    db.add(pol)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A routing policy with this name already exists") from None
    for i, s in enumerate(body.steps):
        db.add(AIRoutingStep(organization_id=user.organization_id, policy_id=pol.id, position=i, **s.model_dump()))
    db.commit()
    return _policy_out(db, pol)


@router.get("/routing-policies", response_model=Page[PolicyOut])
def list_policies(p: PaginationParams = Depends(), sort: SortParams = Depends(), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(AIRoutingPolicy).where(AIRoutingPolicy.organization_id == user.organization_id)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(apply_sort(q, AIRoutingPolicy, sort, default_field="name", default_dir=SortDirection.ASC).limit(p.limit).offset(p.offset)).scalars().all()
    return Page[PolicyOut](items=[_policy_out(db, r) for r in rows], total=total, limit=p.limit, offset=p.offset)


class PolicyPatch(BaseModel):
    """Rename a policy, change its mode, or set its cost ceiling. Steps are managed through their own
    endpoints, so an edit cannot silently discard them."""
    name: str | None = Field(default=None, min_length=1, max_length=120)
    mode: Literal[ROUTING_MODES] | None = None  # type: ignore[valid-type]
    max_cost_per_job: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    clear_max_cost: bool = False


class StepMove(BaseModel):
    position: int = Field(ge=0)


@router.get("/routing-policies/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _policy_out(db, svc.get_or_404(db, AIRoutingPolicy, policy_id, user.organization_id))


@router.patch("/routing-policies/{policy_id}", response_model=PolicyOut)
def update_policy(policy_id: UUID, body: PolicyPatch, user: User = Admin, db: Session = Depends(get_db)):
    pol = svc.get_or_404(db, AIRoutingPolicy, policy_id, user.organization_id)
    data = body.model_dump(exclude_unset=True)
    clear = data.pop("clear_max_cost", False)
    if "mode" in data and data["mode"] is not None:
        _validate_policy(data["mode"], _steps_of(db, pol.id))     # the new mode must fit the steps it already has
        pol.mode = data["mode"]
    for field in ("name", "max_cost_per_job", "currency"):
        if field in data and data[field] is not None:
            setattr(pol, field, data[field])
    if clear:
        pol.max_cost_per_job = None
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A routing policy with this name already exists") from None
    db.commit()
    return _policy_out(db, pol)


@router.delete("/routing-policies/{policy_id}", status_code=204)
def delete_policy(policy_id: UUID, user: User = Admin, db: Session = Depends(get_db)) -> Response:
    pol = svc.get_or_404(db, AIRoutingPolicy, policy_id, user.organization_id)
    used = db.execute(select(func.count()).select_from(AIJob).where(AIJob.policy_id == pol.id)).scalar_one()
    if used:
        raise HTTPException(status_code=409, detail=f"This policy has run {used} job(s); it is kept so their history stays readable")
    for s in _steps_of(db, pol.id):
        db.delete(s)
    db.delete(pol)
    db.commit()
    return Response(status_code=204)


@router.post("/routing-policies/{policy_id}/steps", response_model=PolicyOut, status_code=201)
def add_step(policy_id: UUID, body: StepIn, user: User = Admin, db: Session = Depends(get_db)):
    """Appends a step at the end of the order."""
    pol = svc.get_or_404(db, AIRoutingPolicy, policy_id, user.organization_id)
    svc.get_or_404(db, AIProviderAccount, body.account_id, user.organization_id)
    steps = _steps_of(db, pol.id)
    _validate_policy(pol.mode, steps + [body])
    db.add(AIRoutingStep(organization_id=user.organization_id, policy_id=pol.id, position=len(steps), **body.model_dump()))
    db.commit()
    return _policy_out(db, pol)


@router.patch("/routing-policies/{policy_id}/steps/{position}", response_model=PolicyOut)
def update_step(policy_id: UUID, position: int, body: StepIn, user: User = Admin, db: Session = Depends(get_db)):
    pol = svc.get_or_404(db, AIRoutingPolicy, policy_id, user.organization_id)
    svc.get_or_404(db, AIProviderAccount, body.account_id, user.organization_id)
    steps = _steps_of(db, pol.id)
    step = next((s for s in steps if s.position == position), None)
    if step is None:
        raise HTTPException(status_code=404, detail="No step at that position")
    _validate_policy(pol.mode, [body if s.position == position else s for s in steps])
    for k, v in body.model_dump().items():
        setattr(step, k, v)
    db.commit()
    return _policy_out(db, pol)


@router.post("/routing-policies/{policy_id}/steps/{position}/move", response_model=PolicyOut)
def move_step(policy_id: UUID, position: int, body: StepMove, user: User = Admin, db: Session = Depends(get_db)):
    """Moves one step to another position; everything between it and its destination shifts by one.
    This is how an admin sets which provider is tried first."""
    pol = svc.get_or_404(db, AIRoutingPolicy, policy_id, user.organization_id)
    steps = _steps_of(db, pol.id)
    step = next((s for s in steps if s.position == position), None)
    if step is None:
        raise HTTPException(status_code=404, detail="No step at that position")
    if body.position >= len(steps):
        raise HTTPException(status_code=422, detail=f"position must be between 0 and {len(steps) - 1}")
    steps.remove(step)
    steps.insert(body.position, step)
    _renumber(db, steps)
    db.commit()
    return _policy_out(db, pol)


@router.delete("/routing-policies/{policy_id}/steps/{position}", response_model=PolicyOut)
def delete_step(policy_id: UUID, position: int, user: User = Admin, db: Session = Depends(get_db)):
    pol = svc.get_or_404(db, AIRoutingPolicy, policy_id, user.organization_id)
    steps = _steps_of(db, pol.id)
    step = next((s for s in steps if s.position == position), None)
    if step is None:
        raise HTTPException(status_code=404, detail="No step at that position")
    remaining = [s for s in steps if s is not step]
    _validate_policy(pol.mode, remaining)          # refuses to leave the policy in a shape it could not be created in
    db.delete(step)
    db.flush()
    _renumber(db, remaining)
    db.commit()
    return _policy_out(db, pol)


@router.get("/routing-policies/{policy_id}/preview")
def preview(policy_id: UUID, stage: str | None = None, capability: str | None = None,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Why would this policy pick what it picks right now? (not persisted)"""
    pol = svc.get_or_404(db, AIRoutingPolicy, policy_id, user.organization_id)
    d = decide(db, organization_id=user.organization_id, policy=pol, stage=stage, capability=capability, persist=False)
    return {"mode": pol.mode, "stage": stage, "chosen": next((e for e in d.explanation if e["verdict"] == "chosen"), None),
            "stop_reason": d.stop_reason, "candidates": d.explanation}


@router.get("/routing-decisions")
def routing_decisions(job_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(AIRoutingDecision).where(AIRoutingDecision.organization_id == user.organization_id,
                                                      AIRoutingDecision.job_key == job_key).order_by(AIRoutingDecision.created_at)).scalars()
    return [{"id": str(r.id), "trigger": r.trigger, "mode": r.mode, "stage": r.stage, "chosen_account_id": str(r.chosen_account_id) if r.chosen_account_id else None,
             "chosen_model": r.chosen_model, "explanation": r.explanation, "at": r.created_at.isoformat()} for r in rows]


# ---------------- jobs ----------------
class ItemIn(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=200_000)
    source_id: UUID | None = None
    document_id: UUID | None = None
    # ADR-135: keys of items in this job that must complete first (task DAG; checked acyclic).
    depends_on: list[str] = Field(default_factory=list, max_length=100)


class JobIn(BaseModel):
    job_key: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=1000)
    policy_id: UUID
    stage: str | None = None
    # Set for background work: the tenant's BackgroundTaskPolicy is then enforced (ADR-095).
    task_type: str | None = Field(default=None, max_length=80)
    knowledge_object_id: UUID | None = None
    # ADR-134: 'ktp_v1' = each item returns a Knowledge Transfer Package that is validated and reconciled.
    output_contract: Literal["ktp_v1"] | None = None
    items: list[ItemIn] = Field(min_length=1, max_length=1000)


def _job_view(db: Session, job: AIJob) -> dict:
    counts = ai_job_service._counts(db, job)
    return {"id": str(job.id), "job_key": job.job_key, "goal": job.goal, "stage": job.stage, "status": job.status,
            "stop_reason": job.stop_reason, "retry_count": job.retry_count, "switch_count": job.switch_count, "task_type": job.task_type, "policy_id": str(job.policy_id),
            "resume_after": job.resume_after.isoformat() if job.resume_after and job.status == "blocked" else None,
            "auto_resume_count": job.auto_resume_count, "worker_lease_active": job.lease_owner is not None,
            "output_contract": job.output_contract, **counts}


def _run_in_background(job_id: UUID) -> None:
    from app.workers.tasks import run_ai_job
    run_ai_job.delay(str(job_id))


@router.post("/jobs", status_code=202)
def create_job(body: JobIn, background: BackgroundTasks, user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
               db: Session = Depends(get_db)) -> dict:
    if body.output_contract is not None:
        if body.knowledge_object_id is None:
            raise HTTPException(status_code=422, detail="output_contract needs knowledge_object_id")
        from app.services.knowledge_service import get_knowledge_object_or_404
        get_knowledge_object_or_404(db, object_id=body.knowledge_object_id, organization_id=user.organization_id)
    try:
        job, created = ai_job_service.create_job(db, organization_id=user.organization_id, job_key=body.job_key,
                                                 goal=body.goal, policy_id=body.policy_id, stage=body.stage,
                                                 user_id=user.id, knowledge_object_id=body.knowledge_object_id,
                                                 task_type=body.task_type, output_contract=body.output_contract,
                                                 items=[i.model_dump() for i in body.items])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if created:
        background.add_task(_run_in_background, job.id)
    return {"created": created, **_job_view(db, job)}


def _job(db: Session, user: User, job_key: str) -> AIJob:
    job = db.execute(select(AIJob).where(AIJob.organization_id == user.organization_id, AIJob.job_key == job_key)).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="AI job not found")
    return job


@router.get("/jobs/{job_key}")
def get_job(job_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _job_view(db, _job(db, user, job_key))


class ControlIn(BaseModel):
    action: Literal["pause", "resume", "cancel", "switch"]
    account_id: UUID | None = None


@router.post("/jobs/{job_key}/control", status_code=202)
def control_job(job_key: str, body: ControlIn, background: BackgroundTasks,
                user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)), db: Session = Depends(get_db)) -> dict:
    job = _job(db, user, job_key)
    if body.action == "resume":
        if job.status not in ("paused", "blocked"):
            raise HTTPException(status_code=409, detail=f"Job is {job.status}; only a paused or blocked job can be resumed")
        # A person resuming starts a fresh allowance of automatic resumes (ADR-131).
        job.status, job.resume_after, job.auto_resume_count = "queued", None, 0
        db.commit()
        background.add_task(_run_in_background, job.id)
    else:
        if body.action == "switch" and body.account_id is None:
            raise HTTPException(status_code=422, detail="switch needs account_id")
        try:
            ai_job_service.request_control(db, job, body.action, account_id=body.account_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    return _job_view(db, job)


@router.get("/jobs/{job_key}/handoff")
def job_handoff(job_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _job(db, user, job_key)
    m = ai_memory_service.latest(db, organization_id=user.organization_id, job_key=job_key, kind="ai_handoff") \
        or ai_memory_service.latest(db, organization_id=user.organization_id, job_key=job_key, kind="processing_checkpoint")
    if m is None:
        raise HTTPException(status_code=404, detail="No checkpoint yet")
    return {"kind": m.kind, "version": m.version, "package": m.content}


class MemoryOut(_Out):
    id: UUID; kind: str; version: int; status: str; stage: str | None; item_key: str | None; content: dict
    created_by: str; provenance: dict; created_at: datetime; superseded_by_id: UUID | None = None


class MemoryTransitionIn(BaseModel):
    status: Literal["validated", "active", "archived"]
    reason: str | None = Field(default=None, max_length=500)


@router.post("/memory/{memory_id}/status", response_model=MemoryOut)
def memory_transition(memory_id: UUID, body: MemoryTransitionIn, user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
                      db: Session = Depends(get_db)):
    """ADR-133: a person validates, activates or archives a memory record. It never becomes a claim."""
    row = svc.get_or_404(db, AIWorkingMemory, memory_id, user.organization_id)
    try:
        ai_memory_service.transition(db, row, body.status, actor=f"user:{user.id}", reason=body.reason)
    except ai_memory_service.InvalidMemoryTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return MemoryOut.model_validate(row)


@router.get("/memory", response_model=Page[MemoryOut])
def memory_items(job_key: str, kind: str | None = None, p: PaginationParams = Depends(), sort: SortParams = Depends(),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows, total = ai_memory_service.list_items(db, organization_id=user.organization_id, job_key=job_key, kind=kind,
                                               limit=p.limit, offset=p.offset, sort=sort)
    return Page[MemoryOut](items=[MemoryOut.model_validate(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.get("/memory/semantic-backend")
def semantic_backend(user: User = Depends(get_current_user)) -> dict:
    h = walrus.health()
    return {"backend": "walrus", "status": h.status, "detail": h.detail, "canonical_store": "postgresql"}


# ---------------- discovery ----------------
class DiscoveryOut(_Out):
    id: UUID; name: str; canonical_name: str; proposed_types: list[str]; classification_basis: str; status: str
    official_url: str | None; api_url: str | None; documentation_url: str | None; discovery_source: str
    last_verified_at: datetime | None; verification_notes: str | None


@router.post("/discovery/import-seed")
def import_seed(user: User = Admin, db: Session = Depends(get_db)) -> dict:
    """Idempotent: imports the owner-supplied discovery list as DISCOVERED."""
    from sqlalchemy.dialects.postgresql import insert
    import uuid as _uuid
    n = 0
    for name, types in ENTRIES:
        n += db.execute(insert(AIDiscoveryEntry).values(
            id=_uuid.uuid4(), organization_id=user.organization_id, name=name, canonical_name=svc.canonical(name),
            proposed_types=types, classification_basis=BASIS, status="discovered", discovery_source=SOURCE,
        ).on_conflict_do_nothing(constraint="uq_ai_discovery_org_canonical").returning(AIDiscoveryEntry.id)).scalar_one_or_none() is not None
    db.commit()
    return {"received": len(ENTRIES), "inserted": n, "already_present": len(ENTRIES) - n}


@router.get("/discovery", response_model=Page[DiscoveryOut])
def list_discovery(p: PaginationParams = Depends(), sort: SortParams = Depends(), type: str | None = None, status_: str | None = Query(default=None, alias="status"),
                   search: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(AIDiscoveryEntry).where(AIDiscoveryEntry.organization_id == user.organization_id)
    if type:
        q = q.where(AIDiscoveryEntry.proposed_types.any(type))
    if status_:
        q = q.where(AIDiscoveryEntry.status == status_)
    if search:
        q = q.where(AIDiscoveryEntry.name.ilike(f"%{search}%"))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(apply_sort(q, AIDiscoveryEntry, sort, default_field="name", default_dir=SortDirection.ASC).limit(p.limit).offset(p.offset)).scalars().all()
    return Page[DiscoveryOut](items=[DiscoveryOut.model_validate(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


class DiscoveryPatch(BaseModel):
    status: str
    official_url: str | None = None
    api_url: str | None = None
    documentation_url: str | None = None
    verification_notes: str = Field(min_length=3)


@router.patch("/discovery/{entry_id}", response_model=DiscoveryOut)
def verify_discovery(entry_id: UUID, body: DiscoveryPatch, user: User = Admin, db: Session = Depends(get_db)):
    """A human records verification evidence; nothing becomes ACTIVE automatically."""
    if body.status not in DISCOVERY_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown discovery status")
    for u in (body.official_url, body.api_url, body.documentation_url):
        _url_ok(u)
    e = svc.get_or_404(db, AIDiscoveryEntry, entry_id, user.organization_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    e.last_verified_at = datetime.now(timezone.utc)
    db.commit()
    return DiscoveryOut.model_validate(e)


# ---------------- knowledge keyword workspace ----------------
class KeywordIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=500)
    type: str = "primary"
    intent: str | None = None
    source: str | None = None
    volume: int | None = Field(default=None, ge=0)
    country: str | None = None
    language: str | None = None
    notes: str | None = None
    priority: str | None = None


class KeywordOut(_Out):
    id: UUID; keyword: str; kind: str; intent: str | None; source: str | None; volume: int | None; country: str | None
    language: str | None; notes: str | None; priority: str | None; import_batch: str | None; raw: dict
    research_task_ids: list[str]; created_at: datetime


@kw_router.get("/{knowledge_object_id}/keywords", response_model=Page[KeywordOut])
def list_keywords(knowledge_object_id: UUID, p: PaginationParams = Depends(), sort: SortParams = Depends(), kind: str | None = None,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    keyword_service._ko(db, user.organization_id, knowledge_object_id)
    q = select(KnowledgeKeyword).where(KnowledgeKeyword.organization_id == user.organization_id,
                                       KnowledgeKeyword.knowledge_object_id == knowledge_object_id)
    if kind:
        q = q.where(KnowledgeKeyword.kind == kind)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = db.execute(apply_sort(q, KnowledgeKeyword, sort, default_field="created_at", default_dir=SortDirection.ASC).limit(p.limit).offset(p.offset)).scalars().all()
    return Page[KeywordOut](items=[KeywordOut.model_validate(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@kw_router.post("/{knowledge_object_id}/keywords", status_code=201)
def add_keywords(knowledge_object_id: UUID, body: list[KeywordIn], user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
                 db: Session = Depends(get_db)) -> dict:
    rows = [r.model_dump() for r in body]
    return keyword_service.import_rows(db, organization_id=user.organization_id, ko_id=knowledge_object_id, rows=rows, source="manual")


@kw_router.post("/{knowledge_object_id}/keywords/import", status_code=201)
async def import_keywords(knowledge_object_id: UUID, file: UploadFile = File(...), source: str = Form("upload"),
                          user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)), db: Session = Depends(get_db)) -> dict:
    data = await file.read(keyword_service.MAX_IMPORT_BYTES + 1)
    rows = keyword_service.rows_from_upload(file.filename or "", data)
    return keyword_service.import_rows(db, organization_id=user.organization_id, ko_id=knowledge_object_id, rows=rows, source=source[:120])


class SearchSourcesIn(BaseModel):
    keyword_ids: list[UUID] = Field(min_length=1, max_length=50)
    research_project_id: UUID | None = None


@kw_router.post("/{knowledge_object_id}/keywords/search-sources", status_code=201)
def search_sources(knowledge_object_id: UUID, body: SearchSourcesIn, user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
                   db: Session = Depends(get_db)) -> dict:
    return keyword_service.search_new_sources(db, organization_id=user.organization_id, ko_id=knowledge_object_id,
                                              keyword_ids=body.keyword_ids, actor_user_id=user.id,
                                              research_project_id=body.research_project_id)



# ---------------------------------------------------------------- live job progress (Server-Sent Events)
def stream_session_factory():
    """One short-lived session per poll (overridable in tests, which run inside one transaction)."""
    from app.db.session import SessionLocal
    return SessionLocal()


TERMINAL_JOB_STATES = ("completed", "completed_with_failures", "failed", "cancelled", "blocked")


@router.get("/jobs/{job_key}/events")
def job_events(job_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """text/event-stream of job progress snapshots until the job reaches a terminal state.
    Each poll opens its own short session (no connection held); the stream is tenant-scoped and ends
    after 10 minutes at most. Browsers read it with fetch() so the bearer header can be sent."""
    import json as _json
    import time as _time

    from fastapi.responses import StreamingResponse

    _job(db, user, job_key)                           # 404 for unknown / other-tenant jobs before streaming
    org_id = user.organization_id

    def stream():
        last, started, beat = None, _time.monotonic(), _time.monotonic()
        while _time.monotonic() - started < 600:
            s = stream_session_factory()
            try:
                job = s.execute(select(AIJob).where(AIJob.organization_id == org_id, AIJob.job_key == job_key)).scalar_one_or_none()
                if job is None:
                    yield "event: error\ndata: {\"detail\": \"job no longer exists\"}\n\n"
                    return
                view = _job_view(s, job)
            finally:
                s.close()
            payload = _json.dumps(view, default=str, sort_keys=True)
            if payload != last:
                last = payload
                yield f"event: progress\ndata: {payload}\n\n"
            if view.get("status") in TERMINAL_JOB_STATES:
                yield f"event: end\ndata: {_json.dumps({'status': view.get('status')})}\n\n"
                return
            if _time.monotonic() - beat > 15:
                beat = _time.monotonic()
                yield ": keep-alive\n\n"
            _time.sleep(1.0)
        yield "event: end\ndata: {\"status\": \"stream_timeout\"}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- memory export
@router.get("/memory/export")
def export_memory(job_key: str | None = None, user: User = Depends(require_roles(*ADMIN_ROLES)), db: Session = Depends(get_db)):
    """The tenant's shared AI working memory (every version), memory profiles and agent handoffs as one JSON
    document. Tenant-scoped; admin only; the export itself is audited."""
    import json as _json
    from datetime import datetime as _dt, timezone as _tz

    from fastapi.responses import Response

    from app.models.agent_network import AgentHandoff
    from app.models.background_policy import MemoryProfile
    from app.services.audit import record_audit_log

    org = user.organization_id
    mem_q = select(AIWorkingMemory).where(AIWorkingMemory.organization_id == org)
    if job_key:
        mem_q = mem_q.where(AIWorkingMemory.job_key == job_key)
    memory = db.execute(mem_q.order_by(AIWorkingMemory.job_key, AIWorkingMemory.kind, AIWorkingMemory.version)).scalars().all()
    profiles = db.execute(select(MemoryProfile).where(MemoryProfile.organization_id == org)).scalars().all()
    handoffs = db.execute(select(AgentHandoff).where(AgentHandoff.organization_id == org)).scalars().all()
    cols = lambda row: {c.name: getattr(row, c.key if hasattr(c, "key") else c.name) for c in row.__table__.columns}  # noqa: E731
    doc = {"format": "aiol-memory-export/1", "organization_id": str(org), "exported_at": _dt.now(_tz.utc).isoformat(),
           "canonical_store": "postgresql", "filter": {"job_key": job_key},
           "memory_profiles": [cols(p) for p in profiles],
           "working_memory": [{k: v for k, v in cols(m).items()} for m in memory],
           "agent_handoffs": [cols(h) for h in handoffs]}
    record_audit_log(db, organization_id=org, user_id=user.id, action="ai_memory.export", resource_type="organization",
                     resource_id=org, new_value={"items": len(memory), "job_key": job_key})
    db.commit()
    body = _json.dumps(doc, default=str, ensure_ascii=False, indent=1)
    name = f"memory-export-{_dt.now(_tz.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    return Response(body, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})
