"""Source overview: sources with the status and counts behind the Sources list,
filtered, ordered and paged in one read.

derived_status is the first rule that holds, in this order:

  a. failed          any document's extraction_status is failed
  b. processing      any document is pending or extracting, or its current
                     conversion is pending
  c. completed       the source has documents and every one is extracted
  d. abstract_only   no documents, and content_access is abstract_only
  e. reference_only  no documents, any other content_access

A document's extraction_status already records how its conversion ended
(ingestion_service sets failed when no text came out, extracted when it did,
including OCR rescuing an empty conversion), so the conversion row is read
only for a pending current conversion. A document without a conversion row
(created as text) is judged by extraction_status alone.

The status is a SQL expression, so filtering and ordering by it happen across
all pages, never per page in the browser.
"""

from uuid import UUID

from sqlalchemy import BigInteger, and_, case, cast, distinct, func, literal, select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.document import Document
from app.models.document_artifact import DocumentConversion
from app.models.enums import DocumentConversionStatus, DocumentExtractionStatus
from app.models.evidence import Evidence
from app.models.source import Source
from app.schemas.source_overview import SourceDerivedStatus, SourceOverviewSort

COUNT_NAMES = ("documents", "knowledge_objects", "claims", "evidence")


def get_overview(
    db: Session,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
    search: str | None = None,
    source_type: str | None = None,
    status: SourceDerivedStatus | None = None,
    sort: SourceOverviewSort = SourceOverviewSort.UPDATED,
) -> tuple[list[dict], int, dict[SourceDerivedStatus, int]]:
    # At most one current conversion per document (uq_document_conversions_one_current),
    # so the outer join cannot duplicate documents.
    docs = (
        select(
            Document.source_id.label("source_id"),
            func.count().label("documents"),
            func.count().filter(Document.extraction_status == DocumentExtractionStatus.FAILED).label("failed"),
            func.count().filter(
                Document.extraction_status.in_((DocumentExtractionStatus.PENDING, DocumentExtractionStatus.EXTRACTING))
                | (DocumentConversion.conversion_status == DocumentConversionStatus.PENDING)
            ).label("processing"),
            # SUM of a bigint is numeric in Postgres; cast back so the API gets an int.
            cast(func.sum(Document.file_size), BigInteger).label("file_size"),
            func.max(func.coalesce(DocumentConversion.source_mime_type, Document.mime_type)).label("mime_type"),
            func.max(Document.updated_at).label("updated_at"),
        )
        .select_from(Document)
        .outerjoin(DocumentConversion, and_(DocumentConversion.document_id == Document.id,
                                            DocumentConversion.is_current))
        .where(Document.organization_id == organization_id)
        .group_by(Document.source_id)
        .subquery()
    )
    # Evidence with no linked claim still counts as evidence.
    links = (
        select(
            Evidence.source_id.label("source_id"),
            func.count(distinct(Evidence.id)).label("evidence"),
            func.count(distinct(Claim.id)).label("claims"),
            func.count(distinct(Claim.knowledge_object_id)).label("knowledge_objects"),
        )
        .select_from(Evidence)
        .outerjoin(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id)
        .outerjoin(Claim, and_(Claim.id == ClaimEvidence.claim_id, Claim.organization_id == organization_id))
        .where(Evidence.organization_id == organization_id)
        .group_by(Evidence.source_id)
        .subquery()
    )

    col = {
        "documents": func.coalesce(docs.c.documents, 0),
        "knowledge_objects": func.coalesce(links.c.knowledge_objects, 0),
        "claims": func.coalesce(links.c.claims, 0),
        "evidence": func.coalesce(links.c.evidence, 0),
    }
    derived_status = case(
        (docs.c.failed > 0, literal(SourceDerivedStatus.FAILED.value)),
        (docs.c.processing > 0, literal(SourceDerivedStatus.PROCESSING.value)),
        (docs.c.documents > 0, literal(SourceDerivedStatus.COMPLETED.value)),
        (Source.content_access == "abstract_only", literal(SourceDerivedStatus.ABSTRACT_ONLY.value)),
        else_=literal(SourceDerivedStatus.REFERENCE_ONLY.value),
    )
    # GREATEST ignores NULL, so a source without documents keeps its own updated_at.
    last_activity_at = func.greatest(Source.updated_at, docs.c.updated_at)
    mime_type = case((docs.c.documents == 1, docs.c.mime_type), else_=None)

    query = (
        select(Source)
        .where(Source.organization_id == organization_id)
        .outerjoin(docs, docs.c.source_id == Source.id)
        .outerjoin(links, links.c.source_id == Source.id)
        .add_columns(
            *(col[name].label(name) for name in COUNT_NAMES),
            derived_status.label("derived_status"),
            last_activity_at.label("last_activity_at"),
            docs.c.file_size.label("file_size"),
            mime_type.label("mime_type"),
        )
    )
    if search:
        pattern = f"%{search}%"
        query = query.where(
            Source.title.ilike(pattern) | Source.canonical_title.ilike(pattern) | Source.doi.ilike(pattern)
            | Source.pmid.ilike(pattern) | Source.url.ilike(pattern)
        )
    if source_type:
        query = query.where(Source.source_type == source_type)

    by_status = query.subquery()
    found = dict(db.execute(
        select(by_status.c.derived_status, func.count()).group_by(by_status.c.derived_status)
    ).all())
    counts_by_status = {s: found.get(s.value, 0) for s in SourceDerivedStatus}

    if status:
        query = query.where(derived_status == status.value)
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()

    if sort == SourceOverviewSort.NAME:
        order = (Source.title.asc(),)
    elif sort == SourceOverviewSort.CLAIMS:
        order = (col["claims"].desc(), last_activity_at.desc())
    elif sort == SourceOverviewSort.EVIDENCE:
        order = (col["evidence"].desc(), last_activity_at.desc())
    else:
        order = (last_activity_at.desc(),)
    # The id makes the order total, so offset paging never repeats or skips a row.
    rows = db.execute(query.order_by(*order, Source.id).limit(limit).offset(offset)).all()

    items = [
        {
            "source": row[0],
            "counts": {name: getattr(row, name) for name in COUNT_NAMES},
            "derived_status": row.derived_status,
            "last_activity_at": row.last_activity_at,
            "file_size": row.file_size,
            "mime_type": row.mime_type,
        }
        for row in rows
    ]
    return items, total, counts_by_status
