from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import CompanyServiceDep
from app.api.serialization import with_watchlist_counts
from app.schemas.common import ListResponse
from app.schemas.companies import CompanyCreate, CompanyRead, CompanyUpdate

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=ListResponse[CompanyRead])
async def list_companies(
    service: CompanyServiceDep, search: str | None = Query(default=None, max_length=200)
) -> ListResponse[CompanyRead]:
    companies = await service.list(search)
    counts = await service.watchlist_counts([company.id for company in companies])
    items = with_watchlist_counts(CompanyRead, companies, counts)
    return ListResponse(items=items, total=len(items))


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(payload: CompanyCreate, service: CompanyServiceDep) -> CompanyRead:
    return CompanyRead.model_validate(await service.create(payload))


@router.get("/{company_id}", response_model=CompanyRead)
async def read_company(company_id: UUID, service: CompanyServiceDep) -> CompanyRead:
    company = await service.get(company_id)
    counts = await service.watchlist_counts([company.id])
    return with_watchlist_counts(CompanyRead, [company], counts)[0]


@router.patch("/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: UUID, payload: CompanyUpdate, service: CompanyServiceDep
) -> CompanyRead:
    return CompanyRead.model_validate(await service.update(company_id, payload))


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(company_id: UUID, service: CompanyServiceDep) -> None:
    await service.delete(company_id)
