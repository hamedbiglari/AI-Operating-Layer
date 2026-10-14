"""
Customer Context & Recommendation endpoints (master spec sections
32/33, §50's `/recommendations` and `/context` groups).

§50 literal paths, all implemented:
    POST /recommendations
    GET  /recommendations/{id}
    POST /context
    GET  /context/{id}

`POST /context/query` from §50 is implemented as
`POST /recommendations` taking an optional `customer_context_id` — the
same capability (recommend against a context) without a second path
that would duplicate it. Documented in ADR-030.

Additions beyond the literal list (listing, update, consent
withdrawal) follow the same conventions as every other resource here
and are documented rather than silent.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.customer_context import CustomerContext
from app.models.enums import KNOWLEDGE_EDITOR_ROLES, RecommendationStatus
from app.models.recommendation import Recommendation
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.recommendation import (
    CustomerContextCreate,
    CustomerContextRead,
    CustomerContextUpdate,
    RecommendationRead,
    RecommendationRequest,
    RecommendationResponse,
    RejectedCandidate,
)
from app.security.dependencies import get_current_user, require_roles
from app.services import customer_context_service, recommendation_service
from app.services import recommendation_policy as policy

router = APIRouter(tags=["recommendation"])


# --- Customer Context ------------------------------------------------------


@router.post("/context", response_model=CustomerContextRead, status_code=status.HTTP_201_CREATED)
def create_context(
    payload: CustomerContextCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> CustomerContext:
    return customer_context_service.create_customer_context(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        **payload.model_dump(),
    )


@router.get("/context", response_model=Page[CustomerContextRead])
def list_contexts(
    customer_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[CustomerContextRead]:
    items, total = customer_context_service.list_customer_contexts(
        db,
        organization_id=current_user.organization_id,
        customer_id=customer_id,
        session_id=session_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/context/{context_id}", response_model=CustomerContextRead)
def get_context(
    context_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> CustomerContext:
    return customer_context_service.get_context_or_404(
        db, context_id=context_id, organization_id=current_user.organization_id
    )


@router.patch("/context/{context_id}", response_model=CustomerContextRead)
def update_context(
    context_id: UUID,
    payload: CustomerContextUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> CustomerContext:
    context = customer_context_service.get_context_or_404(
        db, context_id=context_id, organization_id=current_user.organization_id
    )
    return customer_context_service.update_customer_context(
        db, context=context, actor_user_id=current_user.id, **payload.model_dump(exclude_unset=True)
    )


@router.post("/context/{context_id}/withdraw-consent", response_model=CustomerContextRead)
def withdraw_context_consent(
    context_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> CustomerContext:
    """Privacy action: clears identity fields and blocks this context
    from producing any further recommendations (a hard gate, not a
    ranking penalty)."""
    context = customer_context_service.get_context_or_404(
        db, context_id=context_id, organization_id=current_user.organization_id
    )
    return customer_context_service.withdraw_consent(
        db, context=context, actor_user_id=current_user.id
    )


# --- Recommendations ---------------------------------------------------------


@router.post("/recommendations", response_model=RecommendationResponse)
def create_recommendations(
    payload: RecommendationRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    """Returns 200 even when the answer is NO_RECOMMENDATION — that is
    a successful, meaningful result (the engine declined), not a
    failure. Callers must read `status`, not just check for an empty
    list."""
    context = None
    if payload.customer_context_id is not None:
        context = customer_context_service.get_context_or_404(
            db, context_id=payload.customer_context_id, organization_id=current_user.organization_id
        )

    overall, explanation, rows, rejected = recommendation_service.recommend(
        db,
        organization_id=current_user.organization_id,
        response_mode=payload.response_mode,
        customer_context=context,
        query_id=payload.query_id,
        knowledge_object_id=payload.knowledge_object_id,
        category=payload.category,
        brand=payload.brand,
        product_ids=payload.product_ids,
        limit=payload.limit,
        persist=payload.persist,
        actor_user_id=current_user.id,
    )

    return RecommendationResponse(
        status=overall if rows else RecommendationStatus.NO_RECOMMENDATION,
        response_mode=payload.response_mode,
        policy_version=policy.POLICY_VERSION,
        explanation=explanation,
        recommendations=[RecommendationRead.model_validate(r) for r in rows],
        rejected=[RejectedCandidate(**r) for r in rejected],
    )


@router.get("/recommendations", response_model=Page[RecommendationRead])
def list_recommendations(
    customer_context_id: UUID | None = Query(default=None),
    product_id: UUID | None = Query(default=None),
    status_filter: RecommendationStatus | None = Query(default=None, alias="status"),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[RecommendationRead]:
    items, total = recommendation_service.list_recommendations(
        db,
        organization_id=current_user.organization_id,
        customer_context_id=customer_context_id,
        product_id=product_id,
        status=status_filter,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/recommendations/{recommendation_id}", response_model=RecommendationRead)
def get_recommendation(
    recommendation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Recommendation:
    return recommendation_service.get_recommendation_or_404(
        db, recommendation_id=recommendation_id, organization_id=current_user.organization_id
    )
