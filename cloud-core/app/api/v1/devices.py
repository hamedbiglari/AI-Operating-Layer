"""
Device Intelligence API (ADR-138). Every route requires a session; admin routes require owner/admin.

    POST   /devices/challenges                          a single-use nonce for register or verify
    POST   /devices/credentials                         register this installation's public key (proof of possession)
    POST   /devices/credentials/{id}/verify             continuity check: sign a verify challenge
    GET    /devices/credentials                         installations linked to MY account
    DELETE /devices/credentials/{id}                    remove this installation from my account
    GET    /devices/admin/credentials                   tenant installations with evidence categories (admin)
    GET    /devices/admin/credentials/{id}              one installation, its linked accounts and observations (admin, audited)
    POST   /devices/admin/credentials/{id}/revoke       revoke (admin, audited)

Errors carry `detail = {"code", "message"}` so a client can branch on the code. A failure here must never block
sign-in: clients treat every device route as optional (ADR-138).
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ADMIN_ROLES
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.security.client_ip import client_ip
from app.security.dependencies import get_current_user, require_roles
from app.services import device_intelligence_service as svc

router = APIRouter(prefix="/devices", tags=["device-intelligence"])
Reader = Depends(get_current_user)
Admin = Depends(require_roles(*ADMIN_ROLES))

Platform = Literal["web", "windows", "macos", "android", "ios"]
KeyStorage = Literal["hardware", "os_keystore", "browser_non_extractable", "software", "unknown"]


class ChallengeIn(BaseModel):
    purpose: Literal["register", "verify"]
    credential_id: UUID | None = None


class RegisterIn(BaseModel):
    challenge_id: UUID
    nonce: str = Field(min_length=16, max_length=100)
    public_key: str = Field(min_length=40, max_length=400, description="base64 DER SubjectPublicKeyInfo, P-256")
    signature: str = Field(min_length=40, max_length=200, description="base64 ECDSA-SHA256, DER or P1363")
    platform: Platform
    key_storage: KeyStorage = "unknown"
    app_version: str | None = Field(default=None, max_length=40)
    os_family: str | None = Field(default=None, max_length=40)
    os_version: str | None = Field(default=None, max_length=40)


class VerifyIn(BaseModel):
    challenge_id: UUID
    nonce: str = Field(min_length=16, max_length=100)
    signature: str = Field(min_length=40, max_length=200)
    app_version: str | None = Field(default=None, max_length=40)


def _limit(user: User) -> None:
    from app.security.rate_limit import check_rate_limit

    result = check_rate_limit(installation_id=f"device-challenge:{user.id}", limit=30, window_seconds=60)
    if not result.allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            {"code": "rate_limited", "message": "Too many device requests."},
                            headers={"Retry-After": str(result.retry_after)})


@router.post("/challenges", status_code=status.HTTP_201_CREATED)
def challenge(body: ChallengeIn, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    _limit(user)
    return svc.issue_challenge(db, user=user, purpose=body.purpose, credential_id=body.credential_id)


@router.post("/credentials")
def register(body: RegisterIn, request: Request, response: Response, user: User = Reader,
             db: Session = Depends(get_db)) -> dict:
    cred, created = svc.register(
        db, user=user, challenge_id=body.challenge_id, nonce=body.nonce, public_key=body.public_key,
        signature=body.signature, platform=body.platform, key_storage=body.key_storage,
        app_version=body.app_version, os_family=body.os_family, os_version=body.os_version, ip=client_ip(request))
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return {**svc.credential_out(cred), "created": created}


@router.post("/credentials/{credential_id}/verify")
def verify(credential_id: UUID, body: VerifyIn, request: Request, user: User = Reader,
           db: Session = Depends(get_db)) -> dict:
    cred = svc.verify(db, user=user, credential_id=credential_id, challenge_id=body.challenge_id, nonce=body.nonce,
                      signature=body.signature, app_version=body.app_version, ip=client_ip(request))
    return svc.credential_out(cred)


@router.get("/credentials")
def mine(user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return {"items": svc.list_mine(db, user=user)}


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink(credential_id: UUID, request: Request, user: User = Reader, db: Session = Depends(get_db)) -> Response:
    svc.unlink_mine(db, user=user, credential_id=credential_id, ip=client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/credentials", response_model=Page[dict])
def admin_list(p: PaginationParams = Depends(), sort: SortParams = Depends(), state: Literal["active", "revoked"] | None = Query(default=None),
               user: User = Admin, db: Session = Depends(get_db)) -> Page[dict]:
    total, items = svc.admin_list(db, organization_id=user.organization_id, limit=p.limit, offset=p.offset,
                                  status_filter=state, sort=sort)
    return Page(items=items, total=total, limit=p.limit, offset=p.offset)


@router.get("/admin/credentials/{credential_id}")
def admin_detail(credential_id: UUID, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    return svc.admin_detail(db, actor=user, credential_id=credential_id)


@router.post("/admin/credentials/{credential_id}/revoke")
def admin_revoke(credential_id: UUID, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    return svc.admin_revoke(db, actor=user, credential_id=credential_id)
