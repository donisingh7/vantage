from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


def is_sqlite(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def ensure_sqlite_directory(database_url: str) -> None:
    database_path = urlsplit(database_url).path.lstrip("/")
    if database_path and database_path != ":memory:":
        Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """SQLite ignores foreign keys, including cascade deletes, unless enabled per connection."""

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_engine(database_url: str) -> AsyncEngine:
    if is_sqlite(database_url):
        ensure_sqlite_directory(database_url)
        engine = create_async_engine(database_url)
        enable_sqlite_foreign_keys(engine)
        return engine
    return create_async_engine(database_url, pool_pre_ping=True)


engine = create_engine(get_settings().database_url)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
