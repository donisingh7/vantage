from typing import Literal
from uuid import UUID

from sqlalchemy import func, select

from app.models import Company, Topic, Watchlist
from app.schemas.watchlists import WatchlistCreate, WatchlistUpdate
from app.services.base import WorkspaceResourceService
from app.services.companies import CompanyService
from app.services.sources import SourceService
from app.services.topics import TopicService

MemberKind = Literal["companies", "topics", "sources"]
MEMBER_SERVICES = {"companies": CompanyService, "topics": TopicService, "sources": SourceService}


class WatchlistService(WorkspaceResourceService[Watchlist]):
    model = Watchlist
    label = "Watchlist"
    search_fields = ("name",)

    async def create(self, payload: WatchlistCreate) -> Watchlist:
        await self.ensure_unique(
            "name", payload.name, message="A watchlist with this name already exists in this workspace"
        )
        watchlist = Watchlist(workspace_id=self.workspace_id, **payload.model_dump())
        await self.repository.add(watchlist)
        await self.session.commit()
        return await self.get(watchlist.id)

    async def update(self, watchlist_id: UUID, payload: WatchlistUpdate) -> Watchlist:
        watchlist = await self.get(watchlist_id)
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes:
            await self.ensure_unique(
                "name",
                changes["name"],
                message="A watchlist with this name already exists in this workspace",
                exclude_id=watchlist_id,
            )
        self.apply_changes(watchlist, changes)
        await self.session.commit()
        return watchlist

    async def list_containing(
        self, *, company_id: UUID | None = None, topic_id: UUID | None = None
    ) -> list[Watchlist]:
        """Watchlists containing a given company/topic, in one query -- avoids an N+1 detail fetch."""
        statement = select(Watchlist).where(Watchlist.workspace_id == self.workspace_id)
        if company_id is not None:
            statement = statement.where(Watchlist.companies.any(Company.id == company_id))
        if topic_id is not None:
            statement = statement.where(Watchlist.topics.any(Topic.id == topic_id))
        statement = statement.order_by(func.lower(Watchlist.name))
        return list((await self.session.execute(statement)).scalars().unique().all())

    async def count_active(self) -> int:
        watchlists = await self.list()
        return sum(1 for watchlist in watchlists if watchlist.is_active)

    async def add_member(self, watchlist_id: UUID, kind: MemberKind, member_id: UUID) -> Watchlist:
        watchlist = await self.get(watchlist_id)
        member = await MEMBER_SERVICES[kind](self.session, self.workspace_id).get(member_id)
        members = getattr(watchlist, kind)
        if all(existing.id != member.id for existing in members):
            members.append(member)
            await self.session.commit()
        return await self.get(watchlist_id)

    async def remove_member(self, watchlist_id: UUID, kind: MemberKind, member_id: UUID) -> Watchlist:
        watchlist = await self.get(watchlist_id)
        member = await MEMBER_SERVICES[kind](self.session, self.workspace_id).get(member_id)
        members = getattr(watchlist, kind)
        remaining = [existing for existing in members if existing.id != member.id]
        if len(remaining) != len(members):
            setattr(watchlist, kind, remaining)
            await self.session.commit()
        return await self.get(watchlist_id)
