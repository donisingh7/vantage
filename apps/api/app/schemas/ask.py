from uuid import UUID

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class AskCitationRead(BaseModel):
    document_id: UUID
    title: str | None
    source_name: str
    url: str
    excerpt: str
    similarity: float


class AskResponse(BaseModel):
    answer: str
    citations: list[AskCitationRead]
    retrieved_count: int
    provider: str
    grounded: bool
