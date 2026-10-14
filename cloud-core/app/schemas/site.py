"""Pydantic contracts for Site."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SitePlatform, SiteStatus


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    domain: str
    platform: SitePlatform
    wordpress_url: str | None
    woo_enabled: bool
    status: SiteStatus
    created_at: datetime
    updated_at: datetime


class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=255)
    platform: SitePlatform = SitePlatform.WORDPRESS
    wordpress_url: str | None = Field(default=None, max_length=500)
    woo_enabled: bool = False


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    wordpress_url: str | None = Field(default=None, max_length=500)
    woo_enabled: bool | None = None
    status: SiteStatus | None = None
