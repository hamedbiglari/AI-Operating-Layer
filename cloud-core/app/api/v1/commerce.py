"""
Products / Offers / Product Evidence / Product Relations / Trust
endpoints (master spec sections 26-30, endpoint surface reconciled
against section 50's literal list).

Section 50 lists exactly five product paths, all GET:

    GET /products
    GET /products/{id}
    GET /products/{id}/offers
    GET /products/{id}/evidence
    GET /products/{id}/related

All five are implemented exactly as written. The write endpoints below
(POST/PATCH, the status action, the verify actions, and the /trust
routes) go beyond that literal list — an approved, documented
deviation (docs/DECISIONS.md ADR-023): a merchant must be able to
create a product somehow, and section 50's list is a read-surface
sketch, not a prohibition on writes. Every one follows this project's
existing conventions: reads open to any authenticated user in the org,
writes gated on KNOWLEDGE_EDITOR_ROLES, `Page[...]` responses,
tenant-scoped 404s.

Verification actions are deliberately separate endpoints rather than
PATCH fields — sections 28 and 30 both require that verified status be
a reviewed act, never a side effect of editing something else.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import (
    KNOWLEDGE_EDITOR_ROLES,
    OfferAvailability,
    ProductRelationType,
    ProductStatus,
    TrustSubjectType,
    TrustType,
    VerificationStatus,
)
from app.models.offer import Offer
from app.models.product import Product
from app.models.product_evidence import ProductEvidence
from app.models.product_relation import ProductRelation
from app.models.trust_record import TrustRecord
from app.models.user import User
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.product import (
    OfferCreate,
    OfferRead,
    OfferUpdate,
    ProductCreate,
    ProductEvidenceCreate,
    ProductEvidenceRead,
    ProductEvidenceVerifyRequest,
    ProductRead,
    ProductRelationCreate,
    ProductRelationRead,
    ProductStatusChangeRequest,
    ProductUpdate,
    TrustRecordCreate,
    TrustRecordRead,
    TrustRecordVerifyRequest,
)
from app.security.dependencies import get_current_user, require_roles
from app.services import commerce_service, product_service

router = APIRouter(tags=["commerce"])


# --- Products ------------------------------------------------------------


@router.get("/products", response_model=Page[ProductRead])
def list_products(
    status_filter: ProductStatus | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    knowledge_object_id: UUID | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ProductRead]:
    items, total = product_service.list_products(
        db,
        organization_id=current_user.organization_id,
        status_filter=status_filter,
        category=category,
        brand=brand,
        knowledge_object_id=knowledge_object_id,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Product:
    return product_service.create_product(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        **payload.model_dump(),
    )


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(
    product_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Product:
    return product_service.get_product_or_404(
        db, product_id=product_id, organization_id=current_user.organization_id
    )


@router.patch("/products/{product_id}", response_model=ProductRead)
def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Product:
    product = product_service.get_product_or_404(
        db, product_id=product_id, organization_id=current_user.organization_id
    )
    return product_service.update_product(
        db, product=product, actor_user_id=current_user.id, **payload.model_dump(exclude_unset=True)
    )


@router.post("/products/{product_id}/status", response_model=ProductRead)
def change_product_status(
    product_id: UUID,
    payload: ProductStatusChangeRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Product:
    product = product_service.get_product_or_404(
        db, product_id=product_id, organization_id=current_user.organization_id
    )
    try:
        return product_service.change_product_status(
            db, product=product, new_status=payload.status, actor_user_id=current_user.id
        )
    except product_service.InvalidProductStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None


# --- Offers ----------------------------------------------------------------


@router.get("/products/{product_id}/offers", response_model=Page[OfferRead])
def list_product_offers(
    product_id: UUID,
    availability: OfferAvailability | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[OfferRead]:
    product_service.get_product_or_404(
        db, product_id=product_id, organization_id=current_user.organization_id
    )
    items, total = commerce_service.list_offers(
        db,
        organization_id=current_user.organization_id,
        product_id=product_id,
        availability=availability,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/products/{product_id}/offers", response_model=OfferRead, status_code=status.HTTP_201_CREATED)
def create_product_offer(
    product_id: UUID,
    payload: OfferCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Offer:
    product = product_service.get_product_or_404(
        db, product_id=product_id, organization_id=current_user.organization_id
    )
    return commerce_service.create_offer(
        db, product=product, actor_user_id=current_user.id, **payload.model_dump()
    )


@router.patch("/offers/{offer_id}", response_model=OfferRead)
def update_offer(
    offer_id: UUID,
    payload: OfferUpdate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Offer:
    offer = commerce_service.get_offer_or_404(
        db, offer_id=offer_id, organization_id=current_user.organization_id
    )
    return commerce_service.update_offer(
        db, offer=offer, actor_user_id=current_user.id, **payload.model_dump(exclude_unset=True)
    )


# --- Product Evidence --------------------------------------------------------


@router.get("/products/{product_id}/evidence", response_model=Page[ProductEvidenceRead])
def list_product_evidence(
    product_id: UUID,
    verification_status: VerificationStatus | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ProductEvidenceRead]:
    items, total = commerce_service.list_product_evidence(
        db,
        product_id=product_id,
        organization_id=current_user.organization_id,
        verification_status=verification_status,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post(
    "/products/{product_id}/evidence", response_model=ProductEvidenceRead, status_code=status.HTTP_201_CREATED
)
def link_product_evidence(
    product_id: UUID,
    payload: ProductEvidenceCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ProductEvidence:
    product = product_service.get_product_or_404(
        db, product_id=product_id, organization_id=current_user.organization_id
    )
    return commerce_service.link_product_evidence(
        db,
        product=product,
        evidence_id=payload.evidence_id,
        claim=payload.claim,
        actor_user_id=current_user.id,
    )


@router.post("/product-evidence/{link_id}/verify", response_model=ProductEvidenceRead)
def verify_product_evidence(
    link_id: UUID,
    payload: ProductEvidenceVerifyRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ProductEvidence:
    link = commerce_service.get_product_evidence_or_404(
        db, link_id=link_id, organization_id=current_user.organization_id
    )
    return commerce_service.verify_product_evidence(
        db,
        link=link,
        verification_status=payload.verification_status,
        note=payload.note,
        actor_user_id=current_user.id,
    )


# --- Product Relations ---------------------------------------------------------


@router.get("/products/{product_id}/related", response_model=Page[ProductRelationRead])
def list_related_products(
    product_id: UUID,
    relation_type: ProductRelationType | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ProductRelationRead]:
    items, total = commerce_service.list_product_relations(
        db,
        product_id=product_id,
        organization_id=current_user.organization_id,
        relation_type=relation_type,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post(
    "/products/{product_id}/related", response_model=ProductRelationRead, status_code=status.HTTP_201_CREATED
)
def create_product_relation(
    product_id: UUID,
    payload: ProductRelationCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> ProductRelation:
    product = product_service.get_product_or_404(
        db, product_id=product_id, organization_id=current_user.organization_id
    )
    return commerce_service.create_product_relation(
        db,
        product=product,
        related_product_id=payload.related_product_id,
        relation_type=payload.relation_type,
        confidence=payload.confidence,
        actor_user_id=current_user.id,
    )


# --- Trust Records ---------------------------------------------------------------


@router.get("/trust-records", response_model=Page[TrustRecordRead])
def list_trust_records(
    subject_type: TrustSubjectType | None = Query(default=None),
    subject_id: UUID | None = Query(default=None),
    trust_type: TrustType | None = Query(default=None),
    verification_status: VerificationStatus | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[TrustRecordRead]:
    items, total = commerce_service.list_trust_records(
        db,
        organization_id=current_user.organization_id,
        subject_type=subject_type,
        subject_id=subject_id,
        trust_type=trust_type,
        verification_status=verification_status,
        sort=sort,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/trust-records", response_model=TrustRecordRead, status_code=status.HTTP_201_CREATED)
def create_trust_record(
    payload: TrustRecordCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> TrustRecord:
    return commerce_service.create_trust_record(
        db,
        organization_id=current_user.organization_id,
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        trust_type=payload.trust_type,
        claim=payload.claim,
        evidence_id=payload.evidence_id,
        actor_user_id=current_user.id,
    )


@router.get("/trust-records/{record_id}", response_model=TrustRecordRead)
def get_trust_record(
    record_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> TrustRecord:
    return commerce_service.get_trust_record_or_404(
        db, record_id=record_id, organization_id=current_user.organization_id
    )


@router.post("/trust-records/{record_id}/verify", response_model=TrustRecordRead)
def verify_trust_record(
    record_id: UUID,
    payload: TrustRecordVerifyRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> TrustRecord:
    record = commerce_service.get_trust_record_or_404(
        db, record_id=record_id, organization_id=current_user.organization_id
    )
    return commerce_service.verify_trust_record(
        db,
        record=record,
        verification_status=payload.verification_status,
        note=payload.note,
        actor_user_id=current_user.id,
    )
