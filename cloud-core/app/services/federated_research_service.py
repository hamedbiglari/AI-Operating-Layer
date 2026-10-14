"""
Federated research engine (pilot-ready).

Question -> query expansion -> multi-source search (Crossref, PubMed, Europe PMC, web) ->
deduplication (DOI, then PMID, then canonical title) -> access classification -> sources only.
Evidence candidates are a separate, explicit step and always land in human review
(`pending_review`); the engine never creates claims and never edits a knowledge object.

Honesty rules enforced here (and by database constraints from migration 0025):
  * a provider returning a record proves EXISTENCE, not ACCESS;
  * content_access reflects what the system actually holds: abstract_only when the API returned
    an abstract, metadata_only otherwise; never full_text_available from discovery;
  * compound / mechanistic / co-occurrence evidence is INDIRECT for the subject.
"""
from __future__ import annotations

import re
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote_plus
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.integrations.research.scholarly import ScholarlyRecord, default_providers, norm_doi
from app.models.ai_center import KnowledgeKeyword
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.enums import (EvidenceDirectness, EvidenceStatus, EvidenceStrength, ResearchMode,
                              ResearchTaskStatus, SourceRightsStatus)
from app.models.evidence import Evidence
from app.models.keyword_trace import KeywordTrace
from app.models.knowledge_object import KnowledgeObject
from app.models.research_dependency import NON_INDEPENDENT, ResearchIteration, SourceDependency
from app.models.research_federation import ResearchHit, ResearchProviderRun, ResearchQuery, ResearchQuestion
from app.models.research_task import ResearchTask
from app.models.source import Source
from app.services import research_project_service, research_task_service

NOT_REVIEWED_MESSAGE = "This source was found, but its full text has not been reviewed by the system."
INDIRECT_NOTE = ("Evidence about a compound is not evidence that the subject has the effect. It stays INDIRECT "
                 "unless the study tested the subject itself.")
SYNONYM_KINDS = ("primary", "scientific_name", "synonym", "common_name", "alias", "alternative_spelling", "language_variant")
from app.models.research_federation import DIRECT_CAPABLE_ROUTES  # noqa: E402

ROUTES = ("direct_subject", "compound_human", "mechanistic", "co_occurrence",
          "indirect_taxonomic", "indirect_analogous_species", "indirect_formulation", "combination")
# Terms: letters/digits (any script), hyphen, apostrophe, wildcard, dot, slash, colon, plus. Anything else
# (e.g. ';', '<', '{') is rejected: queries go to external APIs as parameters, never into SQL, but a
# research query has no reason to carry them.
_BOOL_TOKEN = re.compile(r'\s*("[^"]*"|\(|\)|\bAND\b|\bOR\b|\bNOT\b|[\w\-\'*./:+]+)\s*')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_title(title: str | None) -> str | None:
    if not title:
        return None
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:1000] or None


# ---------------------------------------------------------------- query building
def validate_boolean(q: str) -> str:
    q = q.strip()
    if not q or len(q) > 1000:
        raise HTTPException(422, "Query must be 1–1000 characters.")
    if q.count('"') % 2:
        raise HTTPException(422, "Unbalanced quotes in query.")
    depth = 0
    pos = 0
    prev_op = True
    while pos < len(q):
        m = _BOOL_TOKEN.match(q, pos)
        if not m or m.end() == pos:
            raise HTTPException(422, "Query contains characters that are not allowed.")
        tok = m.group(1)
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
            if depth < 0:
                raise HTTPException(422, "Unbalanced parentheses in query.")
        elif tok in ("AND", "OR", "NOT"):
            if prev_op and tok != "NOT":
                raise HTTPException(422, f"Operator {tok} is missing a term before it.")
            prev_op = True
            pos = m.end()
            continue
        prev_op = tok == "("
        pos = m.end()
    if depth:
        raise HTTPException(422, "Unbalanced parentheses in query.")
    if prev_op:
        raise HTTPException(422, "Query ends with an operator.")
    return q


def _quote(term: str) -> str:
    term = term.strip().replace('"', "")
    return f'"{term}"' if " " in term or "-" in term else term


def build_query(mode: str, terms: list[str], boolean_query: str | None = None, outcome_terms: list[str] | None = None) -> str:
    terms = [t for t in (x.strip() for x in terms) if t]
    if mode == "boolean":
        return validate_boolean(boolean_query or "")
    if not terms:
        raise HTTPException(422, "At least one keyword is required.")
    if mode == "single":
        return terms[0] if " " not in terms[0] else _quote(terms[0])
    if mode == "exact":
        return " AND ".join(f'"{t.replace(chr(34), "")}"' for t in terms)
    if mode == "multi":
        return "(" + " OR ".join(_quote(t) for t in terms) + ")"
    if mode == "agent":   # query expansion: synonyms OR-ed, outcome/mechanism terms AND-ed
        q = "(" + " OR ".join(_quote(t) for t in terms) + ")"
        if outcome_terms:
            q += " AND (" + " OR ".join(_quote(t) for t in outcome_terms) + ")"
        return q
    raise HTTPException(422, "mode must be single, multi, exact, boolean or agent")


def subject_terms(db: Session, organization_id: UUID, ko: KnowledgeObject | None, subject: str) -> list[str]:
    terms = [subject]
    if ko is not None:
        terms.append(ko.canonical_name)
        kws = db.execute(select(KnowledgeKeyword.keyword).where(
            KnowledgeKeyword.organization_id == organization_id, KnowledgeKeyword.knowledge_object_id == ko.id,
            KnowledgeKeyword.kind.in_(SYNONYM_KINDS))).scalars().all()
        terms += list(kws)
    seen, out = set(), []
    for t in terms:
        k = t.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(t.strip())
    return out[:12]


# ---------------------------------------------------------------- sources
def _acquisition_paths(rec: ScholarlyRecord, existing: dict | None) -> dict:
    p = dict(existing or {})
    title = rec.title or ""
    if rec.doi:
        p["doi"] = f"https://doi.org/{rec.doi}"
    if rec.pmid:
        p["pubmed"] = f"https://pubmed.ncbi.nlm.nih.gov/{rec.pmid}/"
    if rec.pmcid or rec.pmid:
        p["europepmc"] = (f"https://europepmc.org/article/PMC/{rec.pmcid}" if rec.pmcid
                          else f"https://europepmc.org/article/MED/{rec.pmid}")
    if rec.landing_url and rec.landing_url.startswith("https://"):
        p.setdefault("publisher", rec.landing_url)
    if title:
        p["library_search"] = f"https://search.worldcat.org/search?q={quote_plus(title[:250])}"
        p["scholar_search"] = f"https://scholar.google.com/scholar?q={quote_plus(title[:250])}"
    oa = list(dict.fromkeys((p.get("open_access") or []) + [u for u in rec.oa_urls if u.startswith("https://")]))
    p["open_access"] = oa
    return p


def _classify(src: Source, rec: ScholarlyRecord) -> None:
    parts = set(src.accessed_parts or [])
    parts.add("metadata")
    if rec.abstract and not src.abstract:
        src.abstract = rec.abstract[:20000]
    if src.abstract:
        parts.add("abstract")
    src.accessed_parts = sorted(parts)
    if not src.full_text_accessed:      # discovery never upgrades to full text
        src.content_access = "abstract_only" if "abstract" in parts else "metadata_only"
    if rec.open_access is True and src.rights_status == SourceRightsStatus.UNKNOWN:
        src.rights_status = SourceRightsStatus.OPEN
    src.existence_status = "confirmed"


def find_duplicate(db: Session, organization_id: UUID, rec: ScholarlyRecord) -> tuple[Source | None, str | None]:
    base = select(Source).where(Source.organization_id == organization_id)
    if rec.doi:
        s = db.execute(base.where(func.lower(Source.doi) == rec.doi)).scalars().first()
        if s:
            return s, "doi"
    if rec.pmid:
        s = db.execute(base.where(Source.pmid == rec.pmid)).scalars().first()
        if s:
            return s, "pmid"
    ct = canonical_title(rec.title)
    if ct and len(ct) >= 20:
        s = db.execute(base.where(Source.canonical_title == ct)).scalars().first()
        if s:
            return s, "canonical_title"
    return None, None


def upsert_source(db: Session, organization_id: UUID, rec: ScholarlyRecord) -> tuple[Source, str]:
    src, matched = find_duplicate(db, organization_id, rec)
    if src is None:
        src = Source(organization_id=organization_id, source_type="scientific_paper", title=(rec.title or "(untitled record)")[:500],
                     doi=rec.doi, pmid=rec.pmid, publisher=rec.publisher or rec.journal,
                     url=(f"https://doi.org/{rec.doi}" if rec.doi else None), canonical_title=canonical_title(rec.title),
                     metadata_={"journal": rec.journal, "year": rec.year, "license": rec.license,
                                "providers": [rec.provider]},
                     review_status="not_reviewed", full_text_accessed=False)
        db.add(src)
        matched = "new"
    else:
        src.doi = src.doi or rec.doi
        src.pmid = src.pmid or rec.pmid
        src.publisher = src.publisher or rec.publisher or rec.journal
        md = dict(src.metadata_ or {})
        md["providers"] = sorted(set((md.get("providers") or []) + [rec.provider]))
        src.metadata_ = md
    src.acquisition_paths = _acquisition_paths(rec, src.acquisition_paths)
    _classify(src, rec)
    db.flush()
    return src, matched


# ---------------------------------------------------------------- federated run
def run_query(db: Session, *, organization_id: UUID, research_task: ResearchTask, query_text: str, mode: str,
              route: str = "general", keyword_ids: list[UUID] | None = None, question_id: UUID | None = None,
              providers: list | None = None, limit: int = 20) -> dict:
    rq = ResearchQuery(organization_id=organization_id, research_task_id=research_task.id, research_question_id=question_id,
                       mode=mode, route=route, query_text=query_text,
                       keyword_ids=[str(k) for k in (keyword_ids or [])] or None)
    db.add(rq)
    db.flush()
    research_task.status, research_task.started_at = ResearchTaskStatus.RUNNING, _now()
    runs, new_sources, merged = [], 0, 0
    source_ids: list[UUID] = []
    for prov in (providers if providers is not None else default_providers()):
        t0 = time.monotonic()
        run = ResearchProviderRun(organization_id=organization_id, research_query_id=rq.id, provider=prov.name, status="ok", result_count=0)
        db.add(run)
        try:
            records = prov.search(query_text, limit=limit)
        except NotImplementedError as exc:
            run.status, run.error, records = "not_configured", str(exc), []
        except Exception as exc:  # one provider's failure never removes the others' results
            run.status, run.error, records = "failed", f"{type(exc).__name__}: {str(exc)[:300]}", []
        run.duration_ms = int((time.monotonic() - t0) * 1000)
        run.result_count = len(records)
        db.flush()
        for rank, rec in enumerate(records, start=1):
            src, matched = upsert_source(db, organization_id, rec)
            db.add(ResearchHit(organization_id=organization_id, provider_run_id=run.id, source_id=src.id, rank=rank,
                               external_id=rec.external_id, doi=rec.doi, pmid=rec.pmid, title=rec.title,
                               merged_into_existing=matched != "new", matched_on=matched))
            if matched == "new":
                new_sources += 1
            else:
                merged += 1
            if src.id not in source_ids:
                source_ids.append(src.id)
        runs.append({"provider": prov.name, "status": run.status, "error": run.error, "result_count": run.result_count})
    for kid in keyword_ids or []:   # keyword -> task -> first source (summary trace; full chain via /trace)
        if not db.execute(select(KeywordTrace).where(KeywordTrace.organization_id == organization_id, KeywordTrace.keyword_id == kid,
                                                     KeywordTrace.research_task_id == research_task.id)).scalar_one_or_none():
            db.add(KeywordTrace(organization_id=organization_id, keyword_id=kid, research_task_id=research_task.id,
                                source_id=source_ids[0] if source_ids else None,
                                stage="source" if source_ids else "research_task"))
    if question_id is not None:
        n = db.execute(select(func.coalesce(func.max(ResearchIteration.iteration), 0)).where(
            ResearchIteration.organization_id == organization_id, ResearchIteration.research_question_id == question_id)).scalar_one()
        db.add(ResearchIteration(organization_id=organization_id, research_question_id=question_id, iteration=n + 1,
                                 route=route, research_query_id=rq.id, sources_seen=new_sources + merged,
                                 new_sources=new_sources, duplicate_sources=merged,
                                 providers_ok=sum(1 for r in runs if r["status"] == "ok"),
                                 providers_failed=sum(1 for r in runs if r["status"] == "failed")))
    ok = [r for r in runs if r["status"] == "ok"]
    research_task.status = ResearchTaskStatus.COMPLETED if ok else ResearchTaskStatus.FAILED
    research_task.completed_at = _now()
    research_task.result = {"query_id": str(rq.id), "providers": runs, "unique_sources": len(source_ids),
                            "new_sources": new_sources, "merged_duplicates": merged,
                            "note": "Discovery creates sources only; evidence requires human review."}
    db.commit()
    return {"research_query_id": str(rq.id), "research_task_id": str(research_task.id), "query": query_text,
            "providers": runs, "unique_sources": len(source_ids), "new_sources": new_sources,
            "merged_duplicates": merged, "source_ids": [str(s) for s in source_ids]}


def _project_and_task(db: Session, organization_id: UUID, actor: UUID, name: str, objective: str, query: str,
                      project_id=None, mode: str = "user_driven", knowledge_gap_id: UUID | None = None):
    if project_id is None:
        if mode == "gap_driven" and knowledge_gap_id is None:
            raise HTTPException(422, "A gap-driven project must name the knowledge gap it came from.")
        project = research_project_service.create_research_project(
            db, organization_id=organization_id, name=name[:300], objective=objective[:2000], mode=_mode(mode),
            knowledge_gap_id=knowledge_gap_id, actor_user_id=actor)
        project_id = project.id
    task = research_task_service.create_research_task(db, organization_id=organization_id, research_project_id=project_id,
                                                      task_type="federated_search", query=query[:2000], actor_user_id=actor)
    return project_id, task


def keyword_search(db: Session, *, organization_id: UUID, actor: UUID, knowledge_object_id: UUID, keyword_ids: list[UUID],
                   mode: str, boolean_query: str | None, providers: list | None = None) -> dict:
    ko = db.execute(select(KnowledgeObject).where(KnowledgeObject.id == knowledge_object_id,
                                                  KnowledgeObject.organization_id == organization_id)).scalar_one_or_none()
    if ko is None:
        raise HTTPException(404, "Knowledge object not found.")
    kws = db.execute(select(KnowledgeKeyword).where(KnowledgeKeyword.organization_id == organization_id,
                                                    KnowledgeKeyword.knowledge_object_id == ko.id,
                                                    KnowledgeKeyword.id.in_(keyword_ids or []))).scalars().all()
    if mode != "boolean" and len(kws) != len(set(keyword_ids or [])):
        raise HTTPException(404, "Keyword not found for this knowledge object.")
    terms = [k.keyword for k in kws]
    outcomes = [k.keyword for k in kws if k.kind in ("clinical_outcome", "mechanism", "safety_term")]
    subject = [k.keyword for k in kws if k.kind not in ("clinical_outcome", "mechanism", "safety_term")] or terms
    query = build_query(mode, subject if mode == "agent" else terms, boolean_query, outcomes if mode == "agent" else None)
    _, task = _project_and_task(db, organization_id, actor, f"Keyword research: {ko.canonical_name}",
                                f"Find sources for {ko.canonical_name}", query)
    return run_query(db, organization_id=organization_id, research_task=task, query_text=query, mode=mode,
                     keyword_ids=[k.id for k in kws], providers=providers)


def route_queries(subject_q: str, compounds: list[str] | None, outcome: str | None, population: str | None,
                  related_species: list[str] | None = None) -> dict:
    """One query per evidence route. Each route asks a different question, and the answers are never merged:
    a study of a compound, a relative species or a formulation is evidence about *that*, not about the subject."""
    compounds = [c.strip() for c in (compounds or []) if c and c.strip()]
    species = [s.strip() for s in (related_species or []) if s and s.strip()]
    o = _quote(outcome) if outcome else None
    pop = _quote(population) if population else None
    tail = " AND ".join(x for x in (o, pop) if x)
    q = {"direct_subject": subject_q + (f" AND {tail}" if tail else "")}
    if compounds:
        any_compound = "(" + " OR ".join(_quote(c) for c in compounds) + ")"
        q["compound_human"] = any_compound + (f" AND {tail}" if tail else "")
        q["mechanistic"] = any_compound + (f" AND {o}" if o else "") + ' AND (mechanism OR "in vitro" OR animal)'
        q["co_occurrence"] = f"{subject_q} AND {any_compound}"
        if len(compounds) > 1:
            # the compounds studied together, not each on its own
            q["combination"] = " AND ".join(_quote(c) for c in compounds) + (f" AND {tail}" if tail else "")
        q["indirect_formulation"] = f"{subject_q} AND (syrup OR extract OR decoction OR formulation OR preparation)" + (f" AND {o}" if o else "")
    if species:
        any_species = "(" + " OR ".join(_quote(s) for s in species) + ")"
        q["indirect_analogous_species"] = any_species + (f" AND {tail}" if tail else "")
        q["indirect_taxonomic"] = any_species + " AND (genus OR species OR taxonomy OR chemotaxonomy)" + (f" AND {o}" if o else "")
    return q


def _mode(value: str) -> "ResearchMode":
    """The project's mode says WHY this investigation exists (§11). EXPLORATORY means: no specific gap, we are
    looking around; it is recorded as such rather than being disguised as a targeted search."""
    try:
        return ResearchMode(value)
    except ValueError:
        raise HTTPException(422, f"mode must be one of: {', '.join(m.value for m in ResearchMode)}") from None


def create_question(db: Session, *, organization_id: UUID, actor: UUID, knowledge_object_id: UUID | None, subject: str,
                    compound: str | None = None, outcome: str | None = None, population: str | None = None,
                    question_text: str | None = None, compounds: list[str] | None = None,
                    related_species: list[str] | None = None, mode: str = "user_driven",
                    knowledge_gap_id: UUID | None = None, providers: list | None = None) -> dict:
    ko = None
    if knowledge_object_id:
        ko = db.execute(select(KnowledgeObject).where(KnowledgeObject.id == knowledge_object_id,
                                                      KnowledgeObject.organization_id == organization_id)).scalar_one_or_none()
        if ko is None:
            raise HTTPException(404, "Knowledge object not found.")
    text = question_text or (f"Does {subject} " + (f"have a {outcome} effect" if outcome else "have documented effects")
                             + (f" in {population}s" if population else "") + "?")
    # compounds: what the caller passed, otherwise the knowledge object's own compound keywords
    all_compounds = [c for c in (compounds or ([compound] if compound else [])) if c]
    if not all_compounds and ko is not None:
        all_compounds = list(db.execute(select(KnowledgeKeyword.keyword).where(
            KnowledgeKeyword.organization_id == organization_id, KnowledgeKeyword.knowledge_object_id == ko.id,
            KnowledgeKeyword.kind == "compound")).scalars().all())[:6]
    species = list(related_species or [])
    if not species and ko is not None:
        species = list(db.execute(select(KnowledgeKeyword.keyword).where(
            KnowledgeKeyword.organization_id == organization_id, KnowledgeKeyword.knowledge_object_id == ko.id,
            KnowledgeKeyword.kind == "related_entity")).scalars().all())[:6]
    terms = subject_terms(db, organization_id, ko, subject)
    subject_q = "(" + " OR ".join(_quote(t) for t in terms) + ")" if len(terms) > 1 else _quote(terms[0])
    queries = route_queries(subject_q, all_compounds, outcome, population, species)
    project_id, _ = None, None
    q = ResearchQuestion(organization_id=organization_id, knowledge_object_id=ko.id if ko else None, question_text=text,
                         subject=subject, compound=all_compounds[0] if all_compounds else None,
                         compounds=all_compounds or None, related_species=species or None,
                         outcome=outcome, population=population)
    db.add(q)
    db.flush()
    results = {}
    for route, query in queries.items():
        project_id, task = _project_and_task(db, organization_id, actor, f"Research question: {text}", text, query,
                                             project_id, mode=mode, knowledge_gap_id=knowledge_gap_id)
        q.research_project_id = project_id
        results[route] = run_query(db, organization_id=organization_id, research_task=task, query_text=query, mode="agent",
                                   route=route, question_id=q.id, providers=providers)
    return {"research_question_id": str(q.id), "research_project_id": str(project_id), "mode": _mode(mode).value,
            "question": text, "routes": results}


def find_more(db: Session, *, organization_id: UUID, actor: UUID, question_id: UUID, route: str, extra_terms: list[str] | None,
              providers: list | None = None) -> dict:
    q = _question(db, organization_id, question_id)
    if route not in ROUTES:
        raise HTTPException(422, "Unknown route for this question.")
    ko = db.get(KnowledgeObject, q.knowledge_object_id) if q.knowledge_object_id else None
    terms = subject_terms(db, organization_id, ko, q.subject) + [t for t in (extra_terms or []) if t.strip()]
    subject_q = "(" + " OR ".join(_quote(t) for t in terms) + ")"
    built = route_queries(subject_q, q.compounds or ([q.compound] if q.compound else []), q.outcome, None, q.related_species)
    if route not in built:
        raise HTTPException(422, f"This question has nothing to search on the {route.replace('_', ' ')} route.")
    query = built[route]                                                     # broadened: population dropped
    _, task = _project_and_task(db, organization_id, actor, "", "", query, q.research_project_id)
    return run_query(db, organization_id=organization_id, research_task=task, query_text=query, mode="agent", route=route,
                     question_id=q.id, providers=providers)


def _question(db: Session, organization_id: UUID, question_id: UUID) -> ResearchQuestion:
    q = db.execute(select(ResearchQuestion).where(ResearchQuestion.id == question_id,
                                                  ResearchQuestion.organization_id == organization_id)).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "Research question not found.")
    return q


def _question_sources(db: Session, organization_id: UUID, question_id: UUID) -> dict[str, list[Source]]:
    rows = db.execute(select(ResearchQuery.route, Source).join(ResearchProviderRun, ResearchProviderRun.research_query_id == ResearchQuery.id)
                      .join(ResearchHit, ResearchHit.provider_run_id == ResearchProviderRun.id)
                      .join(Source, Source.id == ResearchHit.source_id)
                      .where(ResearchQuery.organization_id == organization_id, ResearchQuery.research_question_id == question_id)).all()
    out: dict[str, dict] = {r: {} for r in ROUTES}
    for route, src in rows:
        out.setdefault(route, {})[src.id] = src
    return {r: list(v.values()) for r, v in out.items()}


# ---------------------------------------------------------------- evidence candidates + human review
def _route_about(q: ResearchQuestion, route: str) -> str | None:
    """What a candidate on this route is about — never the subject unless the route is the subject route."""
    compounds = q.compounds or ([q.compound] if q.compound else [])
    species = q.related_species or []
    if route == "direct_subject":
        return q.subject
    if route in ("compound_human", "mechanistic"):
        return " / ".join(compounds) if compounds else None
    if route == "combination":
        return " + ".join(compounds) if compounds else None
    if route in ("indirect_analogous_species", "indirect_taxonomic"):
        return " / ".join(species) if species else None
    if route == "indirect_formulation":
        return f"a preparation containing {q.subject}"
    if route == "co_occurrence":
        return f"{q.subject} and " + (" / ".join(compounds) if compounds else "a compound")
    return None


def extract_candidates(db: Session, *, organization_id: UUID, question_id: UUID) -> dict:
    """Agent step: one PENDING evidence candidate per source whose abstract the system actually holds.
    Sources with metadata only get no candidate (nothing was read). Never verifies, never creates claims."""
    q = _question(db, organization_id, question_id)
    created, skipped_no_text = 0, 0
    for route, sources in _question_sources(db, organization_id, q.id).items():
        for src in sources:
            if not src.abstract:
                skipped_no_text += 1
                continue
            exists = db.execute(select(Evidence).where(Evidence.organization_id == organization_id, Evidence.source_id == src.id,
                                                       Evidence.evidence_route == route)).scalars().first()
            if exists:
                continue
            db.add(Evidence(organization_id=organization_id, source_id=src.id, study_type=None,
                            directness=EvidenceDirectness.INDIRECT, evidence_strength=EvidenceStrength.VERY_LOW,
                            status=EvidenceStatus.PENDING_REVIEW, source_generated=True, human_reviewed=False,
                            evidence_route=route, basis="abstract", subject_tested=None,
                            evidence_about=_route_about(q, route),
                            summary=(f"[{route}] Candidate from the abstract only — full text not reviewed by the system. "
                                     f"Question: {q.question_text} Abstract excerpt: {src.abstract[:700]}")))
            created += 1
    db.commit()
    return {"created_candidates": created, "sources_without_accessible_text": skipped_no_text,
            "status": "pending_review", "note": "Candidates require human review before they can support any claim."}


def review_candidate(db: Session, *, organization_id: UUID, evidence_id: UUID, decision: str, subject_tested: str | None,
                     evidence_strength: str | None, note: str | None) -> Evidence:
    ev = db.execute(select(Evidence).where(Evidence.id == evidence_id, Evidence.organization_id == organization_id)).scalar_one_or_none()
    if ev is None:
        raise HTTPException(404, "Evidence not found.")
    if ev.status != EvidenceStatus.PENDING_REVIEW:
        raise HTTPException(409, "Only pending candidates can be reviewed here.")
    if decision == "reject":
        ev.status = EvidenceStatus.REJECTED
    elif decision == "approve":
        if not subject_tested or not subject_tested.strip():
            raise HTTPException(422, "State what the study actually tested (subject_tested).")
        ev.subject_tested = subject_tested.strip()[:300]
        q_subjects = set()
        hit = db.execute(select(ResearchQuestion).join(ResearchQuery, ResearchQuery.research_question_id == ResearchQuestion.id)
                         .join(ResearchProviderRun, ResearchProviderRun.research_query_id == ResearchQuery.id)
                         .join(ResearchHit, ResearchHit.provider_run_id == ResearchProviderRun.id)
                         .where(ResearchHit.source_id == ev.source_id, ResearchQuestion.organization_id == organization_id)).scalars().first()
        if hit:
            q_subjects = {hit.subject.lower()}
            if hit.knowledge_object_id:
                ko = db.get(KnowledgeObject, hit.knowledge_object_id)
                if ko:
                    q_subjects.add(ko.canonical_name.lower())
        tested_subject = ev.subject_tested.lower() in q_subjects or any(s in ev.subject_tested.lower() for s in q_subjects)
        # Direct only when the reviewer states the study tested the subject itself AND the route is the subject route.
        if ev.evidence_route == "direct_subject" and tested_subject:
            ev.directness = EvidenceDirectness.DIRECT
        else:
            ev.directness = EvidenceDirectness.INDIRECT
            if ev.evidence_route == "direct_subject" and not tested_subject:
                ev.evidence_route = "co_occurrence"    # found by the subject query but did not test the subject
        if evidence_strength:
            ev.evidence_strength = EvidenceStrength(evidence_strength)
        ev.status = EvidenceStatus.VERIFIED
        ev.human_reviewed = True
    else:
        raise HTTPException(422, "decision must be approve or reject")
    src = db.get(Source, ev.source_id)
    if src is not None:
        src.review_status = "reviewed" if not db.execute(select(func.count()).select_from(Evidence).where(
            Evidence.source_id == src.id, Evidence.status == EvidenceStatus.PENDING_REVIEW, Evidence.id != ev.id)).scalar_one() else "in_review"
    db.commit()
    db.refresh(ev)
    return ev


# ---------------------------------------------------------------- evidence map
def evidence_map(db: Session, *, organization_id: UUID, question_id: UUID) -> dict:
    q = _question(db, organization_id, question_id)
    by_route = _question_sources(db, organization_id, q.id)
    all_ids = {s.id for v in by_route.values() for s in v}
    evid = db.execute(select(Evidence).where(Evidence.organization_id == organization_id, Evidence.source_id.in_(all_ids))).scalars().all() if all_ids else []
    verified = [e for e in evid if e.status == EvidenceStatus.VERIFIED]
    pending = [e for e in evid if e.status == EvidenceStatus.PENDING_REVIEW]
    conflicting = []
    if verified:
        links = db.execute(select(ClaimEvidence).where(ClaimEvidence.evidence_id.in_([e.id for e in verified]))).scalars().all()
        rel_by_claim: dict = {}
        for l in links:
            rel_by_claim.setdefault(l.claim_id, set()).add(str(getattr(l.relation, "value", l.relation)))
        conflicting = [str(cid) for cid, rels in rel_by_claim.items() if "supports" in rels and "contradicts" in rels]

    def ev_out(e: Evidence) -> dict:
        return {"id": str(e.id), "source_id": str(e.source_id), "route": e.evidence_route, "directness": e.directness.value,
                "subject_tested": e.subject_tested, "basis": e.basis, "status": e.status.value}

    direct = [e for e in verified if e.directness == EvidenceDirectness.DIRECT]
    indirect = [e for e in verified if e.directness == EvidenceDirectness.INDIRECT]
    reviewed_sources = {e.source_id for e in verified}
    inaccessible = [{"source_id": str(s.id), "title": s.title, "content_access": s.content_access, "acquisition_paths": s.acquisition_paths,
                     "message": NOT_REVIEWED_MESSAGE}
                    for s in {s.id: s for v in by_route.values() for s in v}.values()
                    if s.id not in reviewed_sources and not s.full_text_accessed]
    missing = [r for r in ROUTES if (r == "direct_subject" or q.compound) and not by_route.get(r)]
    suggestions = []
    for r in (missing or [r for r in ROUTES if (r == "direct_subject" or q.compound) and not any(e.evidence_route == r for e in verified)]):
        query = db.execute(select(ResearchQuery.query_text).where(ResearchQuery.research_question_id == q.id, ResearchQuery.route == r)
                           .order_by(ResearchQuery.created_at.desc())).scalars().first() or q.subject
        suggestions.append({"route": r, "query": query,
                            "pubmed": f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}",
                            "europepmc": f"https://europepmc.org/search?query={quote_plus(query)}",
                            "library": f"https://search.worldcat.org/search?q={quote_plus(query)}"})
    has = lambda route: any(e.evidence_route == route for e in verified)  # noqa: E731
    per_route = {r: {"verified": sum(1 for e in verified if e.evidence_route == r),
                     "awaiting_review": sum(1 for e in pending if e.evidence_route == r),
                     "sources": len(by_route.get(r, []))} for r in ROUTES}
    clinical = "direct" if any(e.evidence_route == "direct_subject" and e.directness == EvidenceDirectness.DIRECT for e in verified) \
        else ("indirect" if has("compound_human") else "insufficient")
    return {
        "research_question_id": str(q.id), "question": q.question_text, "subject": q.subject, "compound": q.compound,
        "knowledge_object_id": str(q.knowledge_object_id) if q.knowledge_object_id else None,
        "outcome": q.outcome, "population": q.population,
        "status_summary": {
            f"direct_evidence_for_{q.subject}": "present" if direct else "absent",
            f"evidence_for_{q.compound}": ("present" if has("compound_human") else "absent") if q.compound else "not_asked",
            "mechanistic_plausibility": ("present" if has("mechanistic") else "absent") if q.compound else "not_asked",
            f"clinical_evidence_for_{q.subject}": clinical,
        },
        "directly_supported": [ev_out(e) for e in direct],
        "indirectly_supported": [ev_out(e) for e in indirect],
        "conflicting_claim_ids": conflicting,
        "awaiting_review": [ev_out(e) for e in pending],
        "inaccessible": inaccessible,
        "missing_routes": missing,
        "suggested_manual_searches": suggestions,
        "sources_by_route": {r: len(v) for r, v in by_route.items()},
        "routes": per_route,
        "independent_evidence_count": dependency_graph(db, organization_id=organization_id, question_id=q.id)["independent_evidence_count"],
        "compounds": q.compounds or ([q.compound] if q.compound else []),
        "related_species": q.related_species or [],
        "note": INDIRECT_NOTE,
        "inference_policy": "No conclusion about the subject is generated from compound evidence.",
    }


# ---------------------------------------------------------------- source detail + trace
def source_detail(db: Session, *, organization_id: UUID, source_id: UUID) -> dict:
    s = db.execute(select(Source).where(Source.id == source_id, Source.organization_id == organization_id)).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "Source not found.")
    hist = db.execute(select(ResearchHit, ResearchProviderRun, ResearchQuery)
                      .join(ResearchProviderRun, ResearchProviderRun.id == ResearchHit.provider_run_id)
                      .join(ResearchQuery, ResearchQuery.id == ResearchProviderRun.research_query_id)
                      .where(ResearchHit.source_id == s.id, ResearchHit.organization_id == organization_id)
                      .order_by(ResearchHit.created_at)).all()
    evid = db.execute(select(Evidence).where(Evidence.source_id == s.id, Evidence.organization_id == organization_id)).scalars().all()
    full = ("available and read by the system (" + {"user_upload": "uploaded by a person", "open_access_fetch": "fetched from an open-access copy"}.get(s.full_text_origin, s.full_text_origin or "") + ")") if s.full_text_accessed else "not reviewed by the system"
    return {
        "id": str(s.id), "title": s.title, "doi": s.doi, "pmid": s.pmid, "publisher": s.publisher,
        "existence": s.existence_status, "content_access": s.content_access, "full_text_accessed": s.full_text_accessed,
        "what_was_accessed": s.accessed_parts or [], "full_text_status": full,
        "abstract_status": "held by the system" if s.abstract else "not available to the system",
        "abstract": s.abstract, "rights": getattr(s.rights_status, "value", s.rights_status),
        "review_status": s.review_status, "full_text_origin": s.full_text_origin,
        "full_text_document_id": str(s.full_text_document_id) if s.full_text_document_id else None,
        "access_blocked_reason": s.access_blocked_reason, "access_checked_at": s.access_checked_at,
        "access_history": (s.metadata_ or {}).get("access_history", []),
        "open_access_links": (s.acquisition_paths or {}).get("open_access", []),
        "access_locators": {k: v for k, v in (s.acquisition_paths or {}).items() if k != "open_access"},
        "message": None if s.full_text_accessed else NOT_REVIEWED_MESSAGE,
        "research_history": [{"provider": run.provider, "query": rq.query_text, "route": rq.route, "research_task_id": str(rq.research_task_id),
                              "rank": h.rank, "matched_on": h.matched_on, "found_at": h.created_at} for h, run, rq in hist],
        "extracted_evidence": [{"id": str(e.id), "route": e.evidence_route, "directness": e.directness.value, "subject_tested": e.subject_tested,
                                "basis": e.basis} for e in evid if e.status == EvidenceStatus.VERIFIED],
        "unreviewed_evidence": [{"id": str(e.id), "route": e.evidence_route, "basis": e.basis, "summary": e.summary[:300]}
                                for e in evid if e.status == EvidenceStatus.PENDING_REVIEW],
    }


def keyword_chain(db: Session, *, organization_id: UUID, keyword_id: UUID) -> dict:
    kw = db.execute(select(KnowledgeKeyword).where(KnowledgeKeyword.id == keyword_id,
                                                   KnowledgeKeyword.organization_id == organization_id)).scalar_one_or_none()
    if kw is None:
        raise HTTPException(404, "Keyword not found.")
    queries = db.execute(select(ResearchQuery).where(ResearchQuery.organization_id == organization_id)).scalars().all()
    queries = [q for q in queries if str(kw.id) in (q.keyword_ids or [])]
    chain = []
    for rq in queries:
        task = db.get(ResearchTask, rq.research_task_id)
        runs = db.execute(select(ResearchProviderRun).where(ResearchProviderRun.research_query_id == rq.id)).scalars().all()
        for run in runs:
            hits = db.execute(select(ResearchHit).where(ResearchHit.provider_run_id == run.id)).scalars().all()
            for h in hits:
                evs = db.execute(select(Evidence).where(Evidence.source_id == h.source_id, Evidence.organization_id == organization_id)).scalars().all()
                links = db.execute(select(ClaimEvidence).where(ClaimEvidence.evidence_id.in_([e.id for e in evs]))).scalars().all() if evs else []
                claims = db.execute(select(Claim).where(Claim.id.in_([l.claim_id for l in links]))).scalars().all() if links else []
                chain.append({"research_project_id": str(task.research_project_id), "research_task_id": str(task.id),
                              "query": rq.query_text, "provider": run.provider, "source_id": str(h.source_id),
                              "evidence": [{"id": str(e.id), "status": e.status.value, "directness": e.directness.value} for e in evs],
                              "claims": [{"id": str(c.id), "knowledge_object_id": str(c.knowledge_object_id)} for c in claims]})
        for run in runs:
            if run.status != "ok":
                chain.append({"research_task_id": str(task.id), "query": rq.query_text, "provider": run.provider,
                              "provider_status": run.status, "error": run.error})
    return {"keyword_id": str(kw.id), "keyword": kw.keyword, "kind": kw.kind, "knowledge_object_id": str(kw.knowledge_object_id),
            "chain": chain, "complete_to_claim": any(c.get("claims") for c in chain)}


def find_more_for_gap(db: Session, *, organization_id: UUID, actor: UUID, gap_id: UUID, providers: list | None = None) -> dict:
    """'Find more' on a knowledge gap: a research question for the gap's knowledge object, searched with the
    object's synonyms and the gap description as the outcome. Sources only; nothing is resolved automatically."""
    from app.models.knowledge_gap import KnowledgeGap
    gap = db.execute(select(KnowledgeGap).where(KnowledgeGap.id == gap_id, KnowledgeGap.organization_id == organization_id)).scalar_one_or_none()
    if gap is None:
        raise HTTPException(404, "Knowledge gap not found.")
    ko = db.get(KnowledgeObject, gap.knowledge_object_id) if gap.knowledge_object_id else None
    subject = ko.canonical_name if ko else (gap.description or "")[:200]
    outcome = (gap.description or "")[:200] if ko else None
    return create_question(db, organization_id=organization_id, actor=actor, knowledge_object_id=ko.id if ko else None,
                           subject=subject, compound=None, outcome=outcome, population=None,
                           question_text=f"Knowledge gap: {gap.description}"[:2000], mode="gap_driven",
                           knowledge_gap_id=gap.id, providers=providers)


FULL_TEXT_MIN_BYTES = 4000     # converted text smaller than this is a landing / abstract page, not a full text


def acquire_full_text(db: Session, *, organization_id: UUID, source_id: UUID, url: str) -> dict:
    """Fetch an open-access copy and claim full text ONLY if a real document was converted.

    * the URL must be one of the source's recorded open-access locations (no arbitrary URLs);
    * the fetch goes through the SSRF-guarded fetcher (private / metadata / non-http targets refused);
    * full_text_accessed is set only when conversion succeeded with at least FULL_TEXT_MIN_BYTES of text.
    Anything less leaves the source exactly as it was and says why."""
    from app.ingestion.url_source import UrlRejected
    from app.models.document_artifact import DocumentConversion
    from app.services import url_ingestion_service

    src = db.execute(select(Source).where(Source.id == source_id, Source.organization_id == organization_id)).scalar_one_or_none()
    if src is None:
        raise HTTPException(404, "Source not found.")
    allowed = set((src.acquisition_paths or {}).get("open_access") or [])
    if url not in allowed:
        raise HTTPException(422, "Only a recorded open-access location of this source can be fetched.")
    try:
        res = url_ingestion_service.fetch_and_ingest_url(db, organization_id=organization_id, source_id=src.id, url=url,
                                                         title=src.title[:200])
    except UrlRejected as exc:
        db.rollback()
        return {"acquired": False, "reason": f"blocked: {exc}", "content_access": src.content_access}
    except Exception as exc:  # network / conversion failure: nothing is claimed
        db.rollback()
        detail = getattr(exc, "detail", None) or str(exc)
        return {"acquired": False, "reason": f"{type(exc).__name__}: {str(detail)[:200]}", "content_access": src.content_access}
    conv = db.get(DocumentConversion, UUID(res["conversion_id"]))
    size = (conv.output_size_bytes or 0) if conv else 0
    ok = conv is not None and str(getattr(conv.conversion_status, "value", conv.conversion_status)) == "succeeded" and size >= FULL_TEXT_MIN_BYTES
    src = db.get(Source, source_id)
    src.access_checked_at = _now()
    if ok:
        src.full_text_accessed = True
        src.content_access = "full_text_available"
        src.full_text_origin = "open_access_fetch"
        src.full_text_document_id = UUID(res["document_id"])
        src.accessed_parts = sorted(set((src.accessed_parts or []) + ["full_text"]))
        md = dict(src.metadata_ or {})
        md["full_text_url"] = url
        src.metadata_ = md
        db.commit()
        return {"acquired": True, "document_id": res["document_id"], "converted_bytes": size, "content_access": src.content_access}
    src.content_access = "landing_page_only" if src.content_access in ("metadata_only", "unknown") else src.content_access
    src.access_blocked_reason = "The open-access link returned a landing or abstract page, not the article."
    db.commit()
    return {"acquired": False, "document_id": res["document_id"], "converted_bytes": size, "content_access": src.content_access,
            "reason": "retrieved, but the page is too short to be the full text (landing or abstract page)"}


def attach_full_text(db: Session, *, organization_id: UUID, source_id: UUID, document_id: UUID, actor_user_id: UUID) -> dict:
    """The user legally obtained the article and uploaded it. Attach that document to the source.

    The claim is only made when the uploaded file really parsed into a document of at least
    FULL_TEXT_MIN_BYTES; otherwise the source is left exactly as it was and the reason is returned.
    Earlier provenance (what the system had before, and how) is preserved in `metadata_`."""
    from app.models.document import Document
    from app.models.document_artifact import DocumentConversion
    from app.services.audit import record_audit_log

    src = db.execute(select(Source).where(Source.id == source_id, Source.organization_id == organization_id)).scalar_one_or_none()
    if src is None:
        raise HTTPException(404, "Source not found.")
    doc = db.execute(select(Document).where(Document.id == document_id,
                                            Document.organization_id == organization_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "Document not found.")
    if doc.source_id != src.id:
        raise HTTPException(422, "That document belongs to a different source.")
    conv = db.execute(select(DocumentConversion).where(DocumentConversion.document_id == doc.id)
                      .order_by(DocumentConversion.created_at.desc())).scalars().first()
    status_value = str(getattr(getattr(conv, "conversion_status", None), "value", getattr(conv, "conversion_status", ""))) if conv else ""
    size = (conv.output_size_bytes or 0) if conv else 0
    src.access_checked_at = _now()
    if status_value != "succeeded":
        db.commit()
        return {"attached": False, "reason": f"the upload has not been parsed yet (conversion {status_value or 'missing'})",
                "content_access": src.content_access}
    if size < FULL_TEXT_MIN_BYTES:
        db.commit()
        return {"attached": False, "reason": "the uploaded file parsed into too little text to be the full article",
                "converted_bytes": size, "content_access": src.content_access}
    md = dict(src.metadata_ or {})
    md.setdefault("access_history", []).append({"at": _now().isoformat(), "was": src.content_access,
                                                "origin": src.full_text_origin, "event": "user_upload"})
    src.metadata_ = md
    src.full_text_accessed = True
    src.content_access = "full_text_available"
    src.full_text_origin = "user_upload"
    src.full_text_document_id = doc.id
    src.access_blocked_reason = None
    src.accessed_parts = sorted(set((src.accessed_parts or []) + ["full_text"]))
    src.review_status = "in_review"
    record_audit_log(db, organization_id=organization_id, user_id=actor_user_id, action="source.full_text_attached",
                     resource_type="source", resource_id=src.id,
                     new_value={"document_id": str(doc.id), "converted_bytes": size, "origin": "user_upload"})
    db.commit()
    db.refresh(src)
    return {"attached": True, "document_id": str(doc.id), "converted_bytes": size, "content_access": src.content_access,
            "full_text_origin": src.full_text_origin,
            "next": "Evidence candidates can now be extracted from the full text; they still require human review."}


def set_access_state(db: Session, *, organization_id: UUID, source_id: UUID, state: str, reason: str | None) -> dict:
    """Record what a person found when trying to obtain a source (paywalled, registration required, blocked,
    title only...). Never sets full_text_available — only a parsed document can do that."""
    allowed = ("abstract_only", "metadata_only", "title_only", "landing_page_only", "paywalled",
               "registration_required", "access_blocked", "unavailable", "unknown")
    if state not in allowed:
        raise HTTPException(422, f"state must be one of: {', '.join(allowed)}")
    src = db.execute(select(Source).where(Source.id == source_id, Source.organization_id == organization_id)).scalar_one_or_none()
    if src is None:
        raise HTTPException(404, "Source not found.")
    if src.full_text_accessed:
        raise HTTPException(409, "This source already has full text; a weaker state cannot be recorded.")
    src.content_access = state
    src.access_blocked_reason = (reason or None)
    src.access_checked_at = _now()
    db.commit()
    return {"source_id": str(src.id), "content_access": src.content_access, "reason": src.access_blocked_reason,
            "checked_at": src.access_checked_at}


def evidence_graph(db: Session, *, organization_id: UUID, question_id: UUID) -> dict:
    """The labelled graph behind the answer (§18).

        subject --contains--> compound --studied_in--> study --reports--> outcome

    Every edge says what it rests on. A `contains` edge exists only where a source actually documents the
    compound in the subject; it is never assumed from a keyword. No path through a compound is ever
    relabelled as evidence for the subject: the `directness` of each study edge is carried through.
    """
    q = _question(db, organization_id, question_id)
    compounds = q.compounds or ([q.compound] if q.compound else [])
    species = q.related_species or []
    by_route = _question_sources(db, organization_id, q.id)
    all_ids = {s.id for v in by_route.values() for s in v}
    evid = db.execute(select(Evidence).where(Evidence.organization_id == organization_id,
                                             Evidence.source_id.in_(all_ids))).scalars().all() if all_ids else []
    verified = [e for e in evid if e.status == EvidenceStatus.VERIFIED]
    src_by_id = {s.id: s for v in by_route.values() for s in v}

    nodes = [{"id": f"subject:{q.subject}", "type": "subject", "label": q.subject}]
    nodes += [{"id": f"compound:{c}", "type": "compound", "label": c} for c in compounds]
    nodes += [{"id": f"species:{s}", "type": "species", "label": s} for s in species]
    if q.outcome:
        nodes.append({"id": f"outcome:{q.outcome}", "type": "outcome", "label": q.outcome})
    edges = []

    # subject --contains--> compound, only where a source documents it
    composition = [e for e in verified if e.evidence_route in ("co_occurrence", "direct_subject") and e.evidence_about]
    for c in compounds:
        support = [e for e in composition if c.lower() in (e.evidence_about or "").lower()]
        edges.append({"from": f"subject:{q.subject}", "to": f"compound:{c}", "label": "contains",
                      "documented": bool(support), "evidence_ids": [str(e.id) for e in support],
                      "note": None if support else "not documented by a reviewed source yet — the link is assumed, not shown as evidence"})

    def study_node(e):  # noqa: ANN001, ANN202
        s = src_by_id.get(e.source_id)
        nid = f"study:{e.source_id}"
        if not any(n["id"] == nid for n in nodes):
            nodes.append({"id": nid, "type": "study", "label": (s.title if s else str(e.source_id))[:160],
                          "content_access": s.content_access if s else None,
                          "full_text_read": bool(s and s.full_text_accessed)})
        return nid

    for e in verified:
        nid = study_node(e)
        about = e.evidence_about or e.subject_tested or ""
        if e.evidence_route == "direct_subject":
            frm = f"subject:{q.subject}"
        elif e.evidence_route in ("compound_human", "mechanistic", "combination"):
            match = next((c for c in compounds if c.lower() in about.lower()), None)
            frm = f"compound:{match}" if match else (f"compound:{compounds[0]}" if compounds else f"subject:{q.subject}")
        elif e.evidence_route in ("indirect_analogous_species", "indirect_taxonomic"):
            match = next((s for s in species if s.lower() in about.lower()), None)
            frm = f"species:{match}" if match else (f"species:{species[0]}" if species else f"subject:{q.subject}")
        else:
            frm = f"subject:{q.subject}"
        edges.append({"from": frm, "to": nid, "label": "studied_in", "route": e.evidence_route,
                      "directness": e.directness.value, "about": e.evidence_about, "tested": e.subject_tested,
                      "basis": e.basis, "evidence_id": str(e.id)})
        if q.outcome:
            edges.append({"from": nid, "to": f"outcome:{q.outcome}", "label": "reports_outcome",
                          "directness": e.directness.value, "evidence_id": str(e.id)})

    direct_paths = [e for e in edges if e["label"] == "studied_in" and e.get("from") == f"subject:{q.subject}"
                    and e.get("directness") == "direct"]
    return {
        "research_question_id": str(q.id), "subject": q.subject, "compounds": compounds, "related_species": species,
        "outcome": q.outcome, "nodes": nodes, "edges": edges,
        "direct_paths_to_subject": len(direct_paths),
        "reading": ("A path that runs through a compound, a related species or a formulation supports that node, "
                    "not the subject. Only a study that tested the subject itself is direct evidence for it."),
    }


# ---------------------------------------------------------------- source dependency (§20)
def add_dependency(db: Session, *, organization_id: UUID, source_id: UUID, depends_on_source_id: UUID,
                   relation: str, note: str | None, detected_by: str = "user") -> dict:
    """Record that one source rests on another (a review on its trials, a reanalysis on its data,
    two records of the same study)."""
    from app.models.research_dependency import DEPENDENCY_RELATIONS

    if relation not in DEPENDENCY_RELATIONS:
        raise HTTPException(422, f"relation must be one of: {', '.join(DEPENDENCY_RELATIONS)}")
    if source_id == depends_on_source_id:
        raise HTTPException(422, "A source cannot depend on itself.")
    for sid in (source_id, depends_on_source_id):
        if db.execute(select(Source).where(Source.id == sid, Source.organization_id == organization_id)).scalar_one_or_none() is None:
            raise HTTPException(404, "Source not found.")
    existing = db.execute(select(SourceDependency).where(
        SourceDependency.organization_id == organization_id, SourceDependency.source_id == source_id,
        SourceDependency.depends_on_source_id == depends_on_source_id, SourceDependency.relation == relation)).scalar_one_or_none()
    if existing:
        return {"id": str(existing.id), "created": False}
    row = SourceDependency(organization_id=organization_id, source_id=source_id, depends_on_source_id=depends_on_source_id,
                           relation=relation, note=note, detected_by=detected_by)
    db.add(row)
    db.commit()
    return {"id": str(row.id), "created": True, "relation": relation}


def dependency_graph(db: Session, *, organization_id: UUID, question_id: UUID) -> dict:
    """How many *independent* findings a question really rests on.

    A source that reviews, reanalyses, is a preprint of, or records the same study as another is not an
    independent finding: it is grouped with what it depends on. A source that merely *cites* another stays
    independent. Groups are transitive, so twenty reviews of three trials count as three."""
    q = _question(db, organization_id, question_id)
    by_route = _question_sources(db, organization_id, q.id)
    sources = {s.id: s for v in by_route.values() for s in v}
    if not sources:
        return {"research_question_id": str(q.id), "sources": 0, "independent_evidence_count": 0, "groups": [],
                "note": "No sources yet."}
    deps = db.execute(select(SourceDependency).where(SourceDependency.organization_id == organization_id,
                                                     SourceDependency.source_id.in_(sources),
                                                     SourceDependency.depends_on_source_id.in_(sources))).scalars().all()
    parent: dict = {sid: sid for sid in sources}

    def find(x):  # noqa: ANN001, ANN202
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    grouping = [d for d in deps if d.relation in NON_INDEPENDENT]
    for d in grouping:                       # the dependent source joins the group of what it rests on
        a, b = find(d.source_id), find(d.depends_on_source_id)
        if a != b:
            parent[a] = b
    groups: dict = {}
    for sid in sources:
        groups.setdefault(find(sid), []).append(sid)
    out = []
    for root, members in groups.items():
        base = sources[root]
        out.append({"independent_finding": base.title, "root_source_id": str(root), "size": len(members),
                    "members": [{"source_id": str(m), "title": sources[m].title,
                                 "role": "primary" if m == root else next(
                                     (d.relation for d in grouping if d.source_id == m), "grouped")} for m in members]})
    out.sort(key=lambda g: -g["size"])
    citations = [{"from": str(d.source_id), "to": str(d.depends_on_source_id), "relation": d.relation,
                  "detected_by": d.detected_by, "independent": d.relation not in NON_INDEPENDENT} for d in deps]
    return {
        "research_question_id": str(q.id), "sources": len(sources), "independent_evidence_count": len(groups),
        "groups": out, "edges": citations,
        "note": ("Sources that review, reanalyse or restate the same study are counted once. A source that only cites "
                 "another still counts on its own. Dependencies not recorded here are not guessed."),
    }


# ---------------------------------------------------------------- research saturation (§22)
LOW_YIELD_RATIO = 0.2          # fewer than 20% new sources in a round is a low yield
LOW_YIELD_ROUNDS = 2           # ...and it has to happen twice in a row


def saturation(db: Session, *, organization_id: UUID, question_id: UUID) -> dict:
    """Why searching should stop — with the actual reason, never "we searched everything"."""
    q = _question(db, organization_id, question_id)
    its = db.execute(select(ResearchIteration).where(
        ResearchIteration.organization_id == organization_id, ResearchIteration.research_question_id == q.id)
        .order_by(ResearchIteration.iteration)).scalars().all()
    done = len(its)
    routes_run = {i.route for i in its}
    compounds = q.compounds or ([q.compound] if q.compound else [])
    possible = {r for r in ROUTES if r in route_queries("(x)", compounds, q.outcome, q.population, q.related_species)}
    remaining = sorted(possible - routes_run)
    recent = its[-LOW_YIELD_ROUNDS:]
    low_yield = (len(recent) == LOW_YIELD_ROUNDS and
                 all(i.sources_seen > 0 and (i.new_sources / i.sources_seen) < LOW_YIELD_RATIO for i in recent))
    only_duplicates = bool(recent) and all(i.sources_seen > 0 and i.new_sources == 0 for i in recent)
    all_failed = bool(its) and all(i.providers_ok == 0 for i in its)

    if q.saturation_reason and q.saturation_reason != "not_saturated":
        reason, saturated = q.saturation_reason, True
    elif all_failed:
        reason, saturated = "provider_unavailable", False        # nothing was searched: not saturation
    elif done >= q.max_iterations:
        reason, saturated = "user_limit_reached", True
    elif only_duplicates:
        reason, saturated = "duplicate_sources_only", True
    elif not remaining and low_yield:
        reason, saturated = "low_marginal_yield", True
    elif not remaining and done > 0:
        reason, saturated = "query_variants_exhausted", True
    else:
        reason, saturated = "not_saturated", False
    return {
        "research_question_id": str(q.id), "saturated": saturated, "reason": reason,
        "iterations_run": done, "max_iterations": q.max_iterations,
        "routes_run": sorted(routes_run), "routes_not_yet_run": remaining,
        "new_sources_per_round": [{"iteration": i.iteration, "route": i.route, "seen": i.sources_seen,
                                   "new": i.new_sources, "duplicates": i.duplicate_sources} for i in its],
        "declared_at": q.saturation_at,
        "note": ("This is an operational stopping condition over the configured providers — not a claim that the "
                 "literature has been exhausted."),
    }


def declare_saturation(db: Session, *, organization_id: UUID, question_id: UUID, reason: str | None) -> dict:
    """A person ends the search and records why."""
    from app.models.research_dependency import SATURATION_REASONS

    q = _question(db, organization_id, question_id)
    computed = saturation(db, organization_id=organization_id, question_id=question_id)
    chosen = reason or computed["reason"]
    if chosen not in SATURATION_REASONS:
        raise HTTPException(422, f"reason must be one of: {', '.join(SATURATION_REASONS)}")
    q.saturation_reason = chosen
    q.saturation_at = _now() if chosen != "not_saturated" else None
    db.commit()
    return saturation(db, organization_id=organization_id, question_id=question_id)
