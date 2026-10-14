"""
Commerce mapping + sync job service (master spec §40/§41).

THE DIRECTIONAL RULE, which every function here obeys (ADR-050):

    WooCommerce may update an Offer's price/stock/availability.
    WooCommerce may NOT update a Product's identity, status, evidence,
    trust, or any recommendation.

This is not a convention — it is the shape of the API. There is no
parameter on any function in this module that can reach Product.name,
Product.status, ProductEvidence, TrustRecord or Recommendation. A
WooCommerce adapter cannot publish a product or verify a claim because the
code path does not exist, which is a stronger guarantee than a permission
check.

Idempotency is structural in two layers: the unique constraints on
`commerce_mappings` make duplicate mappings impossible, and
`idempotency_key` on `sync_jobs` makes duplicate job enqueueing impossible.
A webhook delivered five times therefore produces one mapping and one job
regardless of what the handler remembers to check.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.commerce_mapping import CommerceMapping
from app.models.enums import (
    CommerceSyncStatus,
    OfferAvailability,
    SyncJobStatus,
    SyncJobType,
)
from app.models.offer import Offer
from app.models.sync_job import SyncJob
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.product_service import get_product_or_404

# A job that has failed this many times stops being retried and becomes
# visible as DEAD_LETTER. Documented constant, not a magic number: the
# point is that "stopped trying" is distinguishable from "will try again".
MAX_ATTEMPTS = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Commerce mappings ----------------------------------------------------


def upsert_commerce_mapping(
    db: Session,
    *,
    organization_id: UUID,
    site_id: UUID,
    installation_id: UUID | None,
    product_id: UUID,
    woo_product_id: int,
    woo_variation_id: int | None,
    sku: str | None,
    actor_user_id: UUID | None,
) -> tuple[CommerceMapping, bool]:
    """Returns (mapping, created). Idempotent by database constraint."""
    # Tenant-check the Core product before writing anything.
    get_product_or_404(db, product_id=product_id, organization_id=organization_id)

    existing = db.execute(
        select(CommerceMapping).where(
            CommerceMapping.organization_id == organization_id,
            CommerceMapping.site_id == site_id,
            CommerceMapping.woo_product_id == woo_product_id,
            CommerceMapping.woo_variation_id.is_(None)
            if woo_variation_id is None
            else CommerceMapping.woo_variation_id == woo_variation_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.product_id != product_id:
            # Re-pointing a Woo product at a DIFFERENT Core product is not a
            # sync event, it is a decision. Silently rewriting it would move
            # a merchant's evidence and trust history onto another product.
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail=(
                    f"WooCommerce product {woo_product_id} is already mapped to a different "
                    "Cloud Core product on this site. Remove the existing mapping before "
                    "re-pointing it."
                ),
            )
        existing.sku = sku or existing.sku
        existing.installation_id = installation_id or existing.installation_id
        existing.sync_status = CommerceSyncStatus.SYNCED
        existing.last_synced_at = _utcnow()
        existing.last_error = None
        db.commit()
        db.refresh(existing)
        return existing, False

    mapping = CommerceMapping(
        organization_id=organization_id,
        site_id=site_id,
        product_id=product_id,
        installation_id=installation_id,
        woo_product_id=woo_product_id,
        woo_variation_id=woo_variation_id,
        sku=sku,
        sync_status=CommerceSyncStatus.SYNCED,
        last_synced_at=_utcnow(),
    )
    db.add(mapping)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        concurrent = db.execute(
            select(CommerceMapping).where(
                CommerceMapping.organization_id == organization_id,
                CommerceMapping.site_id == site_id,
                CommerceMapping.woo_product_id == woo_product_id,
            )
        ).scalar_one_or_none()
        if concurrent is not None:
            return concurrent, False
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="This WooCommerce product is already mapped on this site.",
        ) from None

    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="commerce_mapping.created", resource_type="commerce_mapping",
        resource_id=mapping.id,
        new_value={"product_id": str(product_id), "woo_product_id": woo_product_id},
    )
    db.commit()
    db.refresh(mapping)
    return mapping, True


def list_commerce_mappings(
    db: Session, *, organization_id: UUID, site_id: UUID | None,
    sync_status: CommerceSyncStatus | None, limit: int, offset: int,
    sort: SortParams | None = None,
) -> tuple[list[CommerceMapping], int]:
    base = select(CommerceMapping).where(CommerceMapping.organization_id == organization_id)
    if site_id:
        base = base.where(CommerceMapping.site_id == site_id)
    if sync_status:
        base = base.where(CommerceMapping.sync_status == sync_status)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        apply_sort(base, CommerceMapping, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)
    ).scalars().all()
    return list(rows), total


def get_commerce_mapping_or_404(db: Session, *, mapping_id: UUID, organization_id: UUID) -> CommerceMapping:
    return get_tenant_scoped_or_404(
        db, CommerceMapping, mapping_id, organization_id=organization_id,
        not_found_message="Commerce mapping not found",
    )


# --- Offer sync (the ONLY Core data WooCommerce may change) ------------------


def apply_offer_sync(
    db: Session,
    *,
    mapping: CommerceMapping,
    price: float | None,
    currency: str | None,
    availability: OfferAvailability,
    stock_quantity: int | None,
    external_id: str | None,
    actor_user_id: UUID | None,
) -> Offer:
    """Updates or creates the Offer for a mapped product.

    **This is the entire surface through which WooCommerce may change Core
    data.** Note what it cannot touch: the Product it belongs to, its status,
    its evidence, its trust records. §27's Product/Offer separation is what
    makes that containment possible — if price lived on Product, a price
    sync would necessarily be a write to the product record.

    `stock_quantity=None` is preserved as "untracked", never coerced to 0
    (Phase 7's distinction, carried through Phase 8's scoring and Phase 9's
    schema rendering; breaking it here would undo all three).
    """
    offer = db.execute(
        select(Offer).where(
            Offer.organization_id == mapping.organization_id,
            Offer.product_id == mapping.product_id,
            Offer.external_id == (external_id or f"woo:{mapping.woo_product_id}"),
        )
    ).scalar_one_or_none()

    resolved_external_id = external_id or f"woo:{mapping.woo_product_id}"
    created = offer is None

    if offer is None:
        offer = Offer(
            organization_id=mapping.organization_id,
            product_id=mapping.product_id,
            external_id=resolved_external_id,
        )
        db.add(offer)

    offer.price = price
    offer.currency = currency
    offer.availability = availability
    offer.stock_quantity = stock_quantity

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Offer rejected by a database constraint: {exc.__class__.__name__}",
        ) from None

    mapping.sync_status = CommerceSyncStatus.SYNCED
    mapping.last_synced_at = _utcnow()
    mapping.last_error = None

    record_audit_log(
        db, organization_id=mapping.organization_id, user_id=actor_user_id,
        action="commerce_offer.synced" if not created else "commerce_offer.created",
        resource_type="offer", resource_id=offer.id,
        new_value={
            "price": float(price) if price is not None else None,
            "availability": availability.value,
            "stock_quantity": stock_quantity,
            "source": "woocommerce",
        },
    )
    db.commit()
    db.refresh(offer)
    return offer


# --- Sync jobs ---------------------------------------------------------------


def enqueue_job(
    db: Session,
    *,
    organization_id: UUID,
    site_id: UUID | None,
    job_type: SyncJobType,
    payload: dict,
    idempotency_key: str | None,
    actor_user_id: UUID | None,
) -> tuple[SyncJob, bool]:
    """Returns (job, created). A repeated idempotency key returns the
    existing job rather than creating a second one — enforced by a unique
    constraint, so concurrent duplicates lose the race rather than both
    succeeding."""
    if idempotency_key:
        existing = db.execute(
            select(SyncJob).where(
                SyncJob.organization_id == organization_id,
                SyncJob.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False

    job = SyncJob(
        organization_id=organization_id,
        site_id=site_id,
        job_type=job_type,
        status=SyncJobStatus.QUEUED,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(SyncJob).where(
                SyncJob.organization_id == organization_id,
                SyncJob.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False
        raise

    record_audit_log(
        db, organization_id=organization_id, user_id=actor_user_id,
        action="sync_job.enqueued", resource_type="sync_job", resource_id=job.id,
        new_value={"job_type": job_type.value},
    )
    db.commit()
    db.refresh(job)
    return job, True


def mark_running(db: Session, *, job: SyncJob) -> SyncJob:
    job.status = SyncJobStatus.RUNNING
    job.attempts += 1
    job.started_at = _utcnow()
    db.commit()
    db.refresh(job)
    return job


def mark_succeeded(db: Session, *, job: SyncJob) -> SyncJob:
    job.status = SyncJobStatus.SUCCEEDED
    job.completed_at = _utcnow()
    job.error_message = None
    db.commit()
    db.refresh(job)
    return job


def mark_failed(db: Session, *, job: SyncJob, error: str) -> SyncJob:
    """A job that has exhausted MAX_ATTEMPTS becomes DEAD_LETTER rather than
    staying FAILED. The distinction is the whole point: FAILED means "will
    be retried", DEAD_LETTER means "stopped trying, a human is needed".
    Without it an operator cannot tell which jobs still have hope."""
    job.error_message = error[:1000]
    job.completed_at = _utcnow()
    job.status = (
        SyncJobStatus.DEAD_LETTER if job.attempts >= MAX_ATTEMPTS else SyncJobStatus.FAILED
    )
    db.commit()
    db.refresh(job)
    return job


def list_jobs(
    db: Session, *, organization_id: UUID, status: SyncJobStatus | None,
    job_type: SyncJobType | None, limit: int, offset: int,
    sort: SortParams | None = None,
) -> tuple[list[SyncJob], int]:
    base = select(SyncJob).where(SyncJob.organization_id == organization_id)
    if status:
        base = base.where(SyncJob.status == status)
    if job_type:
        base = base.where(SyncJob.job_type == job_type)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(apply_sort(base, SyncJob, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_job_or_404(db: Session, *, job_id: UUID, organization_id: UUID) -> SyncJob:
    return get_tenant_scoped_or_404(
        db, SyncJob, job_id, organization_id=organization_id, not_found_message="Sync job not found"
    )
