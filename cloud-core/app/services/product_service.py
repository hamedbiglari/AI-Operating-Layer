"""
Product service (master spec section 26).

Cross-resource references (`site_id`, `knowledge_object_id`) are each
resolved through their own existing tenant-scoped getter before a
Product row is written — the same two-hop discipline established for
Document->Source (Phase 3), Evidence->Source/Document (Phase 4),
ResearchTask->Project (Phase 5) and QueryGroup->Entity (Phase 6). A
merchant can never attach their product to another organization's site
or knowledge object.

`status` changes only via `change_product_status`, never via a plain
field edit — a Product is "a normalized Product Knowledge Object"
(section 26), so it inherits KnowledgeObject's never-auto-publish
discipline (section 44). The transition table below is deliberately
permissive in one direction only: anything can be ARCHIVED, and an
archived product can be revived to DRAFT, but nothing jumps straight
to PUBLISHED without passing through a review state.
"""

from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import ProductStatus
from app.models.product import Product
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log
from app.services.knowledge_service import get_knowledge_object_or_404
from app.services.site_service import get_site_or_404


class InvalidProductStatusTransitionError(Exception):
    """Raised when a requested status change is not in _VALID_TRANSITIONS."""


_VALID_TRANSITIONS: dict[ProductStatus, frozenset[ProductStatus]] = {
    ProductStatus.DRAFT: frozenset({ProductStatus.IN_REVIEW, ProductStatus.ARCHIVED}),
    ProductStatus.IN_REVIEW: frozenset(
        {ProductStatus.PUBLISHED, ProductStatus.DRAFT, ProductStatus.ARCHIVED}
    ),
    ProductStatus.PUBLISHED: frozenset({ProductStatus.IN_REVIEW, ProductStatus.ARCHIVED}),
    ProductStatus.ARCHIVED: frozenset({ProductStatus.DRAFT}),
}

# Columns a client may edit but may NOT null out, because they are
# NOT NULL in the schema. An explicit `{"name": null}` is a client
# error worth a clear 422, not a raw IntegrityError from the database.
# Every other updatable field is genuinely nullable and an explicit
# null legitimately clears it.
_NON_NULLABLE_UPDATABLE_FIELDS = frozenset(
    {"name", "ingredients", "specifications", "certifications", "images", "shipping"}
)


def _validate_references(
    db: Session, *, organization_id: UUID, site_id: UUID | None, knowledge_object_id: UUID | None
) -> None:
    if site_id is not None:
        get_site_or_404(db, site_id=site_id, organization_id=organization_id)
    if knowledge_object_id is not None:
        get_knowledge_object_or_404(db, object_id=knowledge_object_id, organization_id=organization_id)


def list_products(
    db: Session,
    *,
    organization_id: UUID,
    status_filter: ProductStatus | None,
    category: str | None,
    brand: str | None,
    knowledge_object_id: UUID | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Product], int]:
    base = select(Product).where(Product.organization_id == organization_id)
    if status_filter:
        base = base.where(Product.status == status_filter)
    if category:
        base = base.where(Product.category == category)
    if brand:
        base = base.where(Product.brand == brand)
    if knowledge_object_id:
        base = base.where(Product.knowledge_object_id == knowledge_object_id)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(apply_sort(base, Product, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_product_or_404(db: Session, *, product_id: UUID, organization_id: UUID) -> Product:
    return get_tenant_scoped_or_404(
        db, Product, product_id, organization_id=organization_id, not_found_message="Product not found"
    )


def create_product(db: Session, *, organization_id: UUID, actor_user_id: UUID, **fields) -> Product:
    _validate_references(
        db,
        organization_id=organization_id,
        site_id=fields.get("site_id"),
        knowledge_object_id=fields.get("knowledge_object_id"),
    )

    product = Product(organization_id=organization_id, status=ProductStatus.DRAFT, **fields)
    db.add(product)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="A product with this sku or slug already exists in your organization.",
        ) from None

    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="product.created",
        resource_type="product",
        resource_id=product.id,
        new_value={"name": product.name, "slug": product.slug, "status": product.status.value},
    )
    db.commit()
    db.refresh(product)
    return product


def update_product(db: Session, *, product: Product, actor_user_id: UUID, **fields) -> Product:
    """`fields` comes from `ProductUpdate.model_dump(exclude_unset=True)`,
    so a key is present ONLY if the client actually sent it. That makes
    the two cases genuinely distinguishable, and they are treated
    differently on purpose:

        PATCH {}                  -> field absent  -> unchanged
        PATCH {"origin": null}    -> field present -> cleared to NULL

    An earlier revision skipped every None value, which silently made
    "clear this field" impossible — a caller asking to erase `origin`
    got a 200 and no change. Now an explicit null clears the column,
    and an explicit null on a NOT NULL column is rejected loudly
    instead of failing later as a raw database error."""
    old_value = {"name": product.name, "category": product.category}

    for field_name, value in fields.items():
        if value is None and field_name in _NON_NULLABLE_UPDATABLE_FIELDS:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{field_name}' cannot be set to null.",
            )

    if fields.get("knowledge_object_id") is not None:
        _validate_references(
            db,
            organization_id=product.organization_id,
            site_id=None,
            knowledge_object_id=fields["knowledge_object_id"],
        )

    for field_name, value in fields.items():
        setattr(product, field_name, value)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="This update conflicts with an existing product (duplicate sku or slug).",
        ) from None

    record_audit_log(
        db,
        organization_id=product.organization_id,
        user_id=actor_user_id,
        action="product.updated",
        resource_type="product",
        resource_id=product.id,
        old_value=old_value,
        new_value={"name": product.name, "category": product.category},
    )
    db.commit()
    db.refresh(product)
    return product


def change_product_status(
    db: Session, *, product: Product, new_status: ProductStatus, actor_user_id: UUID
) -> Product:
    allowed = _VALID_TRANSITIONS.get(product.status, frozenset())
    if new_status not in allowed:
        raise InvalidProductStatusTransitionError(
            f"Cannot transition product from '{product.status.value}' to '{new_status.value}'. "
            f"Valid transitions from '{product.status.value}': "
            f"{sorted(s.value for s in allowed) or 'none'}."
        )

    old_status = product.status
    product.status = new_status

    db.flush()
    record_audit_log(
        db,
        organization_id=product.organization_id,
        user_id=actor_user_id,
        action="product.status_changed",
        resource_type="product",
        resource_id=product.id,
        old_value={"status": old_status.value},
        new_value={"status": product.status.value},
    )
    db.commit()
    db.refresh(product)
    return product
