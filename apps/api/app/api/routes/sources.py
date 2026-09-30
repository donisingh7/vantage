from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import IngestionServiceDep, SourceManagementServiceDep, SourceServiceDep
from app.api.serialization import with_watchlist_counts
from app.core.config import Settings, get_settings
from app.schemas.common import ListResponse
from app.schemas.ingestion import CrawlJobRead
from app.schemas.sources import (
    SourceCreate,
    SourceManagementRead,
    SourceRead,
    SourcesManagementResponse,
    SourceUpdate,
)

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/management/view", response_model=SourcesManagementResponse)
async def read_sources_management(
    service: SourceManagementServiceDep,
    counts_service: SourceServiceDep,
    settings: Annotated[Settings, Depends(get_settings)],
    search: str | None = Query(default=None, max_length=200),
) -> SourcesManagementResponse:
    """Each source plus its own latest ingestion job, in one request -- replaces
    GET /sources followed by GET /ingestion/jobs (full job history) for the Sources page.

    Deliberately two path segments (/management/view, not /management): a pre-Pass-3 Lambda
    already has GET /sources/{source_id} with a UUID-typed path param. A single-segment
    /sources/management would match that route's URL shape first and fail UUID validation
    with a 422, not a 404 -- breaking the frontend's 404-only rollout fallback during the
    window between this frontend deploying (automatic) and the Lambda deploying (manual).
    Two segments can never match a one-segment dynamic route, so an old Lambda genuinely has
    no route for this path and returns a real 404.
    """
    rows = await service.list_with_latest_job(search)
    counts = await counts_service.watchlist_counts([source.id for source, _ in rows])
    items = [
        SourceManagementRead.model_validate(source).model_copy(
            update={
                "watchlist_count": counts.get(source.id, 0),
                "latest_job": CrawlJobRead.model_validate(job) if job is not None else None,
            }
        )
        for source, job in rows
    ]
    return SourcesManagementResponse(items=items, total=len(items), scheduler_enabled=settings.enable_scheduler)


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
