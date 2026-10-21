"""
Command workspace API (prompt v4.0 §46–§54; ADR-125). Every route is scoped to the signed-in user's own
commands; another user's command answers 404.

    GET    /workspace/commands                       mine: active, drafts, running, finished, archived
    GET    /workspace/commands/resumable             unfinished work to offer on return (§50)
    POST   /workspace/commands                       new command (a draft, saved immediately)
    GET    /workspace/commands/{id}
    PUT    /workspace/commands/{id}/draft            autosave; 409 when another tab saved newer text
    POST   /workspace/commands/{id}/plan             intent + explicit scope + budget plan, before running
    POST   /workspace/commands/{id}/run              freeze this version and execute it (202)
    POST   /workspace/commands/{id}/regenerate       run the last request again as a new version
    POST   /workspace/commands/{id}/resume           continue unfinished model work from its checkpoint
    POST   /workspace/commands/{id}/cancel
    GET    /workspace/commands/{id}/versions
    GET    /workspace/commands/{id}/versions/{v}
    GET    /workspace/commands/{id}/compare?a=&b=
    POST   /workspace/commands/{id}/versions/{v}/restore
    POST   /workspace/commands/{id}/archive · /unarchive
    DELETE /workspace/commands/{id}?permanent=true   only with explicit permanent=true (§49)
    POST   /workspace/parse                          what the parser would propose for a text
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.user import User
from app.models.workspace import WorkspaceCommand, WorkspaceCommandVersion
from app.schemas.common import Page, PaginationParams, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import workspace_service as svc
from app.services.audit import record_audit_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workspace", tags=["workspace"])
Reader = Depends(get_current_user)
Editor = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES))


class CommandCreate(BaseModel):
    text: str = Field(default="", max_length=20000)
    title: str | None = Field(default=None, max_length=300)
    knowledge_object_id: UUID | None = None
    category_id: UUID | None = None
    scope: dict | None = None


class DraftSave(BaseModel):
    text: str = Field(default="", max_length=20000)
    base_revision: int | None = None
    scope: dict | None = None
    selected_source_ids: list[UUID] | None = None
    attachments: list[UUID] | None = None
    routing_config: dict | None = Field(default=None, alias="model_config")
    budget: dict | None = None
    intent: str | None = None

    model_config = {"populate_by_name": True}


class ParseRequest(BaseModel):
    text: str = Field(max_length=20000)


def _mine(db: Session, user: User, command_id: UUID) -> WorkspaceCommand:
    return svc.get_command(db, organization_id=user.organization_id, user_id=user.id, command_id=command_id)


def _dispatch(cmd: WorkspaceCommand, version: int) -> None:
    from app.workers.tasks import execute_workspace_command

    try:
        execute_workspace_command.delay(str(cmd.id), version)
    except Exception as exc:  # broker down: the version stays queued and /resume re-runs it
        logger.warning("workspace dispatch failed for %s v%s: %s", cmd.id, version, exc)


@router.post("/parse")
def parse(body: ParseRequest, user: User = Reader) -> dict:
    return svc.parse(body.text)


@router.get("/commands", response_model=Page[dict])
def list_commands(state: str | None = None, archived: bool = False, knowledge_object_id: UUID | None = None,
                  q: str | None = Query(default=None, max_length=200), p: PaginationParams = Depends(),
                  sort: SortParams = Depends(), user: User = Reader, db: Session = Depends(get_db)):
    stmt = select(WorkspaceCommand).where(WorkspaceCommand.organization_id == user.organization_id,
                                          WorkspaceCommand.user_id == user.id)
    stmt = stmt.where(WorkspaceCommand.archived_at.isnot(None) if archived else WorkspaceCommand.archived_at.is_(None))
    if state:
        stmt = stmt.where(WorkspaceCommand.state == state)
    if knowledge_object_id:
        stmt = stmt.where(WorkspaceCommand.knowledge_object_id == knowledge_object_id)
    if q:
        stmt = stmt.where(WorkspaceCommand.id.in_(select(WorkspaceCommandVersion.command_id).where(
            WorkspaceCommandVersion.text.ilike(f"%{q}%"))))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    if sort.sort_by:
        stmt = apply_sort(stmt, WorkspaceCommand, sort, default_field="last_activity_at")
    else:   # default: most recent activity first, never-run drafts last (unchanged)
        stmt = stmt.order_by(WorkspaceCommand.last_activity_at.desc().nullslast(), WorkspaceCommand.id)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.command_out(db, c) for c in rows], total=total, limit=p.limit, offset=p.offset)


@router.get("/commands/resumable")
def resumable(user: User = Reader, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(WorkspaceCommand).where(
        WorkspaceCommand.organization_id == user.organization_id, WorkspaceCommand.user_id == user.id,
        WorkspaceCommand.archived_at.is_(None),
        WorkspaceCommand.state.in_(("queued", "running", "blocked")))
        .order_by(WorkspaceCommand.last_activity_at.desc())).scalars().all()
    drafts = db.execute(select(WorkspaceCommand).where(
        WorkspaceCommand.organization_id == user.organization_id, WorkspaceCommand.user_id == user.id,
        WorkspaceCommand.archived_at.is_(None), WorkspaceCommand.state == "draft")
        .order_by(WorkspaceCommand.last_activity_at.desc()).limit(5)).scalars().all()
    return [{**svc.command_out(db, c), "offer": ["continue", "view_result", "restart"]} for c in rows] + \
           [{**svc.command_out(db, c), "offer": ["continue_editing"]} for c in drafts
            if svc.get_version(db, c).text.strip()]


@router.post("/commands", status_code=201)
def create(body: CommandCreate, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    cmd = svc.create(db, organization_id=user.organization_id, user_id=user.id, text=body.text, title=body.title,
                     knowledge_object_id=body.knowledge_object_id, category_id=body.category_id, scope=body.scope)
    return svc.command_out(db, cmd)


@router.get("/commands/{command_id}")
def get_command(command_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.command_out(db, _mine(db, user, command_id))


@router.put("/commands/{command_id}/draft")
def save_draft(command_id: UUID, body: DraftSave, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    cmd = _mine(db, user, command_id)
    v = svc.save_draft(db, cmd, text=body.text, base_revision=body.base_revision, scope=body.scope,
                       selected_source_ids=body.selected_source_ids, attachments=body.attachments,
                       model_config=body.routing_config, budget=body.budget, intent=body.intent)
    return {"command_id": str(cmd.id), "saved": True, "version": svc.version_out(v)}


@router.post("/commands/{command_id}/plan")
def plan(command_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    cmd = _mine(db, user, command_id)
    return svc.version_out(svc.plan(db, cmd))


@router.post("/commands/{command_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run(command_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    cmd = _mine(db, user, command_id)
    v = svc.start(db, cmd)
    _dispatch(cmd, v.version)
    db.expire_all()
    return svc.command_out(db, _mine(db, user, command_id))


@router.post("/commands/{command_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
def regenerate(command_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    cmd = _mine(db, user, command_id)
    v = svc.regenerate(db, cmd)
    _dispatch(cmd, v.version)
    db.expire_all()
    return svc.command_out(db, _mine(db, user, command_id))


@router.post("/commands/{command_id}/resume")
def resume(command_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    cmd = _mine(db, user, command_id)
    outcome = svc.resume(db, cmd)
    db.expire_all()
    return {"outcome": outcome, "command": svc.command_out(db, _mine(db, user, command_id))}


@router.post("/commands/{command_id}/cancel")
def cancel(command_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    cmd = _mine(db, user, command_id)
    svc.cancel(db, cmd)
    return svc.command_out(db, cmd)


@router.get("/commands/{command_id}/versions")
def versions(command_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> list[dict]:
    cmd = _mine(db, user, command_id)
    rows = db.execute(select(WorkspaceCommandVersion).where(WorkspaceCommandVersion.command_id == cmd.id)
                      .order_by(WorkspaceCommandVersion.version.desc())).scalars().all()
    return [svc.version_out(v) for v in rows]


@router.get("/commands/{command_id}/versions/{version}")
def version(command_id: UUID, version: int, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.version_out(svc.get_version(db, _mine(db, user, command_id), version))


@router.get("/commands/{command_id}/compare")
def compare(command_id: UUID, a: int, b: int, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.compare(db, _mine(db, user, command_id), a, b)


@router.post("/commands/{command_id}/versions/{version}/restore")
def restore(command_id: UUID, version: int, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.version_out(svc.restore(db, _mine(db, user, command_id), version))


@router.post("/commands/{command_id}/archive")
def archive(command_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    cmd = _mine(db, user, command_id)
    cmd.archived_at = datetime.now(timezone.utc)
    db.commit()
    return svc.command_out(db, cmd)


@router.post("/commands/{command_id}/unarchive")
def unarchive(command_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    cmd = _mine(db, user, command_id)
    cmd.archived_at = None
    db.commit()
    return svc.command_out(db, cmd)


@router.delete("/commands/{command_id}", status_code=204, response_class=Response)
def delete(command_id: UUID, permanent: bool = False, user: User = Editor, db: Session = Depends(get_db)) -> Response:
    """§49 — history is not destroyed by accident. Without `permanent=true` this refuses and points to
    archive; with it, the command and every version are erased and the erasure is audited."""
    cmd = _mine(db, user, command_id)
    if not permanent:
        raise HTTPException(400, "Deleting erases every version permanently. Archive instead, or repeat with "
                                 "permanent=true to confirm.")
    if cmd.state in ("queued", "running"):
        raise HTTPException(409, "Cancel the running command before deleting it.")
    record_audit_log(db, organization_id=user.organization_id, user_id=user.id, action="workspace.command_deleted",
                     resource_type="workspace_command", resource_id=cmd.id,
                     old_value={"versions": cmd.current_version, "title": cmd.title})
    db.delete(cmd)
    db.commit()
    return Response(status_code=204)
