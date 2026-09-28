from uuid import UUID

from pydantic import BaseModel, Field


class SearchResultRead(BaseModel):
    document_id: UUID
    title: str | None
    source_name: str
    source_url: str
    canonical_url: str
    excerpt: str
    similarity: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultRead]


class IndexResultRead(BaseModel):
    document_id: UUID
    chunks_created: int
    total_chunks: int
    skipped: bool


class IndexPendingRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=25)


class IndexPendingResponse(BaseModel):
    indexed: int
    results: list[IndexResultRead]
