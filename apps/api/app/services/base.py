from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.db.base import Base
from app.repositories.base import WorkspaceScopedRepository


class WorkspaceResourceService[ModelT: Base]:
    """Shared workspace-scoped behaviour for the CRUD resources."""

    model: type[ModelT]
    label: str = "Record"
    search_fields: tuple[str, ...] = ("name",)
    link_table: Table | None = None
    link_column: str = ""

    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.repository = WorkspaceScopedRepository(session, self.model, workspace_id)

    async def list(self, search: str | None = None) -> Sequence[ModelT]:
        return await self.repository.list(search=search, search_fields=self.search_fields)

    async def get(self, entity_id: UUID) -> ModelT:
        entity = await self.repository.get(entity_id)
        if entity is None:
            raise NotFoundError(f"{self.label} was not found in this workspace")
        return entity

    async def count(self) -> int:
        return await self.repository.count()

    async def delete(self, entity_id: UUID) -> None:
        entity = await self.get(entity_id)
        await self.repository.delete(entity)
        await self.session.commit()

    async def watchlist_counts(self, entity_ids: Sequence[UUID]) -> dict[UUID, int]:
        if self.link_table is None or not entity_ids:
            return {}
        column = self.link_table.c[self.link_column]
        statement = select(column, func.count()).where(column.in_(entity_ids)).group_by(column)
        return {row[0]: int(row[1]) for row in (await self.session.execute(statement)).all()}

    async def ensure_unique(
        self, field: str, value: Any, *, message: str, exclude_id: UUID | None = None
    ) -> None:
        if value is None:
            return
        existing = await self.repository.find_by(exclude_id=exclude_id, **{field: value})
        if existing is not None:
            raise ConflictError(message)

    @staticmethod
    def apply_changes(entity: ModelT, changes: dict[str, Any]) -> ModelT:
        for field, value in changes.items():
            setattr(entity, field, value)
        return entity
