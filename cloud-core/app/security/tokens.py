"""
JWT access tokens.

Tokens are short-lived (settings.ACCESS_TOKEN_EXPIRE_MINUTES) and carry
only what's needed to authorize a request:
- sub: user id
- org: organization id (so tenant scoping doesn't require a DB round
  trip just to know which tenant the caller claims to belong to — the
  DB lookup in get_current_user still re-verifies the user is real,
  active, and belongs to that organization)
- role: user role at issuance time

No payment credentials, secrets, or free-text personal data are ever
placed into a token (master spec section 35/36 principle applied here
too, not just to commerce cart tokens).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

# PyJWT replaces python-jose (security audit SEC-08): python-jose 3.3.0 carries PYSEC-2024-232/233 and pulls in
# `ecdsa`, which has an unfixed timing advisory. Only HS256 with an explicit algorithm list is accepted.
import jwt
from jwt import PyJWTError as JWTError

from app.core.config import settings

TOKEN_TYPE_ACCESS = "access"  # noqa: S105 - not a secret, a literal tag


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or invalid."""


def create_access_token(
    *, user_id: str, organization_id: str, role: str, expires_delta: timedelta | None = None
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": user_id,
        "org": organization_id,
        "role": role,
        "type": TOKEN_TYPE_ACCESS,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise TokenError("Could not validate credentials") from exc

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise TokenError("Unexpected token type")

    return payload
