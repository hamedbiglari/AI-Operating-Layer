"""Pydantic contracts for Phase 7 (Commerce & Product Knowledge)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    OfferAvailability,
    OfferCondition,
    ProductProvenance,
    ProductRelationType,
    ProductStatus,
    TrustSubjectType,
    TrustType,
    VerificationStatus,
)


# --- Product -------------------------------------------------------------


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID | None
    external_id: str | None
    sku: str | None
    name: str
    slug: str
    description: str | None
    brand: str | None
    category: str | None
    origin: str | None
    ingredients: dict
    specifications: dict
    certifications: dict
    images: dict
    shipping: dict
    returns_policy: str | None
    status: ProductStatus
    provenance: ProductProvenance
    knowledge_object_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    slug: str = Field(min_length=1, max_length=500)
    site_id: uuid.UUID | None = None
    external_id: str | None = Field(default=None, max_length=255)
    sku: str | None = Field(default=None, max_length=120)
    description: str | None = None
    brand: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=255)
    origin: str | None = Field(default=None, max_length=255)
    ingredients: dict = Field(default_factory=dict)
    specifications: dict = Field(default_factory=dict)
    certifications: dict = Field(default_factory=dict)
    images: dict = Field(default_factory=dict)
    shipping: dict = Field(default_factory=dict)
    returns_policy: str | None = None
    provenance: ProductProvenance = ProductProvenance.MERCHANT
    knowledge_object_id: uuid.UUID | None = None


class ProductUpdate(BaseModel):
    """Plain field edits. `status` is deliberately absent — publication
    goes through the dedicated `/products/{id}/status` action, the same
    review/status split every other reviewable resource in this
    codebase uses (a field edit must never silently publish).

    Explicit-null semantics: an omitted key leaves the column alone; an
    explicit `null` CLEARS it (e.g. `{"origin": null}` erases the
    origin). Nulling a NOT NULL column such as `name` returns 422. See
    product_service.update_product."""

    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    brand: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=255)
    origin: str | None = Field(default=None, max_length=255)
    ingredients: dict | None = None
    specifications: dict | None = None
    certifications: dict | None = None
    images: dict | None = None
    shipping: dict | None = None
    returns_policy: str | None = None
    knowledge_object_id: uuid.UUID | None = None


class ProductStatusChangeRequest(BaseModel):
    status: ProductStatus


# --- Offer ---------------------------------------------------------------


class OfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    product_id: uuid.UUID
    external_id: str | None
    price: float | None
    currency: str | None
    availability: OfferAvailability
    stock_quantity: int | None
    condition: OfferCondition
    url: str | None
    valid_from: datetime | None
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime


class OfferCreate(BaseModel):
    external_id: str | None = Field(default=None, max_length=255)
    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    availability: OfferAvailability = OfferAvailability.IN_STOCK
    stock_quantity: int | None = Field(default=None, ge=0)
    condition: OfferCondition = OfferCondition.NEW
    url: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class OfferUpdate(BaseModel):
    """Every mutable Offer column is editable here (an earlier revision
    omitted external_id/condition/valid_from, which made those
    write-once by accident).

    Explicit-null semantics: an omitted key leaves the column alone; an
    explicit `null` CLEARS it. `{"price": null}` is how a merchant
    moves an offer to "price on request" — see
    commerce_service.update_offer. Nulling a NOT NULL column
    (`availability`, `condition`) returns 422 rather than a raw
    database error."""

    external_id: str | None = Field(default=None, max_length=255)
    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    availability: OfferAvailability | None = None
    stock_quantity: int | None = Field(default=None, ge=0)
    condition: OfferCondition | None = None
    url: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


# --- ProductEvidence -------------------------------------------------------


class ProductEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    product_id: uuid.UUID
    evidence_id: uuid.UUID
    claim: str
    verification_status: VerificationStatus
    verified_at: datetime | None
    created_at: datetime


class ProductEvidenceCreate(BaseModel):
    """`claim` is required and has no default — it is what scopes the
    evidence to a specific assertion about this product (see
    app/models/product_evidence.py's module docstring). A link with no
    stated claim would be exactly the unscoped inheritance the master
    spec forbids, so the API cannot express one."""

    evidence_id: uuid.UUID
    claim: str = Field(min_length=1)


class ProductEvidenceVerifyRequest(BaseModel):
    verification_status: VerificationStatus
    note: str | None = Field(default=None, max_length=2000)


# --- ProductRelation --------------------------------------------------------


class ProductRelationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    product_id: uuid.UUID
    related_product_id: uuid.UUID
    relation_type: ProductRelationType
    confidence: float | None
    created_at: datetime


class ProductRelationCreate(BaseModel):
    related_product_id: uuid.UUID
    relation_type: ProductRelationType
    confidence: float | None = Field(default=None, ge=0, le=1)


# --- TrustRecord ------------------------------------------------------------


class TrustRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    subject_type: TrustSubjectType
    subject_id: uuid.UUID
    trust_type: TrustType
    claim: str
    evidence_id: uuid.UUID
    verification_status: VerificationStatus
    verified_at: datetime | None
    created_at: datetime


class TrustRecordCreate(BaseModel):
    """`evidence_id` is required, never optional — section 30's "Trust
    must be evidence-backed" is enforced at the schema, model, and
    database level alike, so a trust assertion with no evidence cannot
    be expressed at any layer."""

    subject_type: TrustSubjectType
    subject_id: uuid.UUID
    trust_type: TrustType
    claim: str = Field(min_length=1)
    evidence_id: uuid.UUID


class TrustRecordVerifyRequest(BaseModel):
    verification_status: VerificationStatus
    note: str | None = Field(default=None, max_length=2000)
