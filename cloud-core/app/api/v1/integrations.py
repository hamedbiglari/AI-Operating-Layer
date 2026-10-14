"""
Installation management (human-operated) and the adapter-facing
integration surface (machine-operated).

Two authentication realms, deliberately separate:

- `/installations/**` — operated by HUMAN users with
  KNOWLEDGE_EDITOR_ROLES. An installation cannot create or escalate
  itself; credentials authenticate, they do not administer.
- `/adapter/**` — operated by MACHINE clients holding an installation
  credential. Tenant is derived from the credential (ADR-036); no
  endpoint here accepts an organization_id.

Rate limiting applies only to `/adapter/**`, positioned after identity
resolution and before Core work (ADR-039).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import (
    KNOWLEDGE_EDITOR_ROLES,
    AdapterScope,
    CommerceSyncStatus,
    SyncJobStatus,
    SyncJobType,
    AdapterType,
    InstallationStatus,
    MappedObjectType,
    SyncStatus,
)
from app.models.installation import Installation, InstallationCredential
from app.models.user import User
from app.models.wordpress_mapping import WordPressMapping
from app.schemas.common import Page, PaginationParams, SortParams
from app.schemas.integration import (
    AdapterIdentityResponse,
    CommerceMappingRead,
    CommerceMappingUpsert,
    CommerceMappingUpsertResponse,
    OfferSyncRequest,
    OfferSyncResponse,
    SyncJobRead,
    AdapterOfferProjection,
    AdapterProductProjection,
    CredentialIssueRequest,
    CredentialIssueResponse,
    CredentialRead,
    InstallationCreate,
    InstallationRead,
    InstallationStatusChange,
    MappingRead,
    MappingUpsertRequest,
    MappingUpsertResponse,
)
from app.security.dependencies import get_current_user, require_roles
from app.security.machine_identity import MachineIdentity, get_machine_identity
from app.security.rate_limit import rate_limited
from app.contracts import commerce as commerce_contract
from app.models.commerce_mapping import CommerceMapping
from app.models.sync_job import SyncJob
from app.services import commerce_sync_service, installation_service, wordpress_mapping_service

router = APIRouter(tags=["integration"])


# --- Human-operated: installation management --------------------------------


@router.get("/installations", response_model=Page[InstallationRead])
def list_installations(
    adapter_type: AdapterType | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[InstallationRead]:
    items, total = installation_service.list_installations(
        db, organization_id=current_user.organization_id, adapter_type=adapter_type,
        sort=sort, limit=pagination.limit, offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/installations", response_model=InstallationRead, status_code=status.HTTP_201_CREATED)
def create_installation(
    payload: InstallationCreate,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Installation:
    return installation_service.create_installation(
        db, organization_id=current_user.organization_id, name=payload.name,
        adapter_type=payload.adapter_type, site_id=payload.site_id,
        external_url=payload.external_url, actor_user_id=current_user.id,
    )


@router.get("/installations/{installation_id}", response_model=InstallationRead)
def get_installation(
    installation_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Installation:
    return installation_service.get_installation_or_404(
        db, installation_id=installation_id, organization_id=current_user.organization_id
    )


@router.post("/installations/{installation_id}/status", response_model=InstallationRead)
def change_installation_status(
    installation_id: UUID,
    payload: InstallationStatusChange,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> Installation:
    installation = installation_service.get_installation_or_404(
        db, installation_id=installation_id, organization_id=current_user.organization_id
    )
    return installation_service.set_installation_status(
        db, installation=installation, status=payload.status, actor_user_id=current_user.id
    )


@router.get("/installations/{installation_id}/credentials", response_model=Page[CredentialRead])
def list_credentials(
    installation_id: UUID,
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[CredentialRead]:
    items, total = installation_service.list_credentials(
        db, installation_id=installation_id, organization_id=current_user.organization_id,
        sort=sort, limit=pagination.limit, offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post(
    "/installations/{installation_id}/credentials",
    response_model=CredentialIssueResponse, status_code=status.HTTP_201_CREATED,
)
def issue_credential(
    installation_id: UUID,
    payload: CredentialIssueRequest,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> CredentialIssueResponse:
    """The response contains the ONLY copy of the plaintext token."""
    installation = installation_service.get_installation_or_404(
        db, installation_id=installation_id, organization_id=current_user.organization_id
    )
    credential, token = installation_service.issue_credential(
        db, installation=installation, scopes=payload.scopes,
        expires_at=payload.expires_at, actor_user_id=current_user.id,
    )
    return CredentialIssueResponse(credential=CredentialRead.model_validate(credential), token=token)


@router.post("/credentials/{credential_id}/rotate", response_model=CredentialIssueResponse)
def rotate_credential(
    credential_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> CredentialIssueResponse:
    credential = installation_service.get_credential_or_404(
        db, credential_id=credential_id, organization_id=current_user.organization_id
    )
    new_credential, token = installation_service.rotate_credential(
        db, credential=credential, actor_user_id=current_user.id
    )
    return CredentialIssueResponse(credential=CredentialRead.model_validate(new_credential), token=token)


@router.post("/credentials/{credential_id}/revoke", response_model=CredentialRead)
def revoke_credential(
    credential_id: UUID,
    current_user: User = Depends(require_roles(*KNOWLEDGE_EDITOR_ROLES)),
    db: Session = Depends(get_db),
) -> InstallationCredential:
    credential = installation_service.get_credential_or_404(
        db, credential_id=credential_id, organization_id=current_user.organization_id
    )
    return installation_service.revoke_credential(
        db, credential=credential, actor_user_id=current_user.id
    )


@router.get("/mappings", response_model=Page[MappingRead])
def list_mappings_human(
    site_id: UUID | None = Query(default=None),
    object_type: MappedObjectType | None = Query(default=None),
    sync_status: SyncStatus | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[MappingRead]:
    items, total = wordpress_mapping_service.list_mappings(
        db, organization_id=current_user.organization_id, site_id=site_id,
        object_type=object_type, sync_status=sync_status,
        sort=sort, limit=pagination.limit, offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


# --- Machine-operated: the adapter surface ------------------------------------


@router.get("/adapter/identity", response_model=AdapterIdentityResponse)
def adapter_identity(identity: MachineIdentity = Depends(get_machine_identity)) -> AdapterIdentityResponse:
    """Lets an adapter confirm what Core believes it is. Note the
    organization_id here is REPORTED to the adapter, never accepted
    from it."""
    return AdapterIdentityResponse(
        installation_id=identity.installation_id,
        organization_id=identity.organization_id,
        site_id=identity.site_id,
        adapter_type=identity.adapter_type,
        scopes=sorted(s.value for s in identity.scopes),
    )


@router.post(
    "/adapter/mappings", response_model=MappingUpsertResponse, status_code=status.HTTP_200_OK
)
def upsert_mapping(
    payload: MappingUpsertRequest,
    identity: MachineIdentity = Depends(rate_limited(limit=120)),
    db: Session = Depends(get_db),
) -> MappingUpsertResponse:
    """Idempotent: the same post delivered repeatedly yields one row and
    a 200 with `created: false`. Returns 200 rather than 201 precisely
    because the operation is an upsert — a retried webhook is not a
    creation.

    `site_id` comes from the installation, never the payload. An
    installation with no site cannot map anything, which is a
    configuration error worth failing on rather than guessing."""
    from fastapi import HTTPException

    if identity.site_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This installation is not bound to a site; mappings require a site-scoped installation.",
        )
    if not identity.has_scope(AdapterScope.MAPPINGS_WRITE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credential lacks required scope: mappings:write",
        )

    mapping, created = wordpress_mapping_service.upsert_mapping(
        db,
        organization_id=identity.organization_id,  # derived, not supplied
        site_id=identity.site_id,
        installation_id=identity.installation_id,
        object_type=payload.object_type,
        object_id=payload.object_id,
        wordpress_post_id=payload.wordpress_post_id,
        wordpress_post_type=payload.wordpress_post_type,
        wordpress_url=payload.wordpress_url,
        remote_updated_at=payload.remote_updated_at,
        actor_user_id=None,
    )
    return MappingUpsertResponse(mapping=MappingRead.model_validate(mapping), created=created)


@router.get("/adapter/catalog/{product_id}", response_model=AdapterProductProjection)
def adapter_catalog_product(
    product_id: UUID,
    identity: MachineIdentity = Depends(rate_limited(limit=240)),
    db: Session = Depends(get_db),
) -> AdapterProductProjection:
    """The read projection an adapter needs to render structured data.

    Added in Phase 9 because §38 requires schema rendering and no read
    surface existed for it — `AdapterScope.CATALOG_READ` was defined but
    unreachable. Deliberately narrow: it exposes product identity and ONE
    chosen offer, and nothing about evidence or trust. An adapter has no
    business rendering evidence claims as public assertions, so the data
    to do so is simply not provided (ADR-042).

    Offer selection reuses the Commerce contract's own `is_purchasable`
    rule rather than reimplementing it here — the adapter must not get a
    second opinion about what is purchasable."""
    from fastapi import HTTPException

    if not identity.has_scope(AdapterScope.CATALOG_READ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Credential lacks required scope: catalog:read"
        )

    product = commerce_contract.get_product(
        db, product_id=product_id, organization_id=identity.organization_id
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    offers = commerce_contract.get_offers_for_products(
        db, product_ids=[product.id], organization_id=identity.organization_id
    ).get(product.id, [])
    purchasable = [o for o in offers if o.is_purchasable()]
    priced = [o for o in purchasable if o.has_known_price]
    chosen = min(priced, key=lambda o: o.price) if priced else (purchasable[0] if purchasable else None)

    return AdapterProductProjection(
        id=product.id,
        name=product.name,
        slug=product.slug,
        sku=None,
        description=None,
        brand=product.brand,
        category=product.category,
        status=product.status,
        offer=(
            AdapterOfferProjection(
                price=chosen.price,
                currency=chosen.currency,
                availability=chosen.availability,
                url=None,
            )
            if chosen is not None
            else None
        ),
    )


@router.get("/adapter/mappings", response_model=Page[MappingRead])
def list_mappings_adapter(
    object_type: MappedObjectType | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    identity: MachineIdentity = Depends(rate_limited(limit=120)),
    db: Session = Depends(get_db),
) -> Page[MappingRead]:
    from fastapi import HTTPException

    if not identity.has_scope(AdapterScope.MAPPINGS_READ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Credential lacks required scope: mappings:read"
        )
    items, total = wordpress_mapping_service.list_mappings(
        db, organization_id=identity.organization_id, site_id=identity.site_id,
        object_type=object_type, sync_status=None,
        sort=sort, limit=pagination.limit, offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


# --- Phase 10: WooCommerce commerce sync ------------------------------------
#
# THE BOUNDARY, restated where it is enforced: these endpoints can change an
# Offer's price/stock/availability and nothing else. There is no route here
# that reaches Product identity, Product status, ProductEvidence,
# TrustRecord or Recommendation - not "no permission for", but no route.
# A WooCommerce store cannot publish a product or verify a claim because the
# code to do so does not exist on this surface (ADR-050).


@router.post(
    "/adapter/commerce/mappings",
    response_model=CommerceMappingUpsertResponse,
    status_code=status.HTTP_200_OK,
)
def upsert_commerce_mapping(
    payload: CommerceMappingUpsert,
    identity: MachineIdentity = Depends(rate_limited(limit=240)),
    db: Session = Depends(get_db),
) -> CommerceMappingUpsertResponse:
    """Idempotent: a webhook delivered repeatedly yields one mapping and
    `created: false`. 200 rather than 201 because a retried delivery is not
    a creation. Re-pointing a Woo product at a DIFFERENT Core product
    returns 409 - that is a decision, not a sync event, and silently
    rewriting it would move a merchant's evidence history onto another
    product."""
    from fastapi import HTTPException

    if not identity.has_scope(AdapterScope.COMMERCE_WRITE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Credential lacks required scope: commerce:write"
        )
    if identity.site_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This installation is not bound to a site; commerce mappings require a site-scoped installation.",
        )

    mapping, created = commerce_sync_service.upsert_commerce_mapping(
        db,
        organization_id=identity.organization_id,  # derived, never supplied
        site_id=identity.site_id,
        installation_id=identity.installation_id,
        product_id=payload.product_id,
        woo_product_id=payload.woo_product_id,
        woo_variation_id=payload.woo_variation_id,
        sku=payload.sku,
        actor_user_id=None,
    )
    return CommerceMappingUpsertResponse(
        mapping=CommerceMappingRead.model_validate(mapping), created=created
    )


@router.get("/adapter/commerce/mappings", response_model=Page[CommerceMappingRead])
def list_commerce_mappings_adapter(
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    identity: MachineIdentity = Depends(rate_limited(limit=240)),
    db: Session = Depends(get_db),
) -> Page[CommerceMappingRead]:
    from fastapi import HTTPException

    if not identity.has_scope(AdapterScope.COMMERCE_READ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Credential lacks required scope: commerce:read"
        )
    items, total = commerce_sync_service.list_commerce_mappings(
        db, organization_id=identity.organization_id, site_id=identity.site_id,
        sync_status=None, sort=sort, limit=pagination.limit, offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.post("/adapter/commerce/mappings/{mapping_id}/offer", response_model=OfferSyncResponse)
def sync_offer(
    mapping_id: UUID,
    payload: OfferSyncRequest,
    identity: MachineIdentity = Depends(rate_limited(limit=480)),
    db: Session = Depends(get_db),
) -> OfferSyncResponse:
    """Price/stock sync - the ONLY Core write WooCommerce may perform.

    A SyncJob row is recorded for every accepted sync so the operation is
    auditable and, with an `idempotency_key`, exactly-once. The limit is
    higher here than on mapping because stock changes are genuinely
    frequent, while mappings change rarely."""
    from fastapi import HTTPException

    if not identity.has_scope(AdapterScope.COMMERCE_WRITE):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Credential lacks required scope: commerce:write"
        )

    mapping = commerce_sync_service.get_commerce_mapping_or_404(
        db, mapping_id=mapping_id, organization_id=identity.organization_id
    )

    job, job_created = commerce_sync_service.enqueue_job(
        db,
        organization_id=identity.organization_id,
        site_id=identity.site_id,
        job_type=SyncJobType.COMMERCE_OFFER_SYNC,
        payload={"mapping_id": str(mapping_id), "availability": payload.availability.value},
        idempotency_key=payload.idempotency_key,
        actor_user_id=None,
    )
    # A repeated idempotency key means this exact sync already happened.
    # Re-applying it would be harmless but dishonest about what occurred.
    if not job_created and payload.idempotency_key:
        offer_id = None
        from app.models.offer import Offer
        from sqlalchemy import select as _select
        existing_offer = db.execute(
            _select(Offer).where(
                Offer.organization_id == identity.organization_id,
                Offer.product_id == mapping.product_id,
            )
        ).scalars().first()
        if existing_offer is not None:
            return OfferSyncResponse(
                offer_id=existing_offer.id, product_id=mapping.product_id,
                price=float(existing_offer.price) if existing_offer.price is not None else None,
                currency=existing_offer.currency, availability=existing_offer.availability,
                stock_quantity=existing_offer.stock_quantity,
                job_id=job.id, job_created=False,
            )

    commerce_sync_service.mark_running(db, job=job)
    try:
        offer = commerce_sync_service.apply_offer_sync(
            db, mapping=mapping, price=payload.price, currency=payload.currency,
            availability=payload.availability, stock_quantity=payload.stock_quantity,
            external_id=payload.external_id, actor_user_id=None,
        )
    except HTTPException as exc:
        commerce_sync_service.mark_failed(db, job=job, error=str(exc.detail))
        raise
    commerce_sync_service.mark_succeeded(db, job=job)

    return OfferSyncResponse(
        offer_id=offer.id, product_id=mapping.product_id,
        price=float(offer.price) if offer.price is not None else None,
        currency=offer.currency, availability=offer.availability,
        stock_quantity=offer.stock_quantity, job_id=job.id, job_created=job_created,
    )


# --- Human-operated sync job visibility --------------------------------------


@router.get("/sync-jobs", response_model=Page[SyncJobRead])
def list_sync_jobs(
    status_filter: SyncJobStatus | None = Query(default=None, alias="status"),
    job_type: SyncJobType | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[SyncJobRead]:
    """Operators need to see DEAD_LETTER jobs specifically - those are the
    ones that stopped retrying and need a human."""
    items, total = commerce_sync_service.list_jobs(
        db, organization_id=current_user.organization_id, status=status_filter,
        job_type=job_type, sort=sort, limit=pagination.limit, offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)


@router.get("/sync-jobs/{job_id}", response_model=SyncJobRead)
def get_sync_job(
    job_id: UUID, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> SyncJob:
    return commerce_sync_service.get_job_or_404(
        db, job_id=job_id, organization_id=current_user.organization_id
    )


@router.get("/commerce-mappings", response_model=Page[CommerceMappingRead])
def list_commerce_mappings_human(
    site_id: UUID | None = Query(default=None),
    sync_status: CommerceSyncStatus | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    sort: SortParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[CommerceMappingRead]:
    items, total = commerce_sync_service.list_commerce_mappings(
        db, organization_id=current_user.organization_id, site_id=site_id,
        sync_status=sync_status, sort=sort, limit=pagination.limit, offset=pagination.offset,
    )
    return Page(items=items, total=total, limit=pagination.limit, offset=pagination.offset)
