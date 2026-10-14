"""Publication and Vancouver citation API (§33–§67, §71)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.publication import Publication
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import citation_resolver, publication_service as svc

router = APIRouter(tags=["publications"])
Editor = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES))
Reader = Depends(get_current_user)


class PublicationIn(BaseModel):
    knowledge_object_id: UUID
    title: str | None = Field(default=None, max_length=500)
    language: str = Field(default="en", max_length=10)


class SectionIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    section_key: str | None = Field(default=None, max_length=100)


class SentenceIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    kind: Literal["factual", "inference", "interpretation", "hypothesis", "narrative", "heading"] = "factual"
    claim_id: UUID | None = None
    section_id: UUID | None = None
    paragraph: int = Field(default=0, ge=0)
    extra_source_ids: list[UUID] = Field(default_factory=list, max_length=100)


@router.get("/publications", response_model=Page[dict])
def list_publications(p: PaginationParams = Depends(), sort: SortParams = Depends(),
                      knowledge_object_id: UUID | None = None, status: str | None = None,
                      user: User = Reader, db: Session = Depends(get_db)):
    stmt = select(Publication).where(Publication.organization_id == user.organization_id)
    if knowledge_object_id:
        stmt = stmt.where(Publication.knowledge_object_id == knowledge_object_id)
    if status:
        stmt = stmt.where(Publication.status == status)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, Publication, sort, default_field="created_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.publication_out(x) for x in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/publications", status_code=201)
def create_publication(body: PublicationIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.publication_out(svc.create_publication(
        db, organization_id=user.organization_id, knowledge_object_id=body.knowledge_object_id,
        title=body.title, language=body.language))


@router.post("/publications/{publication_id}/sections", status_code=201)
def add_section(publication_id: UUID, body: SectionIn, user: User = Editor,
                db: Session = Depends(get_db)) -> dict:
    sec = svc.add_section(db, organization_id=user.organization_id, publication_id=publication_id,
                          title=body.title, section_key=body.section_key)
    return {"id": str(sec.id), "title": sec.title, "section_key": sec.section_key, "position": sec.position}


@router.post("/publications/{publication_id}/sentences", status_code=201)
def add_sentence(publication_id: UUID, body: SentenceIn, user: User = Editor,
                 db: Session = Depends(get_db)) -> dict:
    return svc.add_sentence(db, organization_id=user.organization_id, publication_id=publication_id,
                            text=body.text, kind=body.kind, claim_id=body.claim_id,
                            paragraph=body.paragraph, section_id=body.section_id,
                            extra_source_ids=body.extra_source_ids)


@router.post("/publications/{publication_id}/resolve")
def resolve(publication_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return citation_resolver.resolve(db, organization_id=user.organization_id, publication_id=publication_id)


@router.get("/publications/{publication_id}")
def render(publication_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.render(db, organization_id=user.organization_id, publication_id=publication_id)


@router.get("/publications/{publication_id}/references")
def references(publication_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> list[dict]:
    return citation_resolver.reference_list(db, organization_id=user.organization_id,
                                            publication_id=publication_id)


@router.get("/publications/{publication_id}/citation-audit")
def citation_audit(publication_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.integrity_audit(db, organization_id=user.organization_id, publication_id=publication_id)
