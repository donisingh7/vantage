from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str
    is_active: bool


class CurrentIdentity(BaseModel):
    user: UserRead
    workspace: WorkspaceRead
    role: str


class WorkspaceSummary(BaseModel):
    watchlists: int
    companies: int
    topics: int
    sources: int
    active_watchlists: int
    active_sources: int
