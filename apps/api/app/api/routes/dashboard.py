from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep, WorkspaceContextDep
from app.core.config import Settings, get_settings
from app.schemas.dashboard import (
    DashboardOverviewResponse,
    DashboardSummaryRead,
    FocusEntityRead,
    KeyCountRead,
    ProviderInfo,
    RecentJobRead,
)
from app.schemas.ingestion import CrawlJobRead
from app.schemas.intelligence import IntelligenceSignalRead
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverviewResponse)
async def read_dashboard_overview(
    session: SessionDep,
    context: WorkspaceContextDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DashboardOverviewResponse:
    """One request replacing the seven the browser previously made for the Overview page.

    Deliberately takes no LLM/embedding provider dependency -- see DashboardService's
    module docstring for why that would be pure dead weight on this read-only path.
    """
    data = await DashboardService(session, context.workspace.id).overview()
    return DashboardOverviewResponse(
        providers=ProviderInfo(llm_provider=settings.llm_provider, embedding_provider=settings.embedding_provider),
        summary=DashboardSummaryRead(
            watchlists=data.summary.watchlists,
            companies=data.summary.companies,
            topics=data.summary.topics,
            sources=data.summary.sources,
            active_watchlists=data.summary.active_watchlists,
            active_sources=data.summary.active_sources,
        ),
        priority_signals=[IntelligenceSignalRead.model_validate(signal) for signal in data.priority_signals],
        latest_signals=[IntelligenceSignalRead.model_validate(signal) for signal in data.latest_signals],
        signal_type_counts=[KeyCountRead(key=item.key, count=item.count) for item in data.signal_type_counts],
        sentiment_counts=[KeyCountRead(key=item.key, count=item.count) for item in data.sentiment_counts],
        recent_jobs=[
            RecentJobRead(**CrawlJobRead.model_validate(item.job).model_dump(), source_name=item.source_name)
            for item in data.recent_jobs
        ],
        focus_companies=[
            FocusEntityRead(id=item.id, name=item.name, count=item.count) for item in data.focus_companies
        ],
        focus_topics=[FocusEntityRead(id=item.id, name=item.name, count=item.count) for item in data.focus_topics],
    )
