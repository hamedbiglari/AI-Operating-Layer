"""
CustomerContext service (master spec section 32).

Small on purpose. The Phase 8 brief is explicit that this must not
become a CRM, so there is no merge-by-customer-id, no profile
enrichment, no cross-session stitching — each context is a standalone
record of what one request knows about its asker.

`withdraw_consent` exists as its own action rather than a PATCH field
because consent withdrawal is a privacy event that must be audit-logged
distinctly, and because it has a hard downstream effect (see
recommendation_policy.check_consent): a withdrawn context produces no
recommendations at all.
"""

from uuid import UUID

from fastapi import HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.customer_context import CustomerContext
from app.models.enums import ConsentStatus, ContextType
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log

_NON_NULLABLE_UPDATABLE_FIELDS = frozenset(
    {"purchase_intent", "evidence_need", "trust_need", "price_sensitivity", "consent_status", "preferences"}
)


def list_customer_contexts(
    db: Session,
    *,
    organization_id: UUID,
    customer_id: str | None,
    session_id: str | None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[CustomerContext], int]:
    base = select(CustomerContext).where(CustomerContext.organization_id == organization_id)
    if customer_id:
        base = base.where(CustomerContext.customer_id == customer_id)
    if session_id:
        base = base.where(CustomerContext.session_id == session_id)

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(apply_sort(base, CustomerContext, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_context_or_404(db: Session, *, context_id: UUID, organization_id: UUID) -> CustomerContext:
    return get_tenant_scoped_or_404(
        db, CustomerContext, context_id, organization_id=organization_id,
        not_found_message="Customer context not found",
    )


def create_customer_context(
    db: Session, *, organization_id: UUID, actor_user_id: UUID, **fields
) -> CustomerContext:
    context = CustomerContext(organization_id=organization_id, **fields)
    db.add(context)
    db.flush()

    # Deliberately does NOT log topic/preferences content - the audit
    # trail records that a context was created and of what kind, not
    # what the person said.
    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="customer_context.created",
        resource_type="customer_context",
        resource_id=context.id,
        new_value={
            "context_type": context.context_type.value,
            "consent_status": context.consent_status.value,
            "source": context.source.value,
        },
    )
    db.commit()
    db.refresh(context)
    return context


def update_customer_context(
    db: Session, *, context: CustomerContext, actor_user_id: UUID, **fields
) -> CustomerContext:
    for field_name, value in fields.items():
        if value is None and field_name in _NON_NULLABLE_UPDATABLE_FIELDS:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{field_name}' cannot be set to null.",
            )

    old_consent = context.consent_status
    for field_name, value in fields.items():
        setattr(context, field_name, value)

    db.flush()
    record_audit_log(
        db,
        organization_id=context.organization_id,
        user_id=actor_user_id,
        action="customer_context.updated",
        resource_type="customer_context",
        resource_id=context.id,
        old_value={"consent_status": old_consent.value},
        new_value={"consent_status": context.consent_status.value},
    )
    db.commit()
    db.refresh(context)
    return context


def withdraw_consent(db: Session, *, context: CustomerContext, actor_user_id: UUID) -> CustomerContext:
    """Privacy action with a hard downstream effect - see module
    docstring. Also clears the identity fields, because the point of
    withdrawing consent is that the identity should no longer be
    retained; the row survives so the merchant retains the audit fact
    that a context existed and was withdrawn."""
    old_value = {"consent_status": context.consent_status.value, "context_type": context.context_type.value}

    context.consent_status = ConsentStatus.WITHDRAWN
    context.customer_id = None
    context.session_id = None
    context.context_type = ContextType.ANONYMOUS
    context.preferences = {}

    db.flush()
    record_audit_log(
        db,
        organization_id=context.organization_id,
        user_id=actor_user_id,
        action="customer_context.consent_withdrawn",
        resource_type="customer_context",
        resource_id=context.id,
        old_value=old_value,
        new_value={"consent_status": context.consent_status.value},
    )
    db.commit()
    db.refresh(context)
    return context
