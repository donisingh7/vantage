"""Read-only, workspace-scoped bootstrap data for the Overview dashboard.

Deliberately has no dependency on LLMProvider/EmbeddingProvider: this only reads
already-persisted rows (summary counts, completed signals, crawl jobs), so constructing a
Gemini/Azure client here -- the way IntelligenceAnalysisService normally requires for its
write path -- would be pure dead weight on a read that never generates or analyzes
anything. Provider *names* (for the `providers` field in the response) come from Settings,
not from a constructed provider instance.

Query strategy: one combined scalar-subquery SELECT for the six summary counts, one bounded
fetch of this workspace's completed signals (priority/latest/type-counts/sentiment-counts/
focus-entity-ids are all derived from that single list in Python rather than five separate
aggregate queries), up to two small targeted lookups for the focus companies'/topics' names
(bounded to the top 3 ids each -- never the full Company/Topic table), and one join query
for the most recent crawl jobs with their source name. That is a handful of targeted,
workspace-scoped queries -- not sequential N+1 traversal, and not full-table loads used
merely to build a lookup map.
"""
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import case, func, select
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


def _counted(items: Sequence[IntelligenceSignal], key_of: Callable[[IntelligenceSignal], str]) -> list[KeyCount]:
    """Groups by `key_of`, then orders deterministically: highest count first, key A-Z on ties."""
    counts = Counter(key_of(item) for item in items)
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [KeyCount(key=key, count=count) for key, count in ordered]


class DashboardService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self.session = session
        self.workspace_id = workspace_id

    async def overview(self) -> DashboardOverview:
        summary = await self._summary()
        signals = await self._completed_signals()
        recent_jobs = await self._recent_jobs()

        # Both sorts add signal id as a final tie-break so ordering never depends on
        # incidental row-fetch order when scores/timestamps are exactly equal.
        priority_signals = sorted(
            signals, key=lambda signal: (signal.importance_score, signal.analyzed_at, str(signal.id)), reverse=True
        )[:PRIORITY_SIGNAL_LIMIT]
        latest_signals = sorted(
            signals, key=lambda signal: (signal.analyzed_at, str(signal.id)), reverse=True
        )[:LATEST_SIGNAL_LIMIT]

        signal_type_counts = _counted(
            signals, lambda signal: signal.signal_type.value if signal.signal_type else DEFAULT_SIGNAL_TYPE
        )
        sentiment_counts = _counted(
            signals, lambda signal: signal.sentiment.value if signal.sentiment else DEFAULT_SENTIMENT
        )

        focus_companies = await self._focus_entities(Company, signals, "company_id")
        focus_topics = await self._focus_entities(Topic, signals, "topic_id")

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
        def _count(model):
            return select(func.count()).select_from(model).where(model.workspace_id == self.workspace_id)

        def _active_count(model):
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

    async def _completed_signals(self) -> list[IntelligenceSignal]:
        statement = select(IntelligenceSignal).where(
            IntelligenceSignal.workspace_id == self.workspace_id,
            IntelligenceSignal.analysis_status == AnalysisStatus.COMPLETED,
        )
        return list((await self.session.execute(statement)).scalars().all())

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

    async def _focus_entities(
        self, model: type[Company] | type[Topic], signals: Sequence[IntelligenceSignal], field: str
    ) -> list[FocusEntity]:
        counts = Counter(getattr(signal, field) for signal in signals if getattr(signal, field) is not None)
        if not counts:
            return []
        top_ids = [entity_id for entity_id, _ in sorted(counts.items(), key=lambda pair: (-pair[1], str(pair[0])))][
            :FOCUS_ENTITY_LIMIT
        ]
        statement = select(model.id, model.name).where(model.workspace_id == self.workspace_id, model.id.in_(top_ids))
        names = {row.id: row.name for row in (await self.session.execute(statement)).all()}
        return [
            FocusEntity(id=entity_id, name=names[entity_id], count=counts[entity_id])
            for entity_id in top_ids
            if entity_id in names
        ]
