from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import EntityBase
from app.schemas.normalizers import normalize_text

TopicName = Annotated[str, Field(min_length=1, max_length=200)]
TopicDescription = Annotated[str | None, Field(max_length=2000)]


class TopicCreate(BaseModel):
    name: TopicName
    description: TopicDescription = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = normalize_text(value)
        if cleaned is None:
            raise ValueError("Name cannot be blank")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return normalize_text(value)


class TopicUpdate(BaseModel):
    name: TopicName | None = None
    description: TopicDescription = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = normalize_text(value)
        if cleaned is None:
            raise ValueError("Name cannot be blank")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        return normalize_text(value)


class TopicRead(EntityBase):
    name: str
    description: str | None
    watchlist_count: int = 0
