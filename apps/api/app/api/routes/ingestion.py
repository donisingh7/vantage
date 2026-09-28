from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import IngestionServiceDep
from app.schemas.common import ListResponse
from app.schemas.ingestion import CrawlJobRead

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/jobs", response_model=ListResponse[CrawlJobRead])
async def list_jobs(
    service: IngestionServiceDep, source_id: UUID | None = Query(default=None)
) -> ListResponse[CrawlJobRead]:
    jobs = await service.list_jobs(source_id)
    items = [CrawlJobRead.model_validate(job) for job in jobs]
    return ListResponse(items=items, total=len(items))


@router.get("/jobs/{job_id}", response_model=CrawlJobRead)
async def read_job(job_id: UUID, service: IngestionServiceDep) -> CrawlJobRead:
    return CrawlJobRead.model_validate(await service.get_job(job_id))
