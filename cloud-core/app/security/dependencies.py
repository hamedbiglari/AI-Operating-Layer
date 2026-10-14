"""
FastAPI dependencies for authentication and tenant isolation.

`get_current_user` is the single choke point every protected endpoint
goes through: decode token -> load user from DB -> verify user AND their
organization are still active. `require_roles` layers authorization on
top. `get_current_user.organization_id` is what every service-layer
query must filter on — see app.security.tenant for the enforcement
helper.
"""

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.enums import OrganizationStatus, UserRole, UserStatus
from app.models.organization import Organization
from app.models.user import User
from app.security.tokens import TokenError, decode_access_token

# tokenUrl is documentation-only (drives the Swagger "Authorize" flow);
# the actual route is registered in app/api/v1/auth.py.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if token is None:
        raise _CREDENTIALS_EXCEPTION

    try:
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
    except (TokenError, KeyError, ValueError):
        raise _CREDENTIALS_EXCEPTION from None

    user = db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_EXCEPTION

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active")

    organization = db.get(Organization, user.organization_id)
    if organization is None or organization.status not in (
        OrganizationStatus.ACTIVE,
        OrganizationStatus.PENDING,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Organization is not active"
        )

    return user


def require_roles(*allowed_roles: UserRole) -> Callable[[User], User]:
    """Dependency factory: raises 403 unless current_user.role is allowed.

    Usage: `current_user: User = Depends(require_roles(UserRole.OWNER, UserRole.ADMIN))`
    """

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return _dependency
