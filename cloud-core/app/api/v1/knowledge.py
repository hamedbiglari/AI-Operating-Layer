"""
Knowledge Object endpoints (master spec section 50 `/knowledge` group).

GET  /knowledge/search        -- alias of GET /knowledge with ?search=
GET  /knowledge/overview      -- the Knowledge list's rows with per-object counts
GET  /knowledge/{id}
POST /knowledge
PATCH /knowledge/{id}
POST /knowledge/{id}/publish
DELETE /knowledge/{id}         -- archives, does not hard-delete
GET  /knowledge/{id}/entities
GET  /knowledge/{id}/claims
GET  /knowledge/{id}/provenance -- claims with their evidence, sources and documents
GET  /knowledge/{id}/relations
GET  /knowledge/{id}/versions
GET  /knowledge/{id}/gaps
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import KNOWLEDGE_EDITOR_ROLES, KnowledgeObjectStatus
from app.models.knowledge_object import KnowledgeObject
from app.models.user import User
from app.schemas.claim import ClaimRead
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.entity import EntityRead
from app.schemas.knowledge_gap import KnowledgeGapRead
from app.schemas.knowledge_object import (
    KnowledgeObjectCreate,
    KnowledgeObjectRead,
    KnowledgeObjectUpdate,
)
from app.schemas.knowledge_overview import KnowledgeOverviewItem, KnowledgeOverviewPage, KnowledgeOverviewSort
from app.schemas.knowledge_version import KnowledgeVersionRead
from app.schemas.provenance import ProvenanceRead
from app.schemas.relationship import RelationshipRead
from app.security.dependencies import get_current_user, require_roles
from app.services import entity_service, knowledge_gap_service, knowledge_service, knowledge_representation
from app.services import claim_service, knowledge_overview_service, provenance_service
from app.services.relationship_service import list_relationships_for_node

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("", response_model=Page[KnowledgeObjectRead])
def list_knowledge_objects(
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    search: str | None = Query(default=None, max_length=500),
    object_type: str | None = Query(default=None, max_length=100),
    status_filter: KnowledgeObjectStatus | None = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[KnowledgeObjectRead]:
    items, total = knowledge_service.list_knowledge_objects(
        db,
        organization_id=current_user.organization_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
        search=search,
        object_type=object_type,
        status=status_filter,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/search", response_model=Page[KnowledgeObjectRead])
def search_knowledge_objects(
    q: str = Query(min_length=1, max_length=500),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[KnowledgeObjectRead]:
    """Section 50 lists `GET /knowledge/search` as its own path. Phase 2
    implements it as simple ILIKE text search; semantic (pgvector) search
    arrives once document_chunks/embeddings exist in Phase 3."""
    # No `sort` here, deliberately: search results are relevance-ordered
    # and an arbitrary sort would discard the ranking that is the point of
    # a search endpoint. See tests/test_sorting.py::_EXCLUDED.
    items, total = knowledge_service.list_knowledge_objects(
        db,
        organization_id=current_user.organization_id,
        limit=pagination.limit,
        offset=pagination.offset,
        search=q,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


# Registered before /{object_id}, which would otherwise match "overview".
@router.get("/overview", response_model=KnowledgeOverviewPage)
def knowledge_overview(
    search: str | None = Query(default=None, max_length=500),
    object_type: str | None = Query(default=None, max_length=100),
    status_filter: KnowledgeObjectStatus | None = Query(default=None, alias="status"),
    sort: KnowledgeOverviewSort = Query(default=KnowledgeOverviewSort.ACTION_NEEDED),
    include_finished: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    knowledge_object_id: UUID | None = Query(default=None, alias="id"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeOverviewPage:
    """The Knowledge list's rows: the same filters as GET /knowledge, plus the
    per-object counts, ordered and paged server-side. Archived objects are
    left out; finished ones only with include_finished=true.

    With ?id= it is the Knowledge detail header's one row
    (any status), whatever filters the list had; an unknown id is a 404."""
    if knowledge_object_id:
        knowledge_service.get_knowledge_object_or_404(
            db, object_id=knowledge_object_id, organization_id=current_user.organization_id
        )
        search = object_type = status_filter = None
        offset = 0
    rows, total = knowledge_overview_service.get_overview(
        db,
        organization_id=current_user.organization_id,
        limit=limit,
        offset=offset,
        search=search,
        object_type=object_type,
        status=status_filter,
        sort=sort,
        include_finished=include_finished,
        object_id=knowledge_object_id,
    )
    items = [
        KnowledgeOverviewItem(
            **KnowledgeObjectRead.model_validate(r["object"]).model_dump(), counts=r["counts"], finished=r["finished"]
        )
        for r in rows
    ]
    return KnowledgeOverviewPage(items=items, total=total, limit=limit, offset=offset, finished_visible=include_finished)


@router.post("", response_model=KnowledgeObjectRead, status_code=status.HTTP_201_CREATED)
def create_knowledge_object(
    payload: KnowledgeObjectCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> KnowledgeObject:
    try:
        return knowledge_service.create_knowledge_object(
            db,
            organization_id=current_user.organization_id,
            canonical_name=payload.canonical_name,
            slug=payload.slug,
            object_type=payload.object_type,
            description=payload.description,
            language=payload.language,
            confidence=payload.confidence,
            actor_user_id=current_user.id,
        )
    except knowledge_service.SlugConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A knowledge object with this slug already exists"
        ) from None


@router.get("/{object_id}", response_model=KnowledgeObjectRead)
def get_knowledge_object(
    object_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeObject:
    return knowledge_service.get_knowledge_object_or_404(
        db, object_id=object_id, organization_id=current_user.organization_id
    )


@router.patch("/{object_id}", response_model=KnowledgeObjectRead)
def update_knowledge_object(
    object_id: UUID,
    payload: KnowledgeObjectUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> KnowledgeObject:
    obj = knowledge_service.get_knowledge_object_or_404(
        db, object_id=object_id, organization_id=current_user.organization_id
    )
    return knowledge_service.update_knowledge_object(
        db,
        obj=obj,
        canonical_name=payload.canonical_name,
        description=payload.description,
        status=payload.status,
        language=payload.language,
        confidence=payload.confidence,
        public_visibility=payload.public_visibility,
        ai_visibility=payload.ai_visibility,
        change_summary=payload.change_summary,
        actor_user_id=current_user.id,
        category_id=payload.category_id,
    )


@router.post("/{object_id}/publish", response_model=KnowledgeObjectRead)
def publish_knowledge_object(
    object_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> KnowledgeObject:
    obj = knowledge_service.get_knowledge_object_or_404(
        db, object_id=object_id, organization_id=current_user.organization_id
    )
    return knowledge_service.publish_knowledge_object(db, obj=obj, actor_user_id=current_user.id)


@router.delete("/{object_id}", response_model=KnowledgeObjectRead)
def archive_knowledge_object(
    object_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> KnowledgeObject:
    obj = knowledge_service.get_knowledge_object_or_404(
        db, object_id=object_id, organization_id=current_user.organization_id
    )
    return knowledge_service.archive_knowledge_object(db, obj=obj, actor_user_id=current_user.id)


@router.get("/{object_id}/entities", response_model=Page[EntityRead])
def list_entities_for_knowledge_object(
    object_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[EntityRead]:
    knowledge_service.get_knowledge_object_or_404(
        db, object_id=object_id, organization_id=current_user.organization_id
    )
    items, total = entity_service.list_entities(
        db,
        organization_id=current_user.organization_id,
        knowledge_object_id=object_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/{object_id}/claims", response_model=Page[ClaimRead])
def list_claims_for_knowledge_object(
    object_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ClaimRead]:
    knowledge_service.get_knowledge_object_or_404(
        db, object_id=object_id, organization_id=current_user.organization_id
    )
    items, total = claim_service.list_claims(
        db,
        organization_id=current_user.organization_id,
        knowledge_object_id=object_id,
        status=None,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/{object_id}/provenance", response_model=ProvenanceRead)
def get_provenance_for_knowledge_object(
    object_id: UUID,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """One page of the object's claims, each with its evidence links, plus
    the evidence, sources and documents those links reach, keyed by id."""
    return provenance_service.get_knowledge_provenance(
        db,
        ko_id=object_id,
        org_id=current_user.organization_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{object_id}/relations", response_model=Page[RelationshipRead])
def list_relations_for_knowledge_object(
    object_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[RelationshipRead]:
    """Relationships where this Knowledge Object is either endpoint."""
    knowledge_service.get_knowledge_object_or_404(
        db, object_id=object_id, organization_id=current_user.organization_id
    )
    items, total = list_relationships_for_node(
        db,
        organization_id=current_user.organization_id,
        node_id=object_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/{object_id}/versions", response_model=list[KnowledgeVersionRead])
def list_versions_for_knowledge_object(
    object_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list:
    knowledge_service.get_knowledge_object_or_404(
        db, object_id=object_id, organization_id=current_user.organization_id
    )
    return knowledge_service.list_knowledge_versions(
        db, knowledge_object_id=object_id, organization_id=current_user.organization_id
    )


@router.get("/{object_id}/gaps", response_model=Page[KnowledgeGapRead])
def list_gaps_for_knowledge_object(
    object_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[KnowledgeGapRead]:
    knowledge_service.get_knowledge_object_or_404(
        db, object_id=object_id, organization_id=current_user.organization_id
    )
    items, total = knowledge_gap_service.list_knowledge_gaps(
        db,
        organization_id=current_user.organization_id,
        knowledge_object_id=object_id,
        status=None,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


# --- Machine-readable representations (§11, §12, §25) -----------------------
#
# All three formats are generated from the SAME canonical Knowledge Object,
# so they cannot drift. Before this existed, the only Markdown in the system
# was the WordPress plugin rendering `post_content` - WordPress's copy, not
# the canonical object. See ADR-067.


@router.get("/{knowledge_object_id}/markdown", response_class=PlainTextResponse)
def knowledge_markdown(
    knowledge_object_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """Canonical Markdown. Every claim carries its status and evidence
    strength, so a draft claim cannot be mistaken for an established one."""
    markdown = knowledge_representation.to_markdown(
        db, knowledge_object_id=knowledge_object_id,
        organization_id=current_user.organization_id,
    )
    if markdown is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Knowledge object not found")
    return PlainTextResponse(content=markdown, media_type="text/markdown; charset=utf-8")


@router.get("/{knowledge_object_id}/representation")
def knowledge_json_representation(
    knowledge_object_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Structured JSON with an explicit `coverage` block."""
    data = knowledge_representation.to_json(
        db, knowledge_object_id=knowledge_object_id,
        organization_id=current_user.organization_id,
    )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Knowledge object not found")
    return data


@router.get("/{knowledge_object_id}/jsonld")
def knowledge_json_ld(
    knowledge_object_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """schema.org JSON-LD.

    ONLY approved, evidence-backed claims appear. A draft claim published as
    structured data is a public assertion the merchant cannot support."""
    document = knowledge_representation.to_json_ld(
        db, knowledge_object_id=knowledge_object_id,
        organization_id=current_user.organization_id,
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Knowledge object not found")
    return document
