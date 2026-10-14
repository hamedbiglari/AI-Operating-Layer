"""
Tenant isolation enforcement.

This is the single helper every service function uses to fetch a
tenant-owned row. It is the direct implementation of the Phase 0 review's
"golden test": a user from Organization A must NEVER be able to read a
resource belonging to Organization B — not even to learn it exists.

Design decision: cross-tenant access returns 404, not 403. Returning 403
would confirm the resource exists in another tenant; 404 reveals nothing
about whether the ID is valid, unowned, or owned by someone else.
"""

from typing import TypeVar
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


def get_tenant_scoped_or_404(
    db: Session,
    model: type[ModelT],
    object_id: UUID,
    *,
    organization_id: UUID,
    not_found_message: str = "Resource not found",
) -> ModelT:
    """Fetch `model` by primary key, scoped to `organization_id`.

    Returns 404 both when the row doesn't exist at all AND when it
    exists but belongs to a different organization — the two cases are
    made indistinguishable to the caller on purpose.
    """
    obj = db.get(model, object_id)
    if obj is None or getattr(obj, "organization_id", None) != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_message)
    return obj
