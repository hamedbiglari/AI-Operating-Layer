"""Pydantic contracts for Intent."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import IntentClassificationSource, IntentType


class IntentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query_id: uuid.UUID
    intent_type: IntentType
    confidence: float | None
    entity_id: uuid.UUID | None
    product_id: uuid.UUID | None
    classification_source: IntentClassificationSource
    reason: str | None
    is_primary: bool
    created_at: datetime


class ManualIntentCreate(BaseModel):
    """Human override / manual classification. Always creates a NEW
    Intent row (classification_source=MANUAL) rather than editing any
    existing rule-engine row — see Intent's model docstring."""

    intent_type: IntentType
    entity_id: uuid.UUID | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str | None = Field(default=None, max_length=2000)
    is_primary: bool = True
