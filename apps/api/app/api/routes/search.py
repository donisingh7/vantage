from fastapi import APIRouter, Query

from app.api.deps import IndexingServiceDep, SearchServiceDep
from app.schemas.search import (
    IndexPendingRequest,
    IndexPendingResponse,
    IndexResultRead,
    SearchResponse,
    SearchResultRead,
)

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    service: SearchServiceDep,
    q: str = Query(..., min_length=1, max_length=500),
    top_k: int = Query(default=5, ge=1, le=20),
) -> SearchResponse:
    results = await service.search(q, top_k=top_k)
    return SearchResponse(
        query=q,
        results=[
            SearchResultRead(
                document_id=result.document_id, title=result.title, source_name=result.source_name,
                source_url=result.source_url, canonical_url=result.canonical_url,
                excerpt=result.excerpt, similarity=result.similarity,
            )
            for result in results
        ],
    )


@router.post("/search/index-pending", response_model=IndexPendingResponse)
async def index_pending(
    service: IndexingServiceDep, payload: IndexPendingRequest | None = None
) -> IndexPendingResponse:
    limit = payload.limit if payload is not None else 5
    results = await service.index_pending(limit=limit)
    return IndexPendingResponse(
        indexed=len(results),
        results=[
            IndexResultRead(
                document_id=result.document_id, chunks_created=result.chunks_created,
                total_chunks=result.total_chunks, skipped=result.skipped,
            )
            for result in results
        ],
    )
