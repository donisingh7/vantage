from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ItemT = TypeVar("ItemT")


class ListResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    total: int


class EntityBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    created_at: datetime
    updated_at: datetime
