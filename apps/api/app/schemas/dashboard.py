from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ProviderInfo
from app.schemas.ingestion import CrawlJobRead
from app.schemas.intelligence import IntelligenceSignalRead

__all__ = [
    "DashboardOverviewResponse",
    "DashboardSummaryRead",
    "FocusEntityRead",
    "KeyCountRead",
    "ProviderInfo",
    "RecentJobRead",
]


class DashboardSummaryRead(BaseModel):
    watchlists: int
    companies: int
    topics: int
    sources: int
    active_watchlists: int
    active_sources: int


class KeyCountRead(BaseModel):
    key: str
    count: int


class RecentJobRead(CrawlJobRead):
    source_name: str


class FocusEntityRead(BaseModel):
    id: UUID
    name: str
    count: int


class DashboardOverviewResponse(BaseModel):
    providers: ProviderInfo
    summary: DashboardSummaryRead
    priority_signals: list[IntelligenceSignalRead]
    latest_signals: list[IntelligenceSignalRead]
    signal_type_counts: list[KeyCountRead]
    sentiment_counts: list[KeyCountRead]
    recent_jobs: list[RecentJobRead]
    focus_companies: list[FocusEntityRead]
    focus_topics: list[FocusEntityRead]
