from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.models import MemberRole, User, Workspace, WorkspaceMember


@dataclass(frozen=True)
class WorkspaceContext:
    user: User
    workspace: Workspace
    role: MemberRole


async def _get_or_create_user(session: AsyncSession, current_user: CurrentUser) -> User:
    existing = (
        await session.execute(select(User).where(User.email == current_user.email))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    user = User(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def resolve_workspace_context(
    session: AsyncSession, current_user: CurrentUser, settings: Settings
) -> WorkspaceContext:
    """Development identity always resolves to its own workspace, created once on first use."""
    user = await _get_or_create_user(session, current_user)
    workspace = (
        await session.execute(select(Workspace).where(Workspace.slug == settings.dev_workspace_slug))
    ).scalar_one_or_none()
    if workspace is None:
        workspace = Workspace(
            name=settings.dev_workspace_name,
            slug=settings.dev_workspace_slug,
            created_by=user.id,
        )
        session.add(workspace)
        await session.flush()

    membership = (
        await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=MemberRole.OWNER)
        session.add(membership)
        await session.flush()

    await session.commit()
    return WorkspaceContext(user=user, workspace=workspace, role=membership.role)


async def list_workspaces_for_user(session: AsyncSession, user_id) -> list[Workspace]:
    statement = (
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.name)
    )
    return list((await session.execute(statement)).scalars().all())


async def get_workspace_for_user(session: AsyncSession, user_id, workspace_id) -> Workspace:
    statement = (
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id, Workspace.id == workspace_id)
    )
    workspace = (await session.execute(statement)).scalar_one_or_none()
    if workspace is None:
        raise NotFoundError("Workspace was not found")
    return workspace
