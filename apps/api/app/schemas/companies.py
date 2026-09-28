from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import EntityBase
from app.schemas.normalizers import normalize_domain, normalize_text

CompanyName = Annotated[str, Field(min_length=1, max_length=200)]
CompanyDomain = Annotated[str | None, Field(max_length=253)]
CompanyDescription = Annotated[str | None, Field(max_length=2000)]


class CompanyCreate(BaseModel):
    name: CompanyName
    domain: CompanyDomain = None
    description: CompanyDescription = None

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

    @field_validator("domain")
    @classmethod
    def clean_domain(cls, value: str | None) -> str | None:
        return normalize_domain(value)


class CompanyUpdate(BaseModel):
    name: CompanyName | None = None
    domain: CompanyDomain = None
    description: CompanyDescription = None

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

    @field_validator("domain")
    @classmethod
    def clean_domain(cls, value: str | None) -> str | None:
        return normalize_domain(value)


class CompanyRead(EntityBase):
    name: str
    domain: str | None
    description: str | None
    watchlist_count: int = 0
