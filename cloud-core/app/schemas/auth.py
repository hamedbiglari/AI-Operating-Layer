"""Pydantic contracts for authentication endpoints."""

from pydantic import BaseModel, EmailStr, Field

from app.schemas.organization import OrganizationRead
from app.schemas.user import UserRead


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class RegisterOrganizationRequest(BaseModel):
    """Bootstraps a brand-new tenant: creates the Organization and its
    first user as OWNER in a single transaction."""

    organization_name: str = Field(min_length=1, max_length=255)
    owner_email: EmailStr
    owner_name: str = Field(min_length=1, max_length=255)
    owner_password: str = Field(min_length=8, max_length=128)


class RegisterOrganizationResponse(BaseModel):
    organization: OrganizationRead
    user: UserRead
    token: TokenResponse


class MeResponse(BaseModel):
    user: UserRead
    organization: OrganizationRead
