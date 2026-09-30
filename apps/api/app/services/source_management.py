"""One-request read for the Sources management page: each source plus its own latest
ingestion job, instead of GET /sources followed by GET /ingestion/jobs (full job history)
with the browser deriving "latest per source" client-side.

Latest-job resolution is done with a portable GROUP BY MAX(created_at) subquery joined back
to crawl_jobs on (source_id, created_at) -- no window functions, no database-specific SQL,
so this stays SQLite-compatible for tests. It is a single query; the browser never receives
full job history.
"""
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CrawlJob, Source


class SourceManagementService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self.session = session
        self.workspace_id = workspace_id

    async def list_with_latest_job(self, search: str | None = None) -> list[tuple[Source, CrawlJob | None]]:
        latest_per_source = (
            select(CrawlJob.source_id, func.max(CrawlJob.created_at).label("latest_created_at"))
            .where(CrawlJob.workspace_id == self.workspace_id)
            .group_by(CrawlJob.source_id)
            .subquery()
        )
        statement = (
            select(Source, CrawlJob)
            .outerjoin(latest_per_source, latest_per_source.c.source_id == Source.id)
            .outerjoin(
                CrawlJob,
                (CrawlJob.source_id == latest_per_source.c.source_id)
                & (CrawlJob.created_at == latest_per_source.c.latest_created_at)
                & (CrawlJob.workspace_id == self.workspace_id),
            )
            .where(Source.workspace_id == self.workspace_id)
        )
        if search and search.strip():
            pattern = f"%{search.strip().lower()}%"
            statement = statement.where(
                or_(func.lower(Source.name).like(pattern), func.lower(Source.url).like(pattern))
            )
        statement = statement.order_by(func.lower(Source.name))

        rows = (await self.session.execute(statement)).all()

        # A tie on created_at for the same source (two jobs in the same instant) is the only
        # way the join above could return more than one row per source; keep the first.
        seen: set[UUID] = set()
        result: list[tuple[Source, CrawlJob | None]] = []
        for source, job in rows:
            if source.id in seen:
                continue
            seen.add(source.id)
            result.append((source, job))
        return result
