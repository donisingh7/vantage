from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base


class WorkspaceScopedRepository[ModelT: Base]:
    """Every query is constrained to one workspace, so entity ids alone never grant access."""

    def __init__(self, session: AsyncSession, model: type[ModelT], workspace_id: UUID) -> None:
        self.session = session
        self.model = model
        self.workspace_id = workspace_id

    def _scoped(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.workspace_id == self.workspace_id)

    async def list(self, *, search: str | None = None, search_fields: Sequence[str] = ()) -> Sequence[ModelT]:
        statement = self._scoped()
        if search and search_fields:
            pattern = f"%{search.strip().lower()}%"
            statement = statement.where(
                or_(*(func.lower(getattr(self.model, field)).like(pattern) for field in search_fields))
            )
        statement = statement.order_by(func.lower(self.model.name))
        return (await self.session.execute(statement)).scalars().unique().all()

    async def get(self, entity_id: UUID) -> ModelT | None:
        statement = self._scoped().where(self.model.id == entity_id)
        return (await self.session.execute(statement)).scalars().unique().one_or_none()

    async def count(self) -> int:
        statement = select(func.count()).select_from(self.model).where(
            self.model.workspace_id == self.workspace_id
        )
        return int((await self.session.execute(statement)).scalar_one())

    async def find_by(self, *, exclude_id: UUID | None = None, **filters: Any) -> ModelT | None:
        statement = self._scoped()
        for field, value in filters.items():
            statement = statement.where(getattr(self.model, field) == value)
        if exclude_id is not None:
            statement = statement.where(self.model.id != exclude_id)
        return (await self.session.execute(statement)).scalars().unique().first()

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()
