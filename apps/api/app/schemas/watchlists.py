from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import EntityBase
from app.schemas.companies import CompanyRead
from app.schemas.normalizers import normalize_text
from app.schemas.sources import SourceRead
from app.schemas.topics import TopicRead

WatchlistName = Annotated[str, Field(min_length=1, max_length=160)]
WatchlistDescription = Annotated[str | None, Field(max_length=2000)]


class WatchlistCreate(BaseModel):
    name: WatchlistName
    description: WatchlistDescription = None
    is_active: bool = True

    @field_validator("name", "description")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return normalize_text(value)


class WatchlistUpdate(BaseModel):
    name: WatchlistName | None = None
    description: WatchlistDescription = None
    is_active: bool | None = None

    @field_validator("name", "description")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return normalize_text(value)


class WatchlistCounts(BaseModel):
    companies: int
    topics: int
    sources: int


class WatchlistRead(EntityBase):
    name: str
    description: str | None
    is_active: bool
    counts: WatchlistCounts


class WatchlistDetail(WatchlistRead):
    companies: list[CompanyRead]
    topics: list[TopicRead]
    sources: list[SourceRead]
