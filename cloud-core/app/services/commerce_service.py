"""
Offer / ProductEvidence / ProductRelation / TrustRecord services
(master spec sections 27-30).

All four share one module because they share one invariant worth
stating once: **every write validates the parent Product (or every
referenced row) against the caller's organization first**, via the
existing tenant-scoped getters, before anything is inserted. A
merchant can never attach an offer, an evidence link, a relation, or a
trust record to another organization's product or evidence.

Two spec rules are enforced structurally here rather than by
convention:

- **Verification is never automatic** (sections 28 and 30). Every
  ProductEvidence and TrustRecord row is created UNVERIFIED, and the
  ONLY path to VERIFIED is an explicit human `verify_*` call, which
  also stamps `verified_at`. Section 28: "Do not allow unsupported
  marketing claims to be presented as verified evidence."
- **Evidence scope is preserved** (the Phase 7 brief's critical rule).
  `link_product_evidence` requires a non-empty `claim` and records it
  on the link itself, so a piece of evidence is always attached to one
  specific stated assertion about the product. Composition evidence
  cannot become clinical-efficacy evidence by accident, because the
  claim text travels with the link and a human must both write it and
  verify it. See app/models/product_evidence.py's docstring.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.claim import Claim
from app.models.enums import (
    EvidenceStatus,
    OfferAvailability,
    ProductRelationType,
    TrustSubjectType,
    TrustType,
    VerificationStatus,
)
from app.models.evidence import Evidence
from app.models.offer import Offer
from app.models.organization import Organization
from app.models.product import Product
from app.models.product_evidence import ProductEvidence
from app.models.product_relation import ProductRelation
from app.models.site import Site
from app.models.trust_record import TrustRecord
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.evidence_service import get_evidence_or_404
from app.services.product_service import get_product_or_404


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Offer columns a client may edit but may not null out (NOT NULL in
# the schema). Everything else on an Offer is genuinely nullable and an
# explicit null legitimately clears it — `price = null` in particular
# is how "price on request" is expressed.
_NON_NULLABLE_OFFER_FIELDS = frozenset({"availability", "condition"})


def _offer_constraint_message(exc: IntegrityError) -> str:
    """Turn a violated CHECK constraint into a message that names what
    the caller actually did wrong, rather than leaking raw SQL."""
    text = str(getattr(exc, "orig", exc))
    if "ck_offers_validity_window_ordered" in text:
        return "valid_until must be later than valid_from."
    if "ck_offers_price_non_negative" in text:
        return "price cannot be negative."
    if "ck_offers_stock_quantity_non_negative" in text:
        return "stock_quantity cannot be negative."
    return "Offer violates a database constraint."


# --- Offers --------------------------------------------------------------


def list_offers(
    db: Session,
    *,
    organization_id: UUID,
    product_id: UUID | None,
    availability: OfferAvailability | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Offer], int]:
    base = select(Offer).where(Offer.organization_id == organization_id)
    if product_id:
        base = base.where(Offer.product_id == product_id)
    if availability:
        base = base.where(Offer.availability == availability)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(apply_sort(base, Offer, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_offer_or_404(db: Session, *, offer_id: UUID, organization_id: UUID) -> Offer:
    return get_tenant_scoped_or_404(
        db, Offer, offer_id, organization_id=organization_id, not_found_message="Offer not found"
    )


def create_offer(db: Session, *, product: Product, actor_user_id: UUID, **fields) -> Offer:
    offer = Offer(organization_id=product.organization_id, product_id=product.id, **fields)
    db.add(offer)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_offer_constraint_message(exc),
        ) from None

    record_audit_log(
        db,
        organization_id=product.organization_id,
        user_id=actor_user_id,
        action="offer.created",
        resource_type="offer",
        resource_id=offer.id,
        new_value={
            "product_id": str(product.id),
            "availability": offer.availability.value,
            "price": float(offer.price) if offer.price is not None else None,
        },
    )
    db.commit()
    db.refresh(offer)
    return offer


def update_offer(db: Session, *, offer: Offer, actor_user_id: UUID, **fields) -> Offer:
    """Same explicit-null semantics as update_product (see its
    docstring): `fields` arrives from `model_dump(exclude_unset=True)`,
    so an absent key means "leave alone" and a present null means
    "clear it". This matters commercially — clearing `price` back to
    NULL is how a merchant moves an offer to "price on request", which
    the previous skip-every-None behaviour made impossible.

    The CHECK constraints on this table (non-negative price/stock, and
    `valid_until > valid_from`) are real and reachable from an update:
    lowering `valid_until` below an existing `valid_from` is a
    perfectly plausible edit. Those now surface as a 422 with the
    constraint named, rather than a raw database error escaping to the
    caller."""
    old_value = {
        "price": float(offer.price) if offer.price is not None else None,
        "availability": offer.availability.value,
        "stock_quantity": offer.stock_quantity,
    }

    for field_name, value in fields.items():
        if value is None and field_name in _NON_NULLABLE_OFFER_FIELDS:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{field_name}' cannot be set to null.",
            )

    for field_name, value in fields.items():
        setattr(offer, field_name, value)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_offer_constraint_message(exc),
        ) from None

    record_audit_log(
        db,
        organization_id=offer.organization_id,
        user_id=actor_user_id,
        action="offer.updated",
        resource_type="offer",
        resource_id=offer.id,
        old_value=old_value,
        new_value={
            "price": float(offer.price) if offer.price is not None else None,
            "availability": offer.availability.value,
            "stock_quantity": offer.stock_quantity,
        },
    )
    db.commit()
    db.refresh(offer)
    return offer


# --- Product Evidence ------------------------------------------------------


def list_product_evidence(
    db: Session,
    *,
    product_id: UUID,
    organization_id: UUID,
    verification_status: VerificationStatus | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[ProductEvidence], int]:
    get_product_or_404(db, product_id=product_id, organization_id=organization_id)
    base = select(ProductEvidence).where(
        ProductEvidence.product_id == product_id, ProductEvidence.organization_id == organization_id
    )
    if verification_status:
        base = base.where(ProductEvidence.verification_status == verification_status)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, ProductEvidence, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_product_evidence_or_404(db: Session, *, link_id: UUID, organization_id: UUID) -> ProductEvidence:
    return get_tenant_scoped_or_404(
        db, ProductEvidence, link_id, organization_id=organization_id,
        not_found_message="Product evidence link not found",
    )


def link_product_evidence(
    db: Session, *, product: Product, evidence_id: UUID, claim: str, actor_user_id: UUID
) -> ProductEvidence:
    # Two-hop: the evidence must belong to the caller's org too.
    get_evidence_or_404(db, evidence_id=evidence_id, organization_id=product.organization_id)

    link = ProductEvidence(
        organization_id=product.organization_id,
        product_id=product.id,
        evidence_id=evidence_id,
        claim=claim,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    db.add(link)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="This evidence is already linked to this product for this exact claim.",
        ) from None

    record_audit_log(
        db,
        organization_id=product.organization_id,
        user_id=actor_user_id,
        action="product_evidence.linked",
        resource_type="product_evidence",
        resource_id=link.id,
        new_value={"product_id": str(product.id), "evidence_id": str(evidence_id), "claim": claim},
    )
    db.commit()
    db.refresh(link)
    return link


def verify_product_evidence(
    db: Session,
    *,
    link: ProductEvidence,
    verification_status: VerificationStatus,
    note: str | None,
    actor_user_id: UUID,
) -> ProductEvidence:
    """The ONLY path to VERIFIED — see module docstring.

    **Two-layer verification invariant (ADR-032).** Verifying a link
    asserts "this evidence supports this claim about this product". It
    cannot be true unless the underlying Evidence row is itself
    VERIFIED — a DRAFT or REJECTED study cannot support anything. So
    this refuses to mark a link VERIFIED while its Evidence is not,
    rather than allowing the contradictory state
    (Evidence=REJECTED, ProductEvidence=VERIFIED) to exist at all.

    This write-time check is necessary but NOT sufficient on its own:
    Evidence can be rejected AFTER a link was verified. The read
    contract (`app/contracts/commerce.py`) therefore recomputes
    effective verification at read time, so a later revocation
    immediately stops counting. Both layers exist on purpose."""
    if verification_status == VerificationStatus.VERIFIED:
        evidence = db.get(Evidence, link.evidence_id)
        if evidence is None or evidence.status != EvidenceStatus.VERIFIED:
            current = evidence.status.value if evidence else "missing"
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Cannot mark this product-evidence link verified while the underlying "
                    f"Evidence record is '{current}' rather than 'verified'. Verify the "
                    "Evidence itself first."
                ),
            )

    old_status = link.verification_status
    link.verification_status = verification_status
    link.verified_at = _utcnow() if verification_status == VerificationStatus.VERIFIED else None

    db.flush()
    record_audit_log(
        db,
        organization_id=link.organization_id,
        user_id=actor_user_id,
        action="product_evidence.verification_changed",
        resource_type="product_evidence",
        resource_id=link.id,
        old_value={"verification_status": old_status.value},
        new_value={"verification_status": link.verification_status.value, "note": note},
    )
    db.commit()
    db.refresh(link)
    return link


# --- Product Relations -------------------------------------------------------


def list_product_relations(
    db: Session,
    *,
    product_id: UUID,
    organization_id: UUID,
    relation_type: ProductRelationType | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[ProductRelation], int]:
    get_product_or_404(db, product_id=product_id, organization_id=organization_id)
    base = select(ProductRelation).where(
        ProductRelation.product_id == product_id, ProductRelation.organization_id == organization_id
    )
    if relation_type:
        base = base.where(ProductRelation.relation_type == relation_type)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, ProductRelation, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def create_product_relation(
    db: Session,
    *,
    product: Product,
    related_product_id: UUID,
    relation_type: ProductRelationType,
    confidence: float | None,
    actor_user_id: UUID,
) -> ProductRelation:
    # Two-hop: the related product must belong to the caller's org too.
    get_product_or_404(db, product_id=related_product_id, organization_id=product.organization_id)

    if related_product_id == product.id:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A product cannot be related to itself.",
        )

    relation = ProductRelation(
        organization_id=product.organization_id,
        product_id=product.id,
        related_product_id=related_product_id,
        relation_type=relation_type,
        confidence=confidence,
    )
    db.add(relation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="This relation already exists between these two products.",
        ) from None

    record_audit_log(
        db,
        organization_id=product.organization_id,
        user_id=actor_user_id,
        action="product_relation.created",
        resource_type="product_relation",
        resource_id=relation.id,
        new_value={
            "product_id": str(product.id),
            "related_product_id": str(related_product_id),
            "relation_type": relation_type.value,
        },
    )
    db.commit()
    db.refresh(relation)
    return relation


# --- Trust Records ------------------------------------------------------------

_TRUST_SUBJECT_TO_MODEL = {
    TrustSubjectType.PRODUCT: Product,
    TrustSubjectType.CLAIM: Claim,
    TrustSubjectType.SITE: Site,
}


def _resolve_subject(db: Session, *, subject_type: TrustSubjectType, subject_id: UUID, organization_id: UUID) -> None:
    """Resolve + tenant-check the polymorphic subject pointer, the same
    way relationship_service and research_task_service do for theirs.
    ORGANIZATION is special-cased: the only organization a caller may
    make trust assertions about is their own, so the check is an
    identity comparison rather than a tenant-scoped lookup."""
    if subject_type == TrustSubjectType.ORGANIZATION:
        if subject_id != organization_id:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail="organization not found"
            )
        if db.get(Organization, subject_id) is None:  # pragma: no cover - defensive
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="organization not found")
        return

    model = _TRUST_SUBJECT_TO_MODEL[subject_type]
    get_tenant_scoped_or_404(
        db, model, subject_id, organization_id=organization_id,
        not_found_message=f"{subject_type.value} not found",
    )


def list_trust_records(
    db: Session,
    *,
    organization_id: UUID,
    subject_type: TrustSubjectType | None,
    subject_id: UUID | None,
    trust_type: TrustType | None,
    verification_status: VerificationStatus | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[TrustRecord], int]:
    base = select(TrustRecord).where(TrustRecord.organization_id == organization_id)
    if subject_type:
        base = base.where(TrustRecord.subject_type == subject_type)
    if subject_id:
        base = base.where(TrustRecord.subject_id == subject_id)
    if trust_type:
        base = base.where(TrustRecord.trust_type == trust_type)
    if verification_status:
        base = base.where(TrustRecord.verification_status == verification_status)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(apply_sort(base, TrustRecord, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_trust_record_or_404(db: Session, *, record_id: UUID, organization_id: UUID) -> TrustRecord:
    return get_tenant_scoped_or_404(
        db, TrustRecord, record_id, organization_id=organization_id, not_found_message="Trust record not found"
    )


def create_trust_record(
    db: Session,
    *,
    organization_id: UUID,
    subject_type: TrustSubjectType,
    subject_id: UUID,
    trust_type: TrustType,
    claim: str,
    evidence_id: UUID,
    actor_user_id: UUID,
) -> TrustRecord:
    _resolve_subject(db, subject_type=subject_type, subject_id=subject_id, organization_id=organization_id)
    get_evidence_or_404(db, evidence_id=evidence_id, organization_id=organization_id)

    record = TrustRecord(
        organization_id=organization_id,
        subject_type=subject_type,
        subject_id=subject_id,
        trust_type=trust_type,
        claim=claim,
        evidence_id=evidence_id,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    db.add(record)
    db.flush()

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="trust_record.created",
        resource_type="trust_record",
        resource_id=record.id,
        new_value={
            "subject_type": subject_type.value,
            "subject_id": str(subject_id),
            "trust_type": trust_type.value,
        },
    )
    db.commit()
    db.refresh(record)
    return record


def verify_trust_record(
    db: Session,
    *,
    record: TrustRecord,
    verification_status: VerificationStatus,
    note: str | None,
    actor_user_id: UUID,
) -> TrustRecord:
    """Same two-layer invariant as verify_product_evidence (ADR-032):
    a trust assertion cannot be verified on the strength of an
    unverified or rejected Evidence row. Section 30's "Trust must be
    evidence-backed" is meaningless if the backing evidence is itself
    rejected."""
    if verification_status == VerificationStatus.VERIFIED:
        evidence = db.get(Evidence, record.evidence_id)
        if evidence is None or evidence.status != EvidenceStatus.VERIFIED:
            current = evidence.status.value if evidence else "missing"
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Cannot mark this trust record verified while the underlying Evidence "
                    f"record is '{current}' rather than 'verified'. Verify the Evidence first."
                ),
            )

    old_status = record.verification_status
    record.verification_status = verification_status
    record.verified_at = _utcnow() if verification_status == VerificationStatus.VERIFIED else None

    db.flush()
    record_audit_log(
        db,
        organization_id=record.organization_id,
        user_id=actor_user_id,
        action="trust_record.verification_changed",
        resource_type="trust_record",
        resource_id=record.id,
        old_value={"verification_status": old_status.value},
        new_value={"verification_status": record.verification_status.value, "note": note},
    )
    db.commit()
    db.refresh(record)
    return record
