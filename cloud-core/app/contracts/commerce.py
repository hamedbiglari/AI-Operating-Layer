"""
Commerce/Product domain — READ CONTRACT.

**Owned by the Commerce domain (Phase 7).** Consumed by the
Recommendation domain (Phase 8). If Phase 7's internal storage changes,
this module absorbs the change; consumers do not.

Why this exists: before Phase 8, every domain only ever read its own
tables, so direct `select(Model)` was harmless. Recommendation is the
first genuinely cross-domain consumer - it needs Product, Offer,
ProductEvidence and TrustRecord at once. Letting it query those tables
directly would mean any Phase 7 schema change silently breaks Phase 8,
and would put Commerce business rules (what counts as purchasable,
what counts as verified) inside Recommendation, where they do not
belong.

The read models below are **intentionally narrower than the ORM
models**. They expose what a consumer legitimately needs to make a
decision, not every column. Adding a field to Product does not require
touching this file unless consumers actually need the new field -
which is exactly the additive-evolution property the Phase 8 brief's
Scenario A and B ask for.

Two Commerce business rules live here rather than in the consumer,
deliberately:

- **What counts as recommendable** (`ProductReadModel.is_recommendable`)
  - only PUBLISHED products. DRAFT and IN_REVIEW are unreviewed
  content; ARCHIVED is retired. This is a Commerce judgment about its
  own lifecycle, not a Recommendation preference.
- **What counts as EFFECTIVELY verified evidence/trust** - a link is
  only counted as verified when BOTH its own `verification_status` and
  the underlying `Evidence.status` are VERIFIED (ADR-032). This is
  computed at READ time, not trusted from a stored flag, precisely so
  that revoking an Evidence row after a link was verified immediately
  stops that link counting - a write-time check alone cannot catch
  that, because the revocation happens later.
- **What counts as purchasable** (`OfferReadModel.is_purchasable`) -
  an offer that is in stock (or preorder/backorder) and within its
  validity window. Note `stock_quantity is None` means UNTRACKED, not
  zero: an in-stock offer with untracked quantity IS purchasable.
  Collapsing those would silently hide every merchant who doesn't
  count units.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    EvidenceStatus,
    OfferAvailability,
    ProductStatus,
    TrustSubjectType,
    TrustType,
    VerificationStatus,
)
from app.models.evidence import Evidence
from app.models.offer import Offer
from app.models.product import Product
from app.models.product_evidence import ProductEvidence
from app.models.product_relation import ProductRelation
from app.models.trust_record import TrustRecord

# Availability values that still permit a purchase decision. OUT_OF_STOCK
# and DISCONTINUED do not; PREORDER and BACKORDER do, because a customer
# can still commit to buying - whether that is APPROPRIATE for a given
# response mode is a Recommendation policy question, not a Commerce one.
_PURCHASABLE_AVAILABILITY = frozenset(
    {OfferAvailability.IN_STOCK, OfferAvailability.PREORDER, OfferAvailability.BACKORDER}
)


@dataclass(frozen=True)
class ProductReadModel:
    id: UUID
    organization_id: UUID
    name: str
    slug: str
    brand: str | None
    category: str | None
    origin: str | None
    status: ProductStatus
    knowledge_object_id: UUID | None

    @property
    def is_recommendable(self) -> bool:
        """Commerce's own rule about its own lifecycle - see module
        docstring."""
        return self.status == ProductStatus.PUBLISHED


@dataclass(frozen=True)
class OfferReadModel:
    id: UUID
    product_id: UUID
    price: float | None
    currency: str | None
    availability: OfferAvailability
    stock_quantity: int | None
    valid_from: datetime | None
    valid_until: datetime | None

    @property
    def has_known_price(self) -> bool:
        """`price is None` means "price on request", NOT free. A
        consumer must never treat a missing price as 0."""
        return self.price is not None

    def is_purchasable(self, *, at: datetime | None = None) -> bool:
        now = at or datetime.now(timezone.utc)
        if self.availability not in _PURCHASABLE_AVAILABILITY:
            return False
        if self.valid_from is not None and now < self.valid_from:
            return False
        if self.valid_until is not None and now > self.valid_until:
            return False
        # stock_quantity is None => untracked, which does NOT mean zero.
        if self.stock_quantity is not None and self.stock_quantity <= 0:
            return False
        return True


@dataclass(frozen=True)
class ProductEvidenceSummary:
    """Counts by verification status, never raw evidence rows.

    A consumer must be able to tell "nothing established yet"
    (everything zero) from "claims exist and were rejected"
    (`rejected` > 0) - those are different facts that a single
    "evidence count" would destroy."""

    product_id: UUID
    verified: int = 0
    pending_review: int = 0
    unverified: int = 0
    rejected: int = 0
    verified_claims: list[str] = field(default_factory=list)

    @property
    def has_any_record(self) -> bool:
        return bool(self.verified or self.pending_review or self.unverified or self.rejected)


@dataclass(frozen=True)
class TrustSummary:
    """Same discipline as ProductEvidenceSummary: absence and rejection
    are different facts and must stay distinguishable."""

    subject_id: UUID
    verified: int = 0
    pending_review: int = 0
    unverified: int = 0
    rejected: int = 0
    verified_trust_types: list[TrustType] = field(default_factory=list)

    @property
    def has_any_record(self) -> bool:
        return bool(self.verified or self.pending_review or self.unverified or self.rejected)


def _to_product_read_model(product: Product) -> ProductReadModel:
    return ProductReadModel(
        id=product.id,
        organization_id=product.organization_id,
        name=product.name,
        slug=product.slug,
        brand=product.brand,
        category=product.category,
        origin=product.origin,
        status=product.status,
        knowledge_object_id=product.knowledge_object_id,
    )


def _to_offer_read_model(offer: Offer) -> OfferReadModel:
    return OfferReadModel(
        id=offer.id,
        product_id=offer.product_id,
        price=float(offer.price) if offer.price is not None else None,
        currency=offer.currency,
        availability=offer.availability,
        stock_quantity=offer.stock_quantity,
        valid_from=offer.valid_from,
        valid_until=offer.valid_until,
    )


def find_candidate_products(
    db: Session,
    *,
    organization_id: UUID,
    category: str | None = None,
    brand: str | None = None,
    knowledge_object_id: UUID | None = None,
    product_ids: list[UUID] | None = None,
    include_non_recommendable: bool = False,
    limit: int = 100,
) -> list[ProductReadModel]:
    """Every query is organization-scoped at the source. A consumer
    cannot accidentally widen this - there is no parameter that turns
    tenant scoping off.

    `include_non_recommendable` exists so a consumer can ASK for
    non-published products and then reject them with a visible,
    explainable gate, rather than them silently never appearing. The
    default is the safe one."""
    stmt = select(Product).where(Product.organization_id == organization_id)
    if not include_non_recommendable:
        stmt = stmt.where(Product.status == ProductStatus.PUBLISHED)
    if category:
        stmt = stmt.where(Product.category == category)
    if brand:
        stmt = stmt.where(Product.brand == brand)
    if knowledge_object_id:
        stmt = stmt.where(Product.knowledge_object_id == knowledge_object_id)
    if product_ids is not None:
        if not product_ids:
            return []
        stmt = stmt.where(Product.id.in_(product_ids))

    rows = db.execute(stmt.order_by(Product.created_at.desc()).limit(limit)).scalars().all()
    return [_to_product_read_model(p) for p in rows]


def get_product(db: Session, *, product_id: UUID, organization_id: UUID) -> ProductReadModel | None:
    product = db.execute(
        select(Product).where(Product.id == product_id, Product.organization_id == organization_id)
    ).scalar_one_or_none()
    return _to_product_read_model(product) if product else None


def get_offers_for_products(
    db: Session, *, product_ids: list[UUID], organization_id: UUID
) -> dict[UUID, list[OfferReadModel]]:
    """Batched on purpose: the recommendation pipeline evaluates many
    products at once, and a per-product call would be N+1."""
    if not product_ids:
        return {}
    rows = db.execute(
        select(Offer).where(
            Offer.organization_id == organization_id, Offer.product_id.in_(product_ids)
        )
    ).scalars().all()

    grouped: dict[UUID, list[OfferReadModel]] = {pid: [] for pid in product_ids}
    for offer in rows:
        grouped.setdefault(offer.product_id, []).append(_to_offer_read_model(offer))
    return grouped


def get_evidence_summaries(
    db: Session, *, product_ids: list[UUID], organization_id: UUID
) -> dict[UUID, ProductEvidenceSummary]:
    """Counts EFFECTIVE verification, not the link's own flag alone.

    A link counts as verified only when its own `verification_status`
    is VERIFIED **and** the Evidence it points at is VERIFIED too
    (ADR-032). A link whose Evidence was rejected after the link was
    verified is counted as `rejected`, not `verified` - which is the
    honest reading, and is why this is computed here rather than read
    from a stored flag."""
    if not product_ids:
        return {}
    rows = db.execute(
        select(ProductEvidence, Evidence.status)
        .join(Evidence, ProductEvidence.evidence_id == Evidence.id)
        .where(
            ProductEvidence.organization_id == organization_id,
            ProductEvidence.product_id.in_(product_ids),
        )
    ).all()

    counters: dict[UUID, dict] = {
        pid: {"verified": 0, "pending_review": 0, "unverified": 0, "rejected": 0, "claims": []}
        for pid in product_ids
    }
    for link, evidence_status in rows:
        bucket = counters.setdefault(
            link.product_id,
            {"verified": 0, "pending_review": 0, "unverified": 0, "rejected": 0, "claims": []},
        )
        link_status = link.verification_status

        # Either side being rejected makes the whole assertion rejected:
        # a rejected study cannot support a claim, and a rejected claim
        # is not rescued by a good study.
        if (
            link_status == VerificationStatus.REJECTED
            or evidence_status == EvidenceStatus.REJECTED
        ):
            bucket["rejected"] += 1
        elif (
            link_status == VerificationStatus.VERIFIED
            and evidence_status == EvidenceStatus.VERIFIED
        ):
            bucket["verified"] += 1
            bucket["claims"].append(link.claim)
        elif link_status == VerificationStatus.PENDING_REVIEW:
            bucket["pending_review"] += 1
        else:
            # Includes the "link verified, evidence still draft" case -
            # genuinely not established yet, and deliberately NOT
            # counted as verified.
            bucket["unverified"] += 1

    return {
        pid: ProductEvidenceSummary(
            product_id=pid,
            verified=c["verified"],
            pending_review=c["pending_review"],
            unverified=c["unverified"],
            rejected=c["rejected"],
            verified_claims=c["claims"],
        )
        for pid, c in counters.items()
    }


def get_trust_summaries(
    db: Session, *, subject_ids: list[UUID], organization_id: UUID
) -> dict[UUID, TrustSummary]:
    """PRODUCT trust only, and the same effective-verification rule as
    get_evidence_summaries (ADR-032): a trust record counts as verified
    only when it AND its Evidence are both VERIFIED."""
    if not subject_ids:
        return {}
    # subject_type is filtered explicitly (B5). Filtering on
    # subject_id alone relied on UUID collisions being improbable -
    # true, but improbability is not a semantic contract. A caller
    # asking for "trust for these products" must not receive a Claim's
    # trust record that happens to share an id.
    rows = db.execute(
        select(TrustRecord, Evidence.status)
        .join(Evidence, TrustRecord.evidence_id == Evidence.id)
        .where(
            TrustRecord.organization_id == organization_id,
            TrustRecord.subject_type == TrustSubjectType.PRODUCT,
            TrustRecord.subject_id.in_(subject_ids),
        )
    ).all()

    counters: dict[UUID, dict] = {
        sid: {"verified": 0, "pending_review": 0, "unverified": 0, "rejected": 0, "types": []}
        for sid in subject_ids
    }
    for record, evidence_status in rows:
        bucket = counters.setdefault(
            record.subject_id,
            {"verified": 0, "pending_review": 0, "unverified": 0, "rejected": 0, "types": []},
        )
        record_status = record.verification_status

        if (
            record_status == VerificationStatus.REJECTED
            or evidence_status == EvidenceStatus.REJECTED
        ):
            bucket["rejected"] += 1
        elif (
            record_status == VerificationStatus.VERIFIED
            and evidence_status == EvidenceStatus.VERIFIED
        ):
            bucket["verified"] += 1
            bucket["types"].append(record.trust_type)
        elif record_status == VerificationStatus.PENDING_REVIEW:
            bucket["pending_review"] += 1
        else:
            bucket["unverified"] += 1

    return {
        sid: TrustSummary(
            subject_id=sid,
            verified=c["verified"],
            pending_review=c["pending_review"],
            unverified=c["unverified"],
            rejected=c["rejected"],
            verified_trust_types=c["types"],
        )
        for sid, c in counters.items()
    }


def get_related_product_ids(
    db: Session, *, product_id: UUID, organization_id: UUID
) -> list[UUID]:
    rows = db.execute(
        select(ProductRelation.related_product_id).where(
            ProductRelation.organization_id == organization_id,
            ProductRelation.product_id == product_id,
        )
    ).scalars().all()
    return list(rows)
