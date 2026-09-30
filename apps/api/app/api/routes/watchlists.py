from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import (
    CompanyServiceDep,
    SourceServiceDep,
    TopicServiceDep,
    WatchlistBootstrapServiceDep,
    WatchlistServiceDep,
)
from app.api.serialization import to_watchlist_detail, to_watchlist_read
from app.models import Watchlist
from app.schemas.common import ListResponse
from app.schemas.watchlists import (
    WatchlistBootstrapResponse,
    WatchlistCreate,
    WatchlistDetail,
    WatchlistRead,
    WatchlistUpdate,
)
from app.services.watchlists import MemberKind

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("/bootstrap", response_model=WatchlistBootstrapResponse)
async def read_watchlist_bootstrap(service: WatchlistBootstrapServiceDep) -> WatchlistBootstrapResponse:
    """Everything the Watchlists page needs for its first render, in one request."""
    data = await service.bootstrap()
    return WatchlistBootstrapResponse(
        watchlists=data.watchlists, companies=data.companies, topics=data.topics, sources=data.sources,
        initial_detail=data.initial_detail,
    )


async def _detail(
    watchlist: Watchlist,
    companies: CompanyServiceDep,
    topics: TopicServiceDep,
    sources: SourceServiceDep,
) -> WatchlistDetail:
    return to_watchlist_detail(
        watchlist,
        await companies.watchlist_counts([company.id for company in watchlist.companies]),
        await topics.watchlist_counts([topic.id for topic in watchlist.topics]),
        await sources.watchlist_counts([source.id for source in watchlist.sources]),
    )


@router.get("", response_model=ListResponse[WatchlistRead])
async def list_watchlists(
    service: WatchlistServiceDep,
    search: str | None = Query(default=None, max_length=200),
    company_id: UUID | None = Query(default=None),
    topic_id: UUID | None = Query(default=None),
) -> ListResponse[WatchlistRead]:
    if company_id is not None or topic_id is not None:
        watchlists = await service.list_containing(company_id=company_id, topic_id=topic_id)
    else:
        watchlists = await service.list(search)
    items = [to_watchlist_read(watchlist) for watchlist in watchlists]
    return ListResponse(items=items, total=len(items))


@router.post("", response_model=WatchlistRead, status_code=status.HTTP_201_CREATED)
async def create_watchlist(payload: WatchlistCreate, service: WatchlistServiceDep) -> WatchlistRead:
    return to_watchlist_read(await service.create(payload))


@router.get("/{watchlist_id}", response_model=WatchlistDetail)
async def read_watchlist(
    watchlist_id: UUID,
    service: WatchlistServiceDep,
    companies: CompanyServiceDep,
    topics: TopicServiceDep,
    sources: SourceServiceDep,
) -> WatchlistDetail:
    return await _detail(await service.get(watchlist_id), companies, topics, sources)


@router.patch("/{watchlist_id}", response_model=WatchlistRead)
async def update_watchlist(
    watchlist_id: UUID, payload: WatchlistUpdate, service: WatchlistServiceDep
) -> WatchlistRead:
    return to_watchlist_read(await service.update(watchlist_id, payload))


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(watchlist_id: UUID, service: WatchlistServiceDep) -> None:
    await service.delete(watchlist_id)


@router.put("/{watchlist_id}/{member_kind}/{member_id}", response_model=WatchlistDetail)
async def add_watchlist_member(
    watchlist_id: UUID,
    member_kind: MemberKind,
    member_id: UUID,
    service: WatchlistServiceDep,
    companies: CompanyServiceDep,
    topics: TopicServiceDep,
    sources: SourceServiceDep,
) -> WatchlistDetail:
    watchlist = await service.add_member(watchlist_id, member_kind, member_id)
    return await _detail(watchlist, companies, topics, sources)


@router.delete("/{watchlist_id}/{member_kind}/{member_id}", response_model=WatchlistDetail)
async def remove_watchlist_member(
    watchlist_id: UUID,
    member_kind: MemberKind,
    member_id: UUID,
    service: WatchlistServiceDep,
    companies: CompanyServiceDep,
    topics: TopicServiceDep,
    sources: SourceServiceDep,
) -> WatchlistDetail:
    watchlist = await service.remove_member(watchlist_id, member_kind, member_id)
    return await _detail(watchlist, companies, topics, sources)
