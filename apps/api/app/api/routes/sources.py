from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import IngestionServiceDep, SourceServiceDep
from app.api.serialization import with_watchlist_counts
from app.schemas.common import ListResponse
from app.schemas.ingestion import CrawlJobRead
from app.schemas.sources import SourceCreate, SourceRead, SourceUpdate

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=ListResponse[SourceRead])
async def list_sources(
    service: SourceServiceDep, search: str | None = Query(default=None, max_length=200)
) -> ListResponse[SourceRead]:
    sources = await service.list(search)
    counts = await service.watchlist_counts([source.id for source in sources])
    items = with_watchlist_counts(SourceRead, sources, counts)
    return ListResponse(items=items, total=len(items))


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(payload: SourceCreate, service: SourceServiceDep) -> SourceRead:
    return SourceRead.model_validate(await service.create(payload))


@router.get("/{source_id}", response_model=SourceRead)
async def read_source(source_id: UUID, service: SourceServiceDep) -> SourceRead:
    source = await service.get(source_id)
    counts = await service.watchlist_counts([source.id])
    return with_watchlist_counts(SourceRead, [source], counts)[0]


@router.patch("/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: UUID, payload: SourceUpdate, service: SourceServiceDep
) -> SourceRead:
    return SourceRead.model_validate(await service.update(source_id, payload))


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: UUID, service: SourceServiceDep) -> None:
    await service.delete(source_id)


@router.post("/{source_id}/ingest", response_model=CrawlJobRead, status_code=status.HTTP_201_CREATED)
async def ingest_source(source_id: UUID, service: IngestionServiceDep) -> CrawlJobRead:
    job = await service.run(source_id)
    return CrawlJobRead.model_validate(job)
