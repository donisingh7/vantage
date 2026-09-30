"""One-request read for the Watchlists page's first render: the watchlist list, the narrow
catalogs its member selectors need, and the default watchlist's full detail -- replacing
Promise.all(GET /watchlists, GET /companies, GET /topics, GET /sources) followed by a
separate GET /watchlists/{id} for the first selection.

Reuses WatchlistService/CompanyService/TopicService/SourceService for the watchlist list and
the default watchlist's detail (so counts/membership logic can't drift from the existing
single-watchlist endpoints), but queries the three catalogs directly and narrowly (id/name
only, id/name/url for sources) rather than loading full Company/Topic/Source rows just to
populate a selector.
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, Source, Topic
from app.schemas.common import CatalogEntryRead, CatalogSourceRead
from app.schemas.watchlists import WatchlistDetail, WatchlistRead
from app.services.companies import CompanyService
from app.services.sources import SourceService
from app.services.topics import TopicService
from app.services.watchlists import WatchlistService


class WatchlistBootstrapData:
    def __init__(
        self,
        watchlists: list[WatchlistRead],
        companies: list[CatalogEntryRead],
        topics: list[CatalogEntryRead],
        sources: list[CatalogSourceRead],
        initial_detail: WatchlistDetail | None,
    ) -> None:
        self.watchlists = watchlists
        self.companies = companies
        self.topics = topics
        self.sources = sources
        self.initial_detail = initial_detail


class WatchlistBootstrapService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.watchlists = WatchlistService(session, workspace_id)
        self.companies = CompanyService(session, workspace_id)
        self.topics = TopicService(session, workspace_id)
        self.sources = SourceService(session, workspace_id)

    async def bootstrap(self) -> WatchlistBootstrapData:
        from app.api.serialization import to_watchlist_detail, to_watchlist_read

        watchlists = await self.watchlists.list()
        watchlist_reads = [to_watchlist_read(watchlist) for watchlist in watchlists]

        companies = await self._catalog_entries(Company)
        topics = await self._catalog_entries(Topic)
        sources = await self._source_catalog()

        initial_detail: WatchlistDetail | None = None
        if watchlists:
            # watchlists[0]'s companies/topics/sources are already eager-loaded (the Watchlist
            # model's relationships use lazy="selectin"), so no extra fetch-by-id is needed here.
            default_watchlist = watchlists[0]
            initial_detail = to_watchlist_detail(
                default_watchlist,
                await self.companies.watchlist_counts([company.id for company in default_watchlist.companies]),
                await self.topics.watchlist_counts([topic.id for topic in default_watchlist.topics]),
                await self.sources.watchlist_counts([source.id for source in default_watchlist.sources]),
            )

        return WatchlistBootstrapData(
            watchlists=watchlist_reads, companies=companies, topics=topics, sources=sources,
            initial_detail=initial_detail,
        )

    async def _catalog_entries(self, model: type[Company] | type[Topic]) -> list[CatalogEntryRead]:
        statement = (
            select(model.id, model.name).where(model.workspace_id == self.workspace_id).order_by(func.lower(model.name))
        )
        rows = (await self.session.execute(statement)).all()
        return [CatalogEntryRead(id=row.id, name=row.name) for row in rows]

    async def _source_catalog(self) -> list[CatalogSourceRead]:
        statement = (
            select(Source.id, Source.name, Source.url)
            .where(Source.workspace_id == self.workspace_id)
            .order_by(func.lower(Source.name))
        )
        rows = (await self.session.execute(statement)).all()
        return [CatalogSourceRead(id=row.id, name=row.name, url=row.url) for row in rows]
