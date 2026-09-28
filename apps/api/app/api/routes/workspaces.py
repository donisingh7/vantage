from uuid import UUID

from fastapi import APIRouter

from app.api.deps import (
    CompanyServiceDep,
    SessionDep,
    SourceServiceDep,
    TopicServiceDep,
    WatchlistServiceDep,
    WorkspaceContextDep,
)
from app.schemas.identity import CurrentIdentity, WorkspaceRead, WorkspaceSummary
from app.services.workspace import get_workspace_for_user, list_workspaces_for_user

router = APIRouter()


@router.get("/me", response_model=CurrentIdentity)
async def read_current_identity(context: WorkspaceContextDep) -> CurrentIdentity:
    return CurrentIdentity(user=context.user, workspace=context.workspace, role=context.role.value)


@router.get("/workspaces", response_model=list[WorkspaceRead])
async def list_workspaces(session: SessionDep, context: WorkspaceContextDep) -> list[WorkspaceRead]:
    workspaces = await list_workspaces_for_user(session, context.user.id)
    return [WorkspaceRead.model_validate(workspace) for workspace in workspaces]


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceRead)
async def read_workspace(
    workspace_id: UUID, session: SessionDep, context: WorkspaceContextDep
) -> WorkspaceRead:
    workspace = await get_workspace_for_user(session, context.user.id, workspace_id)
    return WorkspaceRead.model_validate(workspace)


@router.get("/workspace/summary", response_model=WorkspaceSummary)
async def read_workspace_summary(
    watchlists: WatchlistServiceDep,
    companies: CompanyServiceDep,
    topics: TopicServiceDep,
    sources: SourceServiceDep,
) -> WorkspaceSummary:
    all_watchlists = await watchlists.list()
    all_sources = await sources.list()
    return WorkspaceSummary(
        watchlists=len(all_watchlists),
        companies=await companies.count(),
        topics=await topics.count(),
        sources=len(all_sources),
        active_watchlists=sum(1 for watchlist in all_watchlists if watchlist.is_active),
        active_sources=sum(1 for source in all_sources if source.is_active),
    )
