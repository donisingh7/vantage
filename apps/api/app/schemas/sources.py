from typing import Annotated

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from app.models import IngestionInterval, SourceType
from app.schemas.common import EntityBase
from app.schemas.normalizers import normalize_text

SourceName = Annotated[str, Field(min_length=1, max_length=200)]


class SourceCreate(BaseModel):
    name: SourceName
    url: AnyHttpUrl
    source_type: SourceType = SourceType.WEBSITE
    is_active: bool = True
    ingestion_interval: IngestionInterval = IngestionInterval.MANUAL

    @field_validator("name")
    @classmethod
    def clean_text(cls, value: str) -> str | None:
        cleaned = normalize_text(value)
        if cleaned is None:
            raise ValueError("Name cannot be blank")
        return cleaned

    @field_validator("url")
    @classmethod
    def reject_embedded_credentials(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password:
            raise ValueError("Source URL cannot contain credentials")
        return value


class SourceUpdate(BaseModel):
    name: SourceName | None = None
    url: AnyHttpUrl | None = None
    source_type: SourceType | None = None
    is_active: bool | None = None
    ingestion_interval: IngestionInterval | None = None

    @field_validator("name")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = normalize_text(value)
        if cleaned is None:
            raise ValueError("Name cannot be blank")
        return cleaned

    @field_validator("url")
    @classmethod
    def reject_embedded_credentials(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value and (value.username or value.password):
            raise ValueError("Source URL cannot contain credentials")
        return value


class SourceRead(EntityBase):
    name: str
    url: str
    source_type: SourceType
    is_active: bool
    ingestion_interval: IngestionInterval
    watchlist_count: int = 0
