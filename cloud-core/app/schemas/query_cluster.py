"""Pydantic contracts for QueryCluster and its membership."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QueryClusterMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    query_cluster_id: uuid.UUID
    query_id: uuid.UUID
    score: float | None
    created_at: datetime


class QueryClusterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    label: str | None
    created_at: datetime
    updated_at: datetime


class QueryClusterRunResult(BaseModel):
    cluster_count: int
    clustered_query_count: int
    unclustered_query_count: int
