"""Read-only, workspace-scoped bootstrap data for the Overview dashboard.

Deliberately has no dependency on LLMProvider/EmbeddingProvider: this only reads
already-persisted rows (summary counts, signals, crawl jobs), so constructing a
Gemini/Azure client here -- the way IntelligenceAnalysisService normally requires for its
write path -- would be pure dead weight on a read that never generates or analyzes
anything. Provider *names* (for the `providers` field in the response) come from Settings,
not from a constructed provider instance.

Query strategy -- every query below is either LIMITed or a database-side aggregate; nothing
here materializes a workspace's full signal history into Python:

1. One combined scalar-subquery SELECT for the six summary counts.
2. Two small ORDER BY ... LIMIT 3 queries for priority_signals and latest_signals -- the
   only two places the response needs full IntelligenceSignal rows, so those two queries
   are the only ones that fetch full rows, and each is capped at 3.
3. Two GROUP BY aggregate queries (signal_type, sentiment) that return only (key, count)
   pairs -- COUNT(*) executes in the database, not by loading and counting rows in Python.
4. Two GROUP BY + INNER JOIN aggregate queries (Company, Topic) that return only
   (id, name, count), each ORDER BY count DESC LIMIT 3 at the database level -- never the
   full Company/Topic table, and no N+1 per-entity lookup.
5. One join query for the 5 most recent crawl jobs with their source name.

That is 8 targeted, workspace-scoped, bounded/aggregate queries in one DB session -- not a
single unreadable mega-query, and not an unbounded fetch that grows with signal history.
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisStatus,
    Company,
    CrawlJob,
    IntelligenceSignal,
    Source,
    Topic,
    Watchlist,
)

PRIORITY_SIGNAL_LIMIT = 3
LATEST_SIGNAL_LIMIT = 3
FOCUS_ENTITY_LIMIT = 3
RECENT_JOB_LIMIT = 5

DEFAULT_SIGNAL_TYPE = "other"
DEFAULT_SENTIMENT = "neutral"


@dataclass(frozen=True)
class DashboardSummary:
    watchlists: int
    companies: int
    topics: int
    sources: int
    active_watchlists: int
    active_sources: int


@dataclass(frozen=True)
class KeyCount:
    key: str
    count: int


@dataclass(frozen=True)
class RecentJob:
    job: CrawlJob
    source_name: str


@dataclass(frozen=True)
class FocusEntity:
    id: UUID
    name: str
    count: int


@dataclass(frozen=True)
class DashboardOverview:
    summary: DashboardSummary
    priority_signals: list[IntelligenceSignal]
    latest_signals: list[IntelligenceSignal]
    signal_type_counts: list[KeyCount]
    sentiment_counts: list[KeyCount]
    recent_jobs: list[RecentJob]
    focus_companies: list[FocusEntity]
    focus_topics: list[FocusEntity]


class DashboardService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self.session = session
        self.workspace_id = workspace_id

    async def overview(self) -> DashboardOverview:
        summary = await self._summary()
        priority_signals = await self._priority_signals()
        latest_signals = await self._latest_signals()
        signal_type_counts = await self._grouped_counts(IntelligenceSignal.signal_type, DEFAULT_SIGNAL_TYPE)
        sentiment_counts = await self._grouped_counts(IntelligenceSignal.sentiment, DEFAULT_SENTIMENT)
        recent_jobs = await self._recent_jobs()
        focus_companies = await self._focus_entities(Company, IntelligenceSignal.company_id)
        focus_topics = await self._focus_entities(Topic, IntelligenceSignal.topic_id)

        return DashboardOverview(
            summary=summary,
            priority_signals=priority_signals,
            latest_signals=latest_signals,
            signal_type_counts=signal_type_counts,
            sentiment_counts=sentiment_counts,
            recent_jobs=recent_jobs,
            focus_companies=focus_companies,
            focus_topics=focus_topics,
        )

    async def _summary(self) -> DashboardSummary:
        def _count(model) -> Select:
            return select(func.count()).select_from(model).where(model.workspace_id == self.workspace_id)

        def _active_count(model) -> Select:
            return select(func.coalesce(func.sum(case((model.is_active, 1), else_=0)), 0)).where(
                model.workspace_id == self.workspace_id
            )

        statement = select(
            _count(Watchlist).scalar_subquery().label("watchlists"),
            _active_count(Watchlist).scalar_subquery().label("active_watchlists"),
            _count(Company).scalar_subquery().label("companies"),
            _count(Topic).scalar_subquery().label("topics"),
            _count(Source).scalar_subquery().label("sources"),
            _active_count(Source).scalar_subquery().label("active_sources"),
        )
        row = (await self.session.execute(statement)).one()
        return DashboardSummary(
            watchlists=int(row.watchlists),
            companies=int(row.companies),
            topics=int(row.topics),
            sources=int(row.sources),
            active_watchlists=int(row.active_watchlists),
            active_sources=int(row.active_sources),
        )

    def _completed_signal_filter(self):
        return (
            IntelligenceSignal.workspace_id == self.workspace_id,
            IntelligenceSignal.analysis_status == AnalysisStatus.COMPLETED,
        )

    async def _priority_signals(self) -> list[IntelligenceSignal]:
        statement = (
            select(IntelligenceSignal)
            .where(*self._completed_signal_filter())
            .order_by(
                IntelligenceSignal.importance_score.desc(),
                IntelligenceSignal.analyzed_at.desc(),
                IntelligenceSignal.id.desc(),
            )
            .limit(PRIORITY_SIGNAL_LIMIT)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def _latest_signals(self) -> list[IntelligenceSignal]:
        statement = (
            select(IntelligenceSignal)
            .where(*self._completed_signal_filter())
            .order_by(IntelligenceSignal.analyzed_at.desc(), IntelligenceSignal.id.desc())
            .limit(LATEST_SIGNAL_LIMIT)
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def _grouped_counts(self, column, default_key: str) -> list[KeyCount]:
        """COUNT(*) ... GROUP BY column, executed in the database -- never loads full rows.

        `column` (signal_type/sentiment) is nullable, so a plain SQL GROUP BY can produce a
        NULL group alongside a real "other"/"neutral" group; both are merged into one key
        here rather than relying on database-specific COALESCE-of-an-enum behavior.
        """
        statement = select(column, func.count()).where(*self._completed_signal_filter()).group_by(column)
        rows = (await self.session.execute(statement)).all()

        merged: dict[str, int] = {}
        for raw_key, count in rows:
            key = raw_key.value if raw_key is not None else default_key
            merged[key] = merged.get(key, 0) + int(count)

        ordered = sorted(merged.items(), key=lambda pair: (-pair[1], pair[0]))
        return [KeyCount(key=key, count=count) for key, count in ordered]

    async def _recent_jobs(self) -> list[RecentJob]:
        statement = (
            select(CrawlJob, Source.name)
            .outerjoin(Source, Source.id == CrawlJob.source_id)
            .where(CrawlJob.workspace_id == self.workspace_id)
            .order_by(CrawlJob.created_at.desc())
            .limit(RECENT_JOB_LIMIT)
        )
        rows = (await self.session.execute(statement)).all()
        return [RecentJob(job=job, source_name=source_name or "Unknown source") for job, source_name in rows]

    async def _focus_entities(self, model: type[Company] | type[Topic], signal_field) -> list[FocusEntity]:
        """Top `FOCUS_ENTITY_LIMIT` entities by linked completed-signal count.

        The INNER JOIN to `model` on `signal_field` already excludes signals with no linked
        entity (a NULL company_id/topic_id can never match `model.id`), and the count/order
        happen entirely in SQL -- this never loads the full Company/Topic table or the full
        signal history to compute a ranking client-side.
        """
        statement = (
            select(model.id, model.name, func.count(IntelligenceSignal.id))
            .select_from(IntelligenceSignal)
            .join(model, model.id == signal_field)
            .where(*self._completed_signal_filter(), model.workspace_id == self.workspace_id)
            .group_by(model.id, model.name)
            .order_by(func.count(IntelligenceSignal.id).desc(), model.id.asc())
            .limit(FOCUS_ENTITY_LIMIT)
        )
        rows = (await self.session.execute(statement)).all()
        return [FocusEntity(id=row[0], name=row[1], count=int(row[2])) for row in rows]
