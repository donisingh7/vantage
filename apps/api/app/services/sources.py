from uuid import UUID

from app.models import Source, watchlist_sources
from app.schemas.sources import SourceCreate, SourceUpdate
from app.services.base import WorkspaceResourceService

DUPLICATE_URL_MESSAGE = "A source with this URL already exists in this workspace"


class SourceService(WorkspaceResourceService[Source]):
    model = Source
    label = "Source"
    search_fields = ("name", "url")
    link_table = watchlist_sources
    link_column = "source_id"

    async def create(self, payload: SourceCreate) -> Source:
        values = payload.model_dump()
        values["url"] = str(payload.url)
        await self.ensure_unique("url", values["url"], message=DUPLICATE_URL_MESSAGE)
        source = Source(workspace_id=self.workspace_id, **values)
        await self.repository.add(source)
        await self.session.commit()
        return source

    async def update(self, source_id: UUID, payload: SourceUpdate) -> Source:
        source = await self.get(source_id)
        changes = payload.model_dump(exclude_unset=True)
        if changes.get("url") is not None:
            changes["url"] = str(changes["url"])
            await self.ensure_unique(
                "url", changes["url"], message=DUPLICATE_URL_MESSAGE, exclude_id=source_id
            )
        self.apply_changes(source, changes)
        await self.session.commit()
        return source
