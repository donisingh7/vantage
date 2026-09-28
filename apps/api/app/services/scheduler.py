"""Lightweight in-process scheduling for periodic source ingestion.

No Redis, no Celery, no distributed workers: a single AsyncIOScheduler tick
looks for active sources whose configured interval has elapsed and runs them
in this same process, reusing IngestionService's own overlap guard.
"""
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import ConflictError
from app.models import CrawlJob, IngestionInterval, Source
from app.services.fetching import HttpxSourceFetcher
from app.services.ingestion import IngestionService

INGESTION_INTERVAL_MINUTES: dict[IngestionInterval, int | None] = {
    IngestionInterval.MANUAL: None,
    IngestionInterval.EVERY_6_HOURS: 360,
    IngestionInterval.EVERY_12_HOURS: 720,
    IngestionInterval.EVERY_24_HOURS: 1440,
}


def should_enable_scheduler(*, enable_scheduler: bool, app_env: str) -> bool:
    """Explicit, unit-testable gate: the scheduler never runs in test mode, even if misconfigured."""
    return enable_scheduler and app_env != "test"


def is_due(source: Source, last_job: CrawlJob | None, *, now: datetime) -> bool:
    """Pure scheduling decision, independent of any timer, so it is easy to unit test."""
    minutes = INGESTION_INTERVAL_MINUTES.get(source.ingestion_interval)
    if not source.is_active or minutes is None:
        return False
    if last_job is None:
        return True
    reference = last_job.completed_at or last_job.started_at or last_job.created_at
    return now - reference >= timedelta(minutes=minutes)


async def _latest_job_by_source(session: AsyncSession) -> dict:
    statement = select(CrawlJob).order_by(CrawlJob.source_id, CrawlJob.created_at.desc())
    latest: dict = {}
    for job in (await session.execute(statement)).scalars().all():
        latest.setdefault(job.source_id, job)
    return latest


async def run_due_ingestions(session: AsyncSession, *, now: datetime | None = None) -> list[Source]:
    """Runs ingestion for every active, scheduled source whose interval has elapsed.

    Returns the sources it attempted. A source already mid-run is skipped, not failed.
    """
    reference_time = now or datetime.now(UTC)
    sources = (await session.execute(select(Source).where(Source.is_active.is_(True)))).scalars().all()
    latest_jobs = await _latest_job_by_source(session)

    attempted: list[Source] = []
    for source in sources:
        if not is_due(source, latest_jobs.get(source.id), now=reference_time):
            continue
        attempted.append(source)
        service = IngestionService(session, source.workspace_id, HttpxSourceFetcher())
        try:
            await service.run(source.id)
        except ConflictError:
            continue
    return attempted


class IngestionScheduler:
    """Thin wrapper around APScheduler's AsyncIOScheduler; a safe no-op when disabled."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | Callable[[], AsyncSession],
        *,
        enabled: bool,
        interval_seconds: int = 60,
    ) -> None:
        self._session_factory = session_factory
        self._enabled = enabled
        self._interval_seconds = interval_seconds
        self._scheduler = None

    def start(self) -> None:
        if not self._enabled or self._scheduler is not None:
            return
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            self._tick,
            "interval",
            seconds=self._interval_seconds,
            id="vantage-ingestion-scheduler",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        self._scheduler = scheduler

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    @property
    def is_running(self) -> bool:
        return self._scheduler is not None

    async def _tick(self) -> None:
        async with self._session_factory() as session:
            await run_due_ingestions(session)
