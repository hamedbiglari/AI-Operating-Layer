"""Categories, section schema, matrix cells and the Master Topic Matrix (ADR-114)."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.knowledge_schema import Category, KnowledgeSection, SectionDefinition, SectionPropagation
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import knowledge_schema_service as svc

router = APIRouter(tags=["knowledge-schema"])
Editor = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES))
Reader = Depends(get_current_user)


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    starter: Literal["medicinal_plant", "device", "generic"] | None = None
    parent_category_id: UUID | None = None


class SectionDefinitionIn(BaseModel):
    key: str = Field(min_length=2, max_length=100)
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    required: bool = True
    discovered_from_topic_id: UUID | None = None
    discovered_evidence_id: UUID | None = None


class SectionStatusIn(BaseModel):
    status: str
    rationale: str | None = Field(default=None, max_length=2000)


class PropagationIn(BaseModel):
    state: Literal["evaluated", "skipped"]
    resulting_status: str | None = None
    note: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------- categories
@router.get("/categories", response_model=Page[dict])
def list_categories(p: PaginationParams = Depends(), sort: SortParams = Depends(),
                    user: User = Reader, db: Session = Depends(get_db)):
    stmt = select(Category).where(Category.organization_id == user.organization_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, Category, sort, default_field="created_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.category_out(c) for c in rows], total=total, limit=p.limit, offset=p.offset)


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    cat = svc.create_category(db, organization_id=user.organization_id, name=body.name,
                              description=body.description, starter=body.starter,
                              parent_category_id=body.parent_category_id)
    return svc.category_out(cat)


@router.get("/categories/{category_id}")
def get_category(category_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.category_out(svc.category_or_404(db, user.organization_id, category_id))


@router.get("/categories/{category_id}/sections")
def list_section_definitions(category_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> list[dict]:
    svc.category_or_404(db, user.organization_id, category_id)
    rows = db.execute(select(SectionDefinition).where(
        SectionDefinition.organization_id == user.organization_id,
        SectionDefinition.category_id == category_id).order_by(SectionDefinition.position)).scalars().all()
    return [svc.definition_out(d) for d in rows]


@router.post("/categories/{category_id}/sections", status_code=201)
def add_section_definition(category_id: UUID, body: SectionDefinitionIn, user: User = Editor,
                           db: Session = Depends(get_db)) -> dict:
    origin = "discovered" if body.discovered_from_topic_id else "user_added"
    sd = svc.add_section_definition(db, organization_id=user.organization_id, category_id=category_id,
                                    key=body.key, title=body.title, description=body.description,
                                    required=body.required, origin=origin,
                                    discovered_from_topic_id=body.discovered_from_topic_id,
                                    discovered_evidence_id=body.discovered_evidence_id)
    return svc.definition_out(sd)


@router.get("/categories/{category_id}/matrix")
def matrix(category_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.matrix(db, organization_id=user.organization_id, category_id=category_id)


# ---------------------------------------------------------------- a topic's sections
@router.get("/knowledge/{knowledge_object_id}/sections")
def list_sections(knowledge_object_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(KnowledgeSection).where(
        KnowledgeSection.organization_id == user.organization_id,
        KnowledgeSection.knowledge_object_id == knowledge_object_id)
        .order_by(KnowledgeSection.section_key)).scalars().all()
    return [svc.section_out(s) for s in rows]


@router.post("/knowledge/{knowledge_object_id}/sections/apply-schema", status_code=201)
def apply_schema(knowledge_object_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.apply_schema(db, organization_id=user.organization_id, knowledge_object_id=knowledge_object_id)


@router.post("/knowledge/{knowledge_object_id}/sections/recalculate")
def recalculate(knowledge_object_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.recalculate_topic(db, organization_id=user.organization_id,
                                 knowledge_object_id=knowledge_object_id)


@router.patch("/knowledge-sections/{section_id}")
def set_status(section_id: UUID, body: SectionStatusIn, user: User = Editor,
               db: Session = Depends(get_db)) -> dict:
    return svc.set_section_status(db, organization_id=user.organization_id, section_id=section_id,
                                  status=body.status, rationale=body.rationale)


# ---------------------------------------------------------------- cross-topic proposals
@router.get("/section-propagations", response_model=Page[dict])
def list_propagations(p: PaginationParams = Depends(), sort: SortParams = Depends(), state: str | None = None,
                      user: User = Reader, db: Session = Depends(get_db)):
    stmt = select(SectionPropagation).where(SectionPropagation.organization_id == user.organization_id)
    if state:
        stmt = stmt.where(SectionPropagation.state == state)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, SectionPropagation, sort, default_field="created_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[svc.propagation_out(r) for r in rows], total=total, limit=p.limit, offset=p.offset)


@router.patch("/section-propagations/{propagation_id}")
def decide(propagation_id: UUID, body: PropagationIn, user: User = Editor,
           db: Session = Depends(get_db)) -> dict:
    return svc.decide_propagation(db, organization_id=user.organization_id, propagation_id=propagation_id,
                                  state=body.state, resulting_status=body.resulting_status, note=body.note,
                                  actor_user_id=user.id)
