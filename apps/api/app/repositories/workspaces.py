from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Workspace


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, workspace_id: UUID) -> Workspace | None:
        return await self.session.get(Workspace, workspace_id)

    async def get_by_slug(self, slug: str) -> Workspace | None:
        result = await self.session.execute(select(Workspace).where(Workspace.slug == slug))
        return result.scalar_one_or_none()

    async def add(self, workspace: Workspace) -> Workspace:
        self.session.add(workspace)
        await self.session.flush()
        return workspace
