"""
Query Engine endpoints (master spec section 23-25, endpoint surface
reconciled against section 50's literal 4-line list — see
docs/DECISIONS.md for the additions beyond those 4 lines and why each
was judged a necessary, conventional complement rather than scope
creep).

POST /queries/import              -- CSV or Excel (.xlsx) file, OR a JSON row batch (manual entry reuses this, source=manual)
GET  /queries                     -- filter by ?status=, ?source=, ?intent_type=
GET  /queries/{id}
PATCH /queries/{id}                -- search_volume/commercial_value/priority only
POST /queries/{id}/archive
GET  /queries/{id}/intents
POST /queries/{id}/intents          -- manual override
POST /queries/{id}/classify         -- run the rule engine on one query
POST /queries/classify              -- run the rule engine on every still-DISCOVERED query in the org
POST /queries/cluster               -- (re)cluster the org's active queries
GET  /query-clusters
GET  /query-clusters/{id}
GET  /query-clusters/{id}/members
GET  /query-groups
POST /query-groups
GET  /query-groups/{id}
PATCH /query-groups/{id}
GET  /query-groups/{id}/members
POST /query-groups/{id}/members
DELETE /query-groups/{id}/members/{membership_id}
GET  /query-groups/{id}/knowledge-need-assessment

Reads open to any authenticated user; writes require
KNOWLEDGE_EDITOR_ROLES — the same split every resource in this API
uses.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query as QueryParam, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import (
    KNOWLEDGE_EDITOR_ROLES,
    IntentType,
    QueryPriority,
    QuerySource,
    QueryStatus,
)
from app.models.intent import Intent
from app.models.query import Query
from app.models.query_cluster import QueryCluster
from app.models.query_group import QueryGroup
from app.models.query_group_membership import QueryGroupMembership
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.intent import IntentRead, ManualIntentCreate
from app.schemas.query import (
    QueryImportResult,
    QueryImportResultItem,
    QueryImportRow,
    QueryRead,
    QueryUpdate,
)
from app.schemas.query_cluster import QueryClusterMemberRead, QueryClusterRead, QueryClusterRunResult
from app.schemas.query_group import (
    KnowledgeNeedAssessment,
    QueryGroupCreate,
    QueryGroupMembershipCreate,
    QueryGroupMembershipRead,
    QueryGroupRead,
    QueryGroupUpdate,
)
from app.security.dependencies import get_current_user, require_roles
from app.services import intent_service, query_cluster_service, query_group_service, query_service

router = APIRouter(tags=["query-engine"])


# --- Queries -------------------------------------------------------------


@router.post("/queries/import", response_model=QueryImportResult, status_code=status.HTTP_201_CREATED)
async def import_queries(
    source: QuerySource = Form(...),
    file: UploadFile | None = File(default=None),
    rows_json: str | None = Form(default=None),
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> QueryImportResult:
    if file is not None:
        content = await file.read()
        filename = (file.filename or "").lower()
        is_excel = filename.endswith(".xlsx") or file.content_type in (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        rows = query_service.parse_excel_rows(content) if is_excel else query_service.parse_csv_rows(content)
    elif rows_json is not None:
        try:
            raw_rows = json.loads(rows_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="rows_json must be valid JSON."
            ) from exc
        rows = [QueryImportRow(**row) for row in raw_rows]
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide either 'file' or 'rows_json'."
        )

    results = query_service.import_queries(
        db, organization_id=current_user.organization_id, source=source, rows=rows, actor_user_id=current_user.id
    )
    items = [QueryImportResultItem(query_id=q.id, query=q.query, created=created) for q, created in results]
    return QueryImportResult(
        created_count=sum(1 for _, created in results if created),
        matched_count=sum(1 for _, created in results if not created),
        items=items,
    )


@router.get("/queries", response_model=Page[QueryRead])
def list_queries(
    status_filter: QueryStatus | None = QueryParam(default=None, alias="status"),
    source: QuerySource | None = QueryParam(default=None),
    intent_type: IntentType | None = QueryParam(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[QueryRead]:
    items, total = query_service.list_queries(
        db,
        organization_id=current_user.organization_id,
        status_filter=status_filter,
        source=source,
        intent_type=intent_type,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/queries/{query_id}", response_model=QueryRead)
def get_query(
    query_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Query:
    return query_service.get_query_or_404(db, query_id=query_id, organization_id=current_user.organization_id)


@router.patch("/queries/{query_id}", response_model=QueryRead)
def update_query(
    query_id: UUID,
    payload: QueryUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Query:
    query = query_service.get_query_or_404(db, query_id=query_id, organization_id=current_user.organization_id)
    return query_service.update_query(
        db,
        query=query,
        search_volume=payload.search_volume,
        commercial_value=payload.commercial_value,
        priority=payload.priority,
        actor_user_id=current_user.id,
    )


@router.post("/queries/{query_id}/archive", response_model=QueryRead)
def archive_query(
    query_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Query:
    query = query_service.get_query_or_404(db, query_id=query_id, organization_id=current_user.organization_id)
    return query_service.archive_query(db, query=query, actor_user_id=current_user.id)


# --- Intent ----------------------------------------------------------------


@router.get("/queries/{query_id}/intents", response_model=Page[IntentRead])
def list_intents(
    query_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[IntentRead]:
    query_service.get_query_or_404(db, query_id=query_id, organization_id=current_user.organization_id)
    items, total = intent_service.list_intents_for_query(
        db, query_id=query_id, sort=sort, limit=pagination.limit, offset=pagination.offset
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/queries/{query_id}/intents", response_model=IntentRead, status_code=status.HTTP_201_CREATED)
def create_manual_intent(
    query_id: UUID,
    payload: ManualIntentCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Intent:
    query = query_service.get_query_or_404(db, query_id=query_id, organization_id=current_user.organization_id)
    return intent_service.create_manual_intent(
        db,
        query=query,
        intent_type=payload.intent_type,
        entity_id=payload.entity_id,
        confidence=payload.confidence,
        reason=payload.reason,
        is_primary=payload.is_primary,
        actor_user_id=current_user.id,
    )


@router.post("/queries/{query_id}/classify", response_model=list[IntentRead])
def classify_query(
    query_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> list[Intent]:
    query = query_service.get_query_or_404(db, query_id=query_id, organization_id=current_user.organization_id)
    return intent_service.classify_query(db, query=query, actor_user_id=current_user.id)


@router.post("/queries/classify", response_model=dict)
def classify_pending_queries(
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    items, _ = query_service.list_queries(
        db,
        organization_id=current_user.organization_id,
        status_filter=QueryStatus.DISCOVERED,
        source=None,
        limit=5000,
        offset=0,
    )
    classified_count = 0
    for query in items:
        created = intent_service.classify_query(db, query=query, actor_user_id=current_user.id)
        if created:
            classified_count += 1
    return {"scanned": len(items), "classified": classified_count}


# --- Clustering --------------------------------------------------------


@router.post("/queries/cluster", response_model=QueryClusterRunResult)
def cluster_queries(
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> QueryClusterRunResult:
    cluster_count, clustered_count = query_cluster_service.cluster_queries(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.id
    )
    return QueryClusterRunResult(
        cluster_count=cluster_count, clustered_query_count=clustered_count, unclustered_query_count=0
    )


@router.get("/query-clusters", response_model=Page[QueryClusterRead])
def list_query_clusters(
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[QueryClusterRead]:
    items, total = query_cluster_service.list_clusters(
        db, organization_id=current_user.organization_id, sort=sort,
        limit=pagination.limit, offset=pagination.offset
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/query-clusters/{cluster_id}", response_model=QueryClusterRead)
def get_query_cluster(
    cluster_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> QueryCluster:
    return query_cluster_service.get_cluster_or_404(
        db, cluster_id=cluster_id, organization_id=current_user.organization_id
    )


@router.get("/query-clusters/{cluster_id}/members", response_model=Page[QueryClusterMemberRead])
def list_query_cluster_members(
    cluster_id: UUID,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[QueryClusterMemberRead]:
    # No `sort` here, deliberately: members are ordered by similarity
    # score against the cluster representative, and that order IS the
    # information. See tests/test_sorting.py::_EXCLUDED.
    items, total = query_cluster_service.list_cluster_members(
        db,
        cluster_id=cluster_id,
        organization_id=current_user.organization_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


# --- Query Groups --------------------------------------------------------


@router.get("/query-groups", response_model=Page[QueryGroupRead])
def list_query_groups(
    primary_intent: IntentType | None = QueryParam(default=None),
    priority: QueryPriority | None = QueryParam(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[QueryGroupRead]:
    items, total = query_group_service.list_query_groups(
        db,
        organization_id=current_user.organization_id,
        primary_intent=primary_intent,
        priority=priority,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/query-groups", response_model=QueryGroupRead, status_code=status.HTTP_201_CREATED)
def create_query_group(
    payload: QueryGroupCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> QueryGroup:
    return query_group_service.create_query_group(
        db,
        organization_id=current_user.organization_id,
        name=payload.name,
        primary_intent=payload.primary_intent,
        target_entity_id=payload.target_entity_id,
        priority=payload.priority,
        actor_user_id=current_user.id,
    )


@router.get("/query-groups/{group_id}", response_model=QueryGroupRead)
def get_query_group(
    group_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> QueryGroup:
    return query_group_service.get_query_group_or_404(
        db, group_id=group_id, organization_id=current_user.organization_id
    )


@router.patch("/query-groups/{group_id}", response_model=QueryGroupRead)
def update_query_group(
    group_id: UUID,
    payload: QueryGroupUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> QueryGroup:
    group = query_group_service.get_query_group_or_404(
        db, group_id=group_id, organization_id=current_user.organization_id
    )
    return query_group_service.update_query_group(
        db, group=group, name=payload.name, priority=payload.priority, actor_user_id=current_user.id
    )


@router.get("/query-groups/{group_id}/members", response_model=Page[QueryGroupMembershipRead])
def list_query_group_members(
    group_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[QueryGroupMembershipRead]:
    items, total = query_group_service.list_group_members(
        db,
        group_id=group_id,
        organization_id=current_user.organization_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post(
    "/query-groups/{group_id}/members", response_model=QueryGroupMembershipRead, status_code=status.HTTP_201_CREATED
)
def add_query_group_member(
    group_id: UUID,
    payload: QueryGroupMembershipCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> QueryGroupMembership:
    group = query_group_service.get_query_group_or_404(
        db, group_id=group_id, organization_id=current_user.organization_id
    )
    return query_group_service.add_query_to_group(
        db, group=group, query_id=payload.query_id, actor_user_id=current_user.id
    )


@router.delete("/query-groups/{group_id}/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_query_group_member(
    group_id: UUID,
    membership_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> None:
    group = query_group_service.get_query_group_or_404(
        db, group_id=group_id, organization_id=current_user.organization_id
    )
    membership = query_group_service.get_membership_or_404(
        db, membership_id=membership_id, organization_id=current_user.organization_id
    )
    if membership.query_group_id != group.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found in this group.")
    query_group_service.remove_query_from_group(db, group=group, membership=membership, actor_user_id=current_user.id)


@router.get("/query-groups/{group_id}/knowledge-need-assessment", response_model=KnowledgeNeedAssessment)
def get_knowledge_need_assessment(
    group_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> KnowledgeNeedAssessment:
    group = query_group_service.get_query_group_or_404(
        db, group_id=group_id, organization_id=current_user.organization_id
    )
    return query_group_service.assess_knowledge_need(db, group=group)
