"""Federated research API (pilot-ready). Sources only from discovery; evidence via human review."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES
from app.models.research_federation import ResearchHit, ResearchProviderRun, ResearchQuery, ResearchQuestion
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortDirection, SortParams, apply_sort
from app.security.dependencies import get_current_user, require_roles
from app.services import federated_research_service as svc

router = APIRouter(prefix="/research", tags=["federated-research"])
Editor = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES))
Reader = Depends(get_current_user)


class KeywordSearchIn(BaseModel):
    knowledge_object_id: UUID
    keyword_ids: list[UUID] = Field(default_factory=list, max_length=50)
    mode: Literal["single", "multi", "exact", "boolean", "agent"]
    boolean_query: str | None = Field(default=None, max_length=1000)


class QuestionIn(BaseModel):
    knowledge_object_id: UUID | None = None
    subject: str = Field(min_length=1, max_length=300)
    compound: str | None = Field(default=None, max_length=300)
    compounds: list[str] = Field(default_factory=list, max_length=8)
    related_species: list[str] = Field(default_factory=list, max_length=8)
    outcome: str | None = Field(default=None, max_length=300)
    population: str | None = Field(default=None, max_length=100)
    question_text: str | None = Field(default=None, max_length=2000)
    mode: Literal["gap_driven", "user_driven", "exploratory", "continuous"] = "user_driven"


class FindMoreIn(BaseModel):
    route: Literal["direct_subject", "compound_human", "mechanistic", "co_occurrence",
                   "indirect_taxonomic", "indirect_analogous_species", "indirect_formulation", "combination"]
    extra_terms: list[str] = Field(default_factory=list, max_length=20)


class ReviewIn(BaseModel):
    decision: Literal["approve", "reject"]
    subject_tested: str | None = Field(default=None, max_length=300)
    evidence_strength: Literal["very_low", "low", "moderate", "high"] | None = None
    note: str | None = Field(default=None, max_length=2000)


@router.post("/federated/keyword-search", status_code=201)
def keyword_search(body: KeywordSearchIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.keyword_search(db, organization_id=user.organization_id, actor=user.id, knowledge_object_id=body.knowledge_object_id,
                              keyword_ids=body.keyword_ids, mode=body.mode, boolean_query=body.boolean_query)


@router.post("/questions", status_code=201)
def create_question(body: QuestionIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.create_question(db, organization_id=user.organization_id, actor=user.id, **body.model_dump())


@router.get("/questions", response_model=Page[dict])
def list_questions(p: PaginationParams = Depends(), sort: SortParams = Depends(), user: User = Reader, db: Session = Depends(get_db)):
    stmt = select(ResearchQuestion).where(ResearchQuestion.organization_id == user.organization_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = apply_sort(stmt, ResearchQuestion, sort, default_field="created_at", default_dir=SortDirection.DESC)
    rows = db.execute(stmt.limit(p.limit).offset(p.offset)).scalars().all()
    return Page(items=[{"id": r.id, "question_text": r.question_text, "subject": r.subject, "compound": r.compound, "outcome": r.outcome,
                        "population": r.population, "knowledge_object_id": r.knowledge_object_id, "created_at": r.created_at} for r in rows],
                total=total, limit=p.limit, offset=p.offset)


@router.get("/questions/{question_id}/evidence-map")
def evidence_map(question_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.evidence_map(db, organization_id=user.organization_id, question_id=question_id)


@router.get("/questions/{question_id}/evidence-graph")
def evidence_graph(question_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.evidence_graph(db, organization_id=user.organization_id, question_id=question_id)


@router.post("/questions/{question_id}/find-more", status_code=201)
def find_more(question_id: UUID, body: FindMoreIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.find_more(db, organization_id=user.organization_id, actor=user.id, question_id=question_id, route=body.route,
                         extra_terms=body.extra_terms)


@router.post("/questions/{question_id}/extract-candidates")
def extract(question_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.extract_candidates(db, organization_id=user.organization_id, question_id=question_id)


@router.post("/evidence-candidates/{evidence_id}/review")
def review(evidence_id: UUID, body: ReviewIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    ev = svc.review_candidate(db, organization_id=user.organization_id, evidence_id=evidence_id, decision=body.decision,
                              subject_tested=body.subject_tested, evidence_strength=body.evidence_strength, note=body.note)
    return {"id": str(ev.id), "status": ev.status.value, "directness": ev.directness.value, "route": ev.evidence_route,
            "subject_tested": ev.subject_tested, "human_reviewed": ev.human_reviewed}


@router.get("/sources/{source_id}/detail")
def source_detail(source_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.source_detail(db, organization_id=user.organization_id, source_id=source_id)


@router.get("/keywords/{keyword_id}/chain")
def keyword_chain(keyword_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.keyword_chain(db, organization_id=user.organization_id, keyword_id=keyword_id)


@router.get("/queries/{query_id}")
def query_detail(query_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    rq = db.execute(select(ResearchQuery).where(ResearchQuery.id == query_id, ResearchQuery.organization_id == user.organization_id)).scalar_one_or_none()
    if rq is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Query not found.")
    runs = db.execute(select(ResearchProviderRun).where(ResearchProviderRun.research_query_id == rq.id)).scalars().all()
    out = []
    for r in runs:
        hits = db.execute(select(ResearchHit).where(ResearchHit.provider_run_id == r.id).order_by(ResearchHit.rank)).scalars().all()
        out.append({"provider": r.provider, "status": r.status, "error": r.error, "result_count": r.result_count, "duration_ms": r.duration_ms,
                    "hits": [{"rank": h.rank, "title": h.title, "doi": h.doi, "pmid": h.pmid, "source_id": str(h.source_id) if h.source_id else None,
                              "matched_on": h.matched_on} for h in hits]})
    return {"id": str(rq.id), "query": rq.query_text, "mode": rq.mode, "route": rq.route, "research_task_id": str(rq.research_task_id),
            "providers": out}


@router.post("/knowledge-gaps/{gap_id}/find-more", status_code=201)
def gap_find_more(gap_id: UUID, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.find_more_for_gap(db, organization_id=user.organization_id, actor=user.id, gap_id=gap_id)



class AcquireIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


@router.post("/sources/{source_id}/acquire-full-text")
def acquire_full_text(source_id: UUID, body: AcquireIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.acquire_full_text(db, organization_id=user.organization_id, source_id=source_id, url=body.url)


class AttachFullTextIn(BaseModel):
    document_id: UUID


class AccessStateIn(BaseModel):
    state: str
    reason: str | None = Field(default=None, max_length=500)


@router.post("/sources/{source_id}/attach-full-text")
def attach_full_text(source_id: UUID, body: AttachFullTextIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    """Attach a document the user uploaded (POST /documents/upload) as this source's full text."""
    return svc.attach_full_text(db, organization_id=user.organization_id, source_id=source_id,
                                document_id=body.document_id, actor_user_id=user.id)


@router.post("/sources/{source_id}/access-state")
def set_access_state(source_id: UUID, body: AccessStateIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.set_access_state(db, organization_id=user.organization_id, source_id=source_id,
                                state=body.state, reason=body.reason)


class DependencyIn(BaseModel):
    depends_on_source_id: UUID
    relation: Literal["cites", "reviews", "reanalyses", "same_study", "preprint_of", "retracts", "corrects"]
    note: str | None = Field(default=None, max_length=500)


class SaturationIn(BaseModel):
    reason: str | None = None


@router.post("/sources/{source_id}/dependencies", status_code=201)
def add_dependency(source_id: UUID, body: DependencyIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.add_dependency(db, organization_id=user.organization_id, source_id=source_id,
                              depends_on_source_id=body.depends_on_source_id, relation=body.relation, note=body.note)


@router.get("/questions/{question_id}/dependency-graph")
def dependency_graph(question_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.dependency_graph(db, organization_id=user.organization_id, question_id=question_id)


@router.get("/questions/{question_id}/saturation")
def saturation(question_id: UUID, user: User = Reader, db: Session = Depends(get_db)) -> dict:
    return svc.saturation(db, organization_id=user.organization_id, question_id=question_id)


@router.post("/questions/{question_id}/saturation")
def declare_saturation(question_id: UUID, body: SaturationIn, user: User = Editor, db: Session = Depends(get_db)) -> dict:
    return svc.declare_saturation(db, organization_id=user.organization_id, question_id=question_id, reason=body.reason)
