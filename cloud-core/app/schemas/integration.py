"""Pydantic contracts for machine identity and adapter mappings.

Note what these schemas deliberately do NOT contain: no
`organization_id` on any request model. Tenant identity is derived from
the authenticated credential and is never accepted from a client
(ADR-036)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AdapterScope,
    CommerceSyncStatus,
    OfferAvailability,
    ProductStatus,
    SyncJobStatus,
    SyncJobType,
    AdapterType,
    CredentialStatus,
    InstallationStatus,
    MappedObjectType,
    SyncStatus,
)


class InstallationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID | None
    name: str
    adapter_type: AdapterType
    status: InstallationStatus
    external_url: str | None
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InstallationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    adapter_type: AdapterType = AdapterType.WORDPRESS
    site_id: uuid.UUID | None = None
    external_url: str | None = None


class InstallationStatusChange(BaseModel):
    status: InstallationStatus


class CredentialRead(BaseModel):
    """Never contains the secret — only the public `key_id`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    installation_id: uuid.UUID
    key_id: str
    scopes: list[str]
    status: CredentialStatus
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class CredentialIssueRequest(BaseModel):
    scopes: list[AdapterScope] = Field(min_length=1)
    expires_at: datetime | None = None


class CredentialIssueResponse(BaseModel):
    """`token` is returned exactly once and cannot be recovered
    afterwards — the secret is stored only as a bcrypt hash."""

    credential: CredentialRead
    token: str
    warning: str = "Store this token now. It cannot be retrieved again."


class MappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID
    installation_id: uuid.UUID | None
    object_type: MappedObjectType
    object_id: uuid.UUID
    wordpress_post_id: int
    wordpress_post_type: str | None
    wordpress_url: str | None
    sync_status: SyncStatus
    last_synced_at: datetime | None
    remote_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MappingUpsertRequest(BaseModel):
    """No `organization_id` and no `site_id` when called by an adapter —
    both come from the authenticated installation."""

    object_type: MappedObjectType
    object_id: uuid.UUID
    wordpress_post_id: int = Field(ge=1)
    wordpress_post_type: str | None = Field(default=None, max_length=100)
    wordpress_url: str | None = None
    remote_updated_at: datetime | None = None


class MappingUpsertResponse(BaseModel):
    mapping: MappingRead
    created: bool


class AdapterIdentityResponse(BaseModel):
    """What an adapter is allowed to know about itself. Deliberately
    minimal — it confirms identity and capability, nothing more."""

    installation_id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID | None
    adapter_type: str
    scopes: list[str]


class AdapterOfferProjection(BaseModel):
    """One purchasable offer, projected for an adapter.

    `price=None` means "on request" and MUST NOT be rendered as 0 by any
    consumer — the distinction is load-bearing (master spec §27)."""

    price: float | None
    currency: str | None
    availability: OfferAvailability
    url: str | None


class AdapterProductProjection(BaseModel):
    """Product identity plus at most one offer.

    Deliberately carries NO evidence or trust data: an adapter must not be
    able to turn a claim into a public structured-data assertion, and the
    simplest guarantee is not to hand it the material (ADR-042)."""

    id: uuid.UUID
    name: str
    slug: str
    sku: str | None
    description: str | None
    brand: str | None
    category: str | None
    status: ProductStatus
    offer: AdapterOfferProjection | None


# --- Phase 10: commerce mapping & sync jobs --------------------------------


class CommerceMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID
    product_id: uuid.UUID
    installation_id: uuid.UUID | None
    woo_product_id: int
    woo_variation_id: int | None
    sku: str | None
    sync_status: CommerceSyncStatus
    last_synced_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class CommerceMappingUpsert(BaseModel):
    """No `organization_id`, no `site_id` — both derive from the
    authenticated installation (ADR-036). There is no field here through
    which an adapter could name a tenant."""

    product_id: uuid.UUID
    woo_product_id: int = Field(ge=1)
    woo_variation_id: int | None = Field(default=None, ge=1)
    sku: str | None = Field(default=None, max_length=120)


class CommerceMappingUpsertResponse(BaseModel):
    mapping: CommerceMappingRead
    created: bool


class OfferSyncRequest(BaseModel):
    """The complete set of Core data WooCommerce may change.

    Note what is absent and cannot be added by a client: product name,
    status, description, evidence, trust. `stock_quantity=None` means
    UNTRACKED and is preserved as such — never coerced to 0, which would
    read as out-of-stock."""

    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    availability: OfferAvailability = OfferAvailability.IN_STOCK
    stock_quantity: int | None = Field(default=None, ge=0)
    external_id: str | None = Field(default=None, max_length=255)
    idempotency_key: str | None = Field(default=None, max_length=200)


class OfferSyncResponse(BaseModel):
    offer_id: uuid.UUID
    product_id: uuid.UUID
    price: float | None
    currency: str | None
    availability: OfferAvailability
    stock_quantity: int | None
    job_id: uuid.UUID | None
    job_created: bool


class SyncJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    site_id: uuid.UUID | None
    job_type: SyncJobType
    status: SyncJobStatus
    payload: dict
    attempts: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    idempotency_key: str | None
    created_at: datetime
