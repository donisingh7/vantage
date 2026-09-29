from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_embedding_provider, get_llm_provider
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys, get_db_session
from app.main import app
from app.models import MemberRole, User, Workspace, WorkspaceMember
from app.providers.embeddings import MockEmbeddingProvider
from app.providers.llm import MockLLMProvider


@pytest.fixture
async def sessions(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    enable_sqlite_foreign_keys(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(sessions) -> AsyncIterator[AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    # Tests must be fully isolated from whatever real .env happens to exist locally (e.g.
    # one kept for production-config smoke testing, per app/db/session.py's serverless
    # tests) -- never a real LLM/embedding provider, real credentials, or even a
    # provider-name label derived from real settings. Force safe, deterministic settings
    # and mock providers for every test regardless of the ambient environment.
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    app.dependency_overrides[get_llm_provider] = lambda: MockLLMProvider()
    app.dependency_overrides[get_embedding_provider] = lambda: MockEmbeddingProvider(dimensions=16)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def other_workspace(sessions) -> Workspace:
    async with sessions() as session:
        user = User(id=uuid4(), email="outsider@example.local", display_name="Outsider")
        session.add(user)
        await session.flush()
        workspace = Workspace(name="Other Tenant", slug="other-tenant", created_by=user.id)
        session.add(workspace)
        await session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=MemberRole.OWNER))
        await session.commit()
        return workspace
