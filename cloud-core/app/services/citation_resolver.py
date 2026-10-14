"""
Vancouver citation resolver (ADR-116, prompt v3.0 §34–§58).

The algorithm is deliberately boring and deterministic:

    walk the sentences in document order
      → for each, take the sources that genuinely support it
        → a source new to this publication gets the next number
        → a source already seen reuses its number, forever (§39)
      → sort the sentence's numbers ascending and compress true runs into ranges (§40)

Four things it will not do, because the prompt forbids them and the code is where that is enforced:

  * invent a number for a source that is not in the publication (§61, §87);
  * give one number to two sources, or two numbers to one source (§59) — the database also refuses;
  * compress 1,3,5 into 1–5 (§40) — only genuinely consecutive runs become ranges;
  * fabricate bibliographic metadata (§88) — every reference is formatted from stored `Source` fields,
    and a field that is not stored is simply absent from the reference.

Duplicate ingestions of one bibliographic source collapse to one canonical source first (§56–§58), so a
paper ingested twice cannot occupy two numbers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.publication import (
    CITATION_REQUIRED_KINDS, Publication, PublicationReference, PublicationSentence, SentenceSource,
)
from app.models.evidence import Evidence
from app.models.source import Source

# which support states actually justify citing a source for a sentence (§48)
CITING_SUPPORT = ("supports", "partially_supports")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- number formatting
def compress(numbers: list[int]) -> str:
    """[1,2,3,4,5] -> '1–5'   ·   [1,3,5] -> '1,3,5'   ·   [1,2,3,7,8] -> '1–3,7,8'

    A run of two (e.g. 4,5) is written out, not hyphenated: '4–5' saves nothing and reads worse.
    The separator is an en dash, which is what Vancouver uses."""
    if not numbers:
        return ""
    ordered = sorted(set(numbers))
    parts: list[str] = []
    run_start = previous = ordered[0]
    for n in ordered[1:] + [None]:  # type: ignore[list-item]
        if n is not None and n == previous + 1:
            previous = n
            continue
        length = previous - run_start + 1
        if length >= 3:
            parts.append(f"{run_start}–{previous}")
        else:
            parts.extend(str(x) for x in range(run_start, previous + 1))
        if n is None:
            break
        run_start = previous = n
    return ",".join(parts)


def citation_text(numbers: list[int]) -> str:
    """§41 — exactly one space before the parenthesis is the caller's job; this returns '(1–5)'."""
    body = compress(numbers)
    return f"({body})" if body else ""


# ---------------------------------------------------------------- Vancouver reference strings
def _authors(meta: dict) -> str | None:
    authors = meta.get("authors")
    if not authors:
        return None
    if isinstance(authors, str):
        names = [a.strip() for a in authors.split(";") if a.strip()] or [authors.strip()]
    else:
        names = [str(a).strip() for a in authors if str(a).strip()]
    if not names:
        return None
    if len(names) > 6:                       # Vancouver: first six, then et al.
        return ", ".join(names[:6]) + ", et al"
    return ", ".join(names)


def format_reference(source: Source) -> tuple[str, dict]:
    """Build the reference string from stored fields only. Nothing is invented; a missing field is omitted.

    Returns the string and the exact fields that went into it, so the audit can prove nothing was added."""
    meta = dict(source.metadata_ or {})
    used: dict = {}
    bits: list[str] = []

    authors = _authors(meta)
    if authors:
        bits.append(f"{authors}.")
        used["authors"] = authors
    title = (source.title or "").strip()
    if title:
        bits.append(title if title.endswith((".", "?", "!")) else f"{title}.")
        used["title"] = title

    kind = str(getattr(source.source_type, "value", source.source_type) or "")
    container = meta.get("journal") or meta.get("container_title") or source.publisher
    if container:
        bits.append(f"{container}.")
        used["container"] = container

    year = source.publication_date.year if source.publication_date else meta.get("year")
    volume, issue, pages = meta.get("volume"), meta.get("issue"), meta.get("pages")
    if year:
        used["year"] = year
        locator = str(year)
        if volume:
            locator += f";{volume}"
            used["volume"] = volume
            if issue:
                locator += f"({issue})"
                used["issue"] = issue
        if pages:
            locator += f":{pages}"
            used["pages"] = pages
        bits.append(f"{locator}.")

    if source.doi:
        bits.append(f"doi:{source.doi}")
        used["doi"] = source.doi
    elif source.pmid:
        bits.append(f"PMID:{source.pmid}")
        used["pmid"] = source.pmid
    elif getattr(source, "isbn", None):
        bits.append(f"ISBN:{source.isbn}")
        used["isbn"] = source.isbn
    elif source.url:
        bits.append(source.url)
        used["url"] = source.url
        accessed = meta.get("accessed_at")
        if accessed:
            bits.append(f"[accessed {accessed}]")
            used["accessed_at"] = accessed

    text = " ".join(b for b in bits if b).strip()
    if not text:
        # §52 — say what is missing rather than invent a plausible-looking reference
        text = f"[source record {source.id} — no bibliographic metadata stored]"
    return text, {"fields_used": used, "source_kind": kind}


# ---------------------------------------------------------------- canonical source (§56–§58)
def canonical_source_id(db: Session, organization_id: UUID, source: Source) -> UUID:
    """Two ingestions of one paper must not take two numbers. Matched on DOI, then PMID, then URL —
    never on a title alone, which is not a reliable identity."""
    for field, value in (("doi", source.doi), ("pmid", source.pmid), ("url", source.url)):
        if not value:
            continue
        rows = db.execute(select(Source).where(
            Source.organization_id == organization_id,
            getattr(Source, field) == value).order_by(Source.created_at)).scalars().all()
        if rows:
            return rows[0].id                      # the earliest ingestion is the canonical record
    return source.id


# ---------------------------------------------------------------- the resolver
def resolve(db: Session, *, organization_id: UUID, publication_id: UUID) -> dict:
    """Assign numbers for one publication, in document order. Deterministic: the same content resolves
    to the same numbering every time (§45, §46)."""
    pub = db.execute(select(Publication).where(
        Publication.id == publication_id,
        Publication.organization_id == organization_id)).scalar_one_or_none()
    if pub is None:
        raise HTTPException(404, "Publication not found.")
    if pub.status == "published":
        raise HTTPException(409, "This publication is already published; create a new version instead.")

    pub.status = "resolving"
    db.flush()

    sentences = db.execute(select(PublicationSentence).where(
        PublicationSentence.publication_id == pub.id).order_by(PublicationSentence.position)).scalars().all()
    links = db.execute(select(SentenceSource).where(
        SentenceSource.organization_id == organization_id,
        SentenceSource.publication_sentence_id.in_([s.id for s in sentences]))).scalars().all() if sentences else []
    by_sentence: dict = {}
    for l in links:
        by_sentence.setdefault(l.publication_sentence_id, []).append(l)

    # start from scratch so a regeneration cannot inherit stale numbers (§66)
    for old in db.execute(select(PublicationReference).where(
            PublicationReference.publication_id == pub.id)).scalars().all():
        db.delete(old)
    db.flush()

    numbers: dict[UUID, int] = {}
    next_number = 1
    unsupported: list[int] = []

    for sentence in sentences:
        supporting = [l for l in by_sentence.get(sentence.id, []) if l.support in CITING_SUPPORT]
        assigned: list[int] = []
        # Several sources first cited by the same sentence are numbered in the order their evidence was
        # attached to the knowledge base, with the source id only as a tie-breaker. Deterministic, and it
        # reads the way a person would expect: study 1 before study 6.
        def _attach_order(link):
            ev = db.get(Evidence, link.evidence_id) if link.evidence_id else None
            return (ev.created_at if ev is not None else datetime.max.replace(tzinfo=timezone.utc), str(link.source_id))
        for link in sorted(supporting, key=_attach_order):
            src = db.get(Source, link.source_id)
            if src is None or src.organization_id != organization_id:
                continue
            canonical = canonical_source_id(db, organization_id, src)
            if canonical not in numbers:
                numbers[canonical] = next_number
                canonical_src = db.get(Source, canonical)
                formatted, extra = format_reference(canonical_src)
                db.add(PublicationReference(
                    organization_id=organization_id, publication_id=pub.id, source_id=canonical,
                    reference_number=next_number, first_sentence_position=sentence.position,
                    formatted=formatted, source_kind=extra["source_kind"],
                    is_user_generated=extra["source_kind"] in ("user_observation", "experiment", "internal_document"),
                    access_note=None if canonical_src.full_text_accessed else
                        {"abstract_only": "abstract only", "title_only": "title only",
                         "metadata_only": "metadata only"}.get(canonical_src.content_access),
                    metadata_=extra["fields_used"]))
                next_number += 1
            assigned.append(numbers[canonical])

        if assigned:
            sentence.citation_numbers = sorted(set(assigned))
            sentence.citation_text = citation_text(sentence.citation_numbers)
            sentence.evidence_unavailable = False
        else:
            sentence.citation_numbers = None
            sentence.citation_text = None
            # §61/§87 — a factual sentence with nothing behind it is marked, never given a fake number
            if sentence.kind in CITATION_REQUIRED_KINDS:
                sentence.evidence_unavailable = True
                unsupported.append(sentence.position)
        sentence.resolved = True

    pub.reference_count = len(numbers)
    pub.sentence_count = len(sentences)
    pub.status = "resolved"
    pub.resolved_at = _now()
    db.commit()
    return {"publication_id": str(pub.id), "publication_version": pub.publication_version,
            "sentences": len(sentences), "references": len(numbers),
            "sentences_without_evidence": unsupported,
            "note": ("Numbers follow first appearance in document order and are reused for repeated sources. "
                     "A factual sentence with no validated source is marked evidence-unavailable, never given "
                     "a citation.")}


def reference_list(db: Session, *, organization_id: UUID, publication_id: UUID) -> list[dict]:
    """§51 — numeric order, which is first-appearance order. Never alphabetical, never by year."""
    rows = db.execute(select(PublicationReference).where(
        PublicationReference.organization_id == organization_id,
        PublicationReference.publication_id == publication_id)
        .order_by(PublicationReference.reference_number)).scalars().all()
    return [{"number": r.reference_number, "source_id": str(r.source_id), "formatted": r.formatted,
             "source_kind": r.source_kind, "is_user_generated": r.is_user_generated,
             "access_note": r.access_note, "fields_used": r.metadata_,
             "first_cited_at_sentence": r.first_sentence_position} for r in rows]
