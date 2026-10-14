"""Website management API (ADR-118).

Admin endpoints (`/website/...`) are for owners and admins of the workspace. Public endpoints
(`/public/website/{org_slug}/...`) are what the marketing site calls: read published posts and enabled
sections, subscribe, unsubscribe. The subscribe endpoint is rate-limited per client, ignores bot-filled
honeypots, never reveals whether an address is already on the list, and refuses to store an address
without explicit consent.
"""
from __future__ import annotations

import csv
import io
import secrets
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import ADMIN_ROLES
from app.models.organization import Organization
from app.models.user import User
from app.models.website import NewsletterSubscriber, SitePost, SitePostRevision, SiteSection
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import require_roles
from app.security.rate_limit import check_rate_limit

router = APIRouter(tags=["website"])
Admin = Depends(require_roles(*ADMIN_ROLES))
Lang = Literal["en", "fa"]

# the home page's real sections, in their real order — what the admin can show, hide, reorder and retitle
DEFAULT_HOME_SECTIONS = [
    ("hero", "Hero"), ("discovery", "Positioning bar"), ("problem", "Problem"), ("how", "How it works"), ("research", "Research engine"),
    ("sources", "Source transparency"), ("evidence", "Evidence, knowledge object & graph"), ("demo", "Interactive demo"),
    ("access", "Access intelligence"), ("before-after", "Before / after"), ("use-cases", "Use cases"),
    ("commerce", "Commerce & search"), ("control", "Control, memory & cost"), ("trust", "Trust & security"),
    ("pricing", "Pricing"), ("faq", "FAQ"), ("final", "Final call to action"),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================ posts (admin)
class Reference(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    publisher: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=1000)
    accessed: str | None = Field(default=None, max_length=40)


class PostIn(BaseModel):
    lang: Lang = "en"
    slug: str = Field(min_length=2, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=2, max_length=300)
    excerpt: str | None = Field(default=None, max_length=1000)
    body: str = Field(default="", max_length=200_000)
    author_name: str | None = Field(default=None, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=20)
    references: list[Reference] = Field(default_factory=list, max_length=100)
    translation_of: uuid.UUID | None = None          # link this post to its other-language version


class PostPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    excerpt: str | None = Field(default=None, max_length=1000)
    body: str | None = Field(default=None, max_length=200_000)
    author_name: str | None = Field(default=None, max_length=200)
    tags: list[str] | None = Field(default=None, max_length=20)
    references: list[Reference] | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)       # what changed, kept in the update history


def _post_out(p: SitePost, full: bool = True) -> dict:
    out = {"id": str(p.id), "lang": p.lang, "slug": p.slug, "title": p.title, "excerpt": p.excerpt,
           "author_name": p.author_name, "status": p.status, "published_at": p.published_at,
           "updated_at": p.updated_at, "created_at": p.created_at, "version": p.version, "tags": p.tags or [],
           "translation_group": str(p.translation_group) if p.translation_group else None}
    if full:
        out["body"] = p.body
        out["references"] = p.references or []
    return out


def _get_post(db: Session, org_id: uuid.UUID, post_id: uuid.UUID) -> SitePost:
    p = db.execute(select(SitePost).where(SitePost.id == post_id, SitePost.organization_id == org_id)).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Post not found.")
    return p


def _revision(db: Session, p: SitePost, user: User, note: str | None) -> None:
    db.add(SitePostRevision(organization_id=p.organization_id, post_id=p.id, version=p.version, title=p.title,
                            body=p.body, note=note, changed_by=user.id))


@router.get("/website/posts", response_model=Page[dict])
def list_posts(p: PaginationParams = Depends(), sort: SortParams = Depends(), lang: Lang | None = None,
               status: str | None = None, user: User = Admin, db: Session = Depends(get_db)):
    stmt = select(SitePost).where(SitePost.organization_id == user.organization_id)
    if lang:
        stmt = stmt.where(SitePost.lang == lang)
    if status:
        stmt = stmt.where(SitePost.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, SitePost, sort, default_field="updated_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[_post_out(x, full=False) for x in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/website/posts", status_code=201)
def create_post(body: PostIn, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    exists = db.execute(select(SitePost.id).where(SitePost.organization_id == user.organization_id,
                        SitePost.lang == body.lang, SitePost.slug == body.slug)).first()
    if exists:
        raise HTTPException(409, "A post with this address already exists in this language.")
    group = None
    if body.translation_of:
        other = _get_post(db, user.organization_id, body.translation_of)
        if other.lang == body.lang:
            raise HTTPException(422, "A translation must be in the other language.")
        group = other.translation_group or other.id
        other.translation_group = group
    p = SitePost(organization_id=user.organization_id, lang=body.lang, slug=body.slug, title=body.title,
                 excerpt=body.excerpt, body=body.body, author_name=body.author_name, tags=body.tags,
                 references=[r.model_dump() for r in body.references], translation_group=group, version=1)
    db.add(p)
    db.flush()
    _revision(db, p, user, "Created")
    db.commit()
    db.refresh(p)
    return _post_out(p)


@router.get("/website/posts/{post_id}")
def get_post(post_id: uuid.UUID, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    return _post_out(_get_post(db, user.organization_id, post_id))


@router.patch("/website/posts/{post_id}")
def update_post(post_id: uuid.UUID, body: PostPatch, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    p = _get_post(db, user.organization_id, post_id)
    data = body.model_dump(exclude_unset=True)
    note = data.pop("note", None)
    if "references" in data and data["references"] is not None:
        data["references"] = [dict(r) for r in data["references"]]
    if not data:
        return _post_out(p)
    for k, v in data.items():
        setattr(p, k, v)
    p.version += 1
    _revision(db, p, user, note or "Edited")
    db.commit()
    db.refresh(p)
    return _post_out(p)


@router.post("/website/posts/{post_id}/publish")
def publish_post(post_id: uuid.UUID, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    p = _get_post(db, user.organization_id, post_id)
    if not p.author_name:
        raise HTTPException(422, "A published post needs an author.")
    if not p.body.strip():
        raise HTTPException(422, "A post with no body cannot be published.")
    p.status = "published"
    p.published_at = p.published_at or _now()
    db.commit()
    db.refresh(p)
    return _post_out(p)


@router.post("/website/posts/{post_id}/unpublish")
def unpublish_post(post_id: uuid.UUID, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    p = _get_post(db, user.organization_id, post_id)
    p.status = "draft"
    db.commit()
    db.refresh(p)
    return _post_out(p)


@router.delete("/website/posts/{post_id}", status_code=204)
def delete_post(post_id: uuid.UUID, user: User = Admin, db: Session = Depends(get_db)) -> Response:
    db.delete(_get_post(db, user.organization_id, post_id))
    db.commit()
    return Response(status_code=204)


@router.get("/website/posts/{post_id}/revisions")
def post_revisions(post_id: uuid.UUID, user: User = Admin, db: Session = Depends(get_db)) -> list[dict]:
    _get_post(db, user.organization_id, post_id)
    rows = db.execute(select(SitePostRevision).where(SitePostRevision.post_id == post_id)
                      .order_by(SitePostRevision.version.desc())).scalars().all()
    return [{"version": r.version, "title": r.title, "note": r.note, "changed_at": r.created_at} for r in rows]


# ============================================================ sections (admin)
class SectionPatch(BaseModel):
    enabled: bool | None = None
    position: int | None = Field(default=None, ge=0, le=999)
    heading: str | None = Field(default=None, max_length=300)
    subheading: str | None = Field(default=None, max_length=2000)


def _section_out(s: SiteSection) -> dict:
    return {"id": str(s.id), "page": s.page, "lang": s.lang, "section_key": s.section_key, "label": s.label,
            "position": s.position, "enabled": s.enabled, "heading": s.heading, "subheading": s.subheading}


@router.get("/website/sections")
def list_sections(page: str = "home", lang: Lang = "en", user: User = Admin, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(SiteSection).where(SiteSection.organization_id == user.organization_id,
                      SiteSection.page == page, SiteSection.lang == lang).order_by(SiteSection.position)).scalars().all()
    if not rows and page == "home":          # first visit: the page's real sections, all enabled, in their real order
        for i, (key, label) in enumerate(DEFAULT_HOME_SECTIONS):
            db.add(SiteSection(organization_id=user.organization_id, page="home", lang=lang, section_key=key,
                               label=label, position=i, enabled=True))
        db.commit()
        return list_sections(page, lang, user, db)
    return [_section_out(s) for s in rows]


@router.patch("/website/sections/{section_id}")
def update_section(section_id: uuid.UUID, body: SectionPatch, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    s = db.execute(select(SiteSection).where(SiteSection.id == section_id,
                   SiteSection.organization_id == user.organization_id)).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "Section not found.")
    if s.section_key == "hero" and body.enabled is False:
        raise HTTPException(422, "The hero carries the page's only H1 and cannot be hidden.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v.strip() or None if isinstance(v, str) else v)
    db.commit()
    db.refresh(s)
    return _section_out(s)


# ============================================================ subscribers (admin)
def _sub_out(s: NewsletterSubscriber) -> dict:
    return {"id": str(s.id), "email": s.email, "lang": s.lang, "status": s.status, "source": s.source,
            "consented_at": s.consented_at, "unsubscribed_at": s.unsubscribed_at, "created_at": s.created_at}


@router.get("/website/subscribers", response_model=Page[dict])
def list_subscribers(p: PaginationParams = Depends(), sort: SortParams = Depends(), status: str | None = None,
                     q: str | None = None, user: User = Admin, db: Session = Depends(get_db)):
    stmt = select(NewsletterSubscriber).where(NewsletterSubscriber.organization_id == user.organization_id)
    if status:
        stmt = stmt.where(NewsletterSubscriber.status == status)
    if q:
        stmt = stmt.where(NewsletterSubscriber.email.ilike(f"%{q.strip().lower()}%"))
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, NewsletterSubscriber, sort, default_field="created_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[_sub_out(x) for x in rows], total=total, limit=p.limit, offset=p.offset)


@router.get("/website/subscribers/export.csv")
def export_subscribers(user: User = Admin, db: Session = Depends(get_db)) -> StreamingResponse:
    rows = db.execute(select(NewsletterSubscriber).where(NewsletterSubscriber.organization_id == user.organization_id)
                      .order_by(NewsletterSubscriber.created_at)).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["email", "status", "language", "source", "consented_at", "unsubscribed_at"])
    for s in rows:
        # a cell starting with = + - @ would be run as a formula by a spreadsheet: neutralise it
        email = ("'" + s.email) if s.email[:1] in "=+-@" else s.email
        w.writerow([email, s.status, s.lang, s.source or "", s.consented_at.isoformat(),
                    s.unsubscribed_at.isoformat() if s.unsubscribed_at else ""])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="newsletter-subscribers.csv"'})


@router.post("/website/subscribers/{sub_id}/unsubscribe")
def admin_unsubscribe(sub_id: uuid.UUID, user: User = Admin, db: Session = Depends(get_db)) -> dict:
    s = db.execute(select(NewsletterSubscriber).where(NewsletterSubscriber.id == sub_id,
                   NewsletterSubscriber.organization_id == user.organization_id)).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "Subscriber not found.")
    s.status, s.unsubscribed_at = "unsubscribed", s.unsubscribed_at or _now()
    db.commit()
    return _sub_out(s)


@router.delete("/website/subscribers/{sub_id}", status_code=204)
def erase_subscriber(sub_id: uuid.UUID, user: User = Admin, db: Session = Depends(get_db)) -> Response:
    """Erasure on request: the row and the address are gone, not flagged."""
    s = db.execute(select(NewsletterSubscriber).where(NewsletterSubscriber.id == sub_id,
                   NewsletterSubscriber.organization_id == user.organization_id)).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "Subscriber not found.")
    db.delete(s)
    db.commit()
    return Response(status_code=204)


# ============================================================ public (the marketing site)
def _org(db: Session, slug: str) -> Organization:
    o = db.execute(select(Organization).where(Organization.slug == slug)).scalar_one_or_none()
    if o is None:
        raise HTTPException(404, "Not found.")
    return o


@router.get("/public/website/{org_slug}/posts")
def public_posts(org_slug: str, lang: Lang = "en", db: Session = Depends(get_db)) -> list[dict]:
    o = _org(db, org_slug)
    rows = db.execute(select(SitePost).where(SitePost.organization_id == o.id, SitePost.lang == lang,
                      SitePost.status == "published").order_by(SitePost.published_at.desc()).limit(50)).scalars().all()
    return [_post_out(p, full=False) for p in rows]


@router.get("/public/website/{org_slug}/posts/{slug}")
def public_post(org_slug: str, slug: str, lang: Lang = "en", db: Session = Depends(get_db)) -> dict:
    o = _org(db, org_slug)
    p = db.execute(select(SitePost).where(SitePost.organization_id == o.id, SitePost.lang == lang,
                   SitePost.slug == slug, SitePost.status == "published")).scalar_one_or_none()
    if p is None:
        raise HTTPException(404, "Not found.")
    out = _post_out(p)
    out["history"] = [{"version": r.version, "note": r.note, "changed_at": r.created_at} for r in db.execute(
        select(SitePostRevision).where(SitePostRevision.post_id == p.id).order_by(SitePostRevision.version)).scalars().all()]
    if p.translation_group:
        alt = db.execute(select(SitePost).where(SitePost.organization_id == o.id, SitePost.status == "published",
                         SitePost.translation_group == p.translation_group, SitePost.id != p.id)).scalars().first()
        out["alternate"] = {"lang": alt.lang, "slug": alt.slug} if alt else None
    return out


@router.get("/public/website/{org_slug}/sections")
def public_sections(org_slug: str, page: str = "home", lang: Lang = "en", db: Session = Depends(get_db)) -> list[dict]:
    o = _org(db, org_slug)
    rows = db.execute(select(SiteSection).where(SiteSection.organization_id == o.id, SiteSection.page == page,
                      SiteSection.lang == lang).order_by(SiteSection.position)).scalars().all()
    return [{"section_key": s.section_key, "position": s.position, "enabled": s.enabled,
             "heading": s.heading, "subheading": s.subheading} for s in rows]


class SubscribeIn(BaseModel):
    email: EmailStr
    lang: Lang = "en"
    source: str | None = Field(default=None, max_length=200)
    consent: bool
    consent_text: str = Field(min_length=10, max_length=1000)
    website: str | None = Field(default=None, max_length=200)     # honeypot: people never fill it in


@router.post("/public/website/{org_slug}/subscribe", status_code=202)
def public_subscribe(org_slug: str, body: SubscribeIn, request: Request, db: Session = Depends(get_db)) -> dict:
    client = (request.client.host if request.client else "unknown").rsplit(".", 1)[0]   # /24 for IPv4: no full IP kept
    rl = check_rate_limit(installation_id=f"subscribe:{org_slug}:{client}", limit=10, window_seconds=3600)
    if not rl.allowed:
        raise HTTPException(429, "Too many requests.", headers={"Retry-After": str(rl.retry_after)})
    accepted = {"status": "accepted", "message": "If the address is valid, it is on the list."}
    if body.website:                       # a bot filled the hidden field: pretend success, store nothing
        return accepted
    if not body.consent:
        raise HTTPException(422, "Consent is required to subscribe.")
    o = _org(db, org_slug)
    email = str(body.email).strip().lower()
    s = db.execute(select(NewsletterSubscriber).where(NewsletterSubscriber.organization_id == o.id,
                   NewsletterSubscriber.email == email)).scalar_one_or_none()
    if s is None:
        db.add(NewsletterSubscriber(organization_id=o.id, email=email, lang=body.lang, status="subscribed",
                                    source=body.source, consent_text=body.consent_text, consented_at=_now(),
                                    unsubscribe_token=secrets.token_urlsafe(32)))
    elif s.status == "unsubscribed":       # a fresh, explicit consent re-subscribes
        s.status, s.unsubscribed_at, s.consented_at, s.consent_text = "subscribed", None, _now(), body.consent_text
    db.commit()
    return accepted                        # the same answer either way: the list cannot be probed


@router.get("/public/website/{org_slug}/unsubscribe")
def public_unsubscribe(org_slug: str, token: str, db: Session = Depends(get_db)) -> dict:
    o = _org(db, org_slug)
    s = db.execute(select(NewsletterSubscriber).where(NewsletterSubscriber.organization_id == o.id,
                   NewsletterSubscriber.unsubscribe_token == token)).scalar_one_or_none()
    if s is not None and s.status != "unsubscribed":
        s.status, s.unsubscribed_at = "unsubscribed", _now()
        db.commit()
    return {"status": "unsubscribed"}
