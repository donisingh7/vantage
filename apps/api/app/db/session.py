from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


def is_sqlite(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def is_postgres(database_url: str) -> bool:
    return database_url.startswith("postgresql")


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


def create_engine(database_url: str, *, serverless: bool = False) -> AsyncEngine:
    if is_sqlite(database_url):
        ensure_sqlite_directory(database_url)
        engine = create_async_engine(database_url)
        enable_sqlite_foreign_keys(engine)
        return engine

    if is_postgres(database_url) and serverless:
        # DATABASE_SERVERLESS=true means "this process is serverless/autoscaling (e.g. AWS
        # Lambda), so don't keep a persistent client-side connection pool" -- a Lambda
        # invocation is short-lived and instances scale independently, so a normal
        # SQLAlchemy pool just accumulates idle/stale connections. NullPool opens a fresh
        # connection per checkout and closes it on release instead. That is the entire scope
        # of this flag: it says nothing about prepared statements or pooling *mode* on the
        # database side.
        #
        # The intended production endpoint is Supabase's SESSION pooler (or a direct
        # connection) on port 5432, not its transaction pooler. A session pooler keeps one
        # backend session per checked-out connection for the checkout's lifetime, so
        # SQLAlchemy's asyncpg dialect and its server-side prepared statements work
        # normally -- this repo does not disable asyncpg's statement cache and does not
        # claim transaction-pooler compatibility (a transaction pooler hands out a
        # different backend connection per query/transaction, which breaks prepared
        # statements; that mode remains unsupported here).
        #
        # ssl="require" tells asyncpg to require an encrypted connection without validating
        # the server's certificate -- equivalent in intent to PostgreSQL's sslmode=require.
        # It does NOT perform CA or hostname verification (unlike ssl=True, which builds a
        # default *validating* SSLContext and fails against Supabase's certificate chain
        # with SSLCertVerificationError). A stronger sslmode=verify-full, pinned to
        # Supabase's CA certificate, could be added later as a separate hardening step; it
        # is not done here. No hostname, project ID, or credentials are referenced in this
        # module -- this is plain SQLAlchemy/asyncpg configuration, not provider-specific.
        return create_async_engine(
            database_url,
            poolclass=NullPool,
            connect_args={"ssl": "require"},
        )

    return create_async_engine(database_url, pool_pre_ping=True)


engine = create_engine(get_settings().database_url, serverless=get_settings().database_serverless)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
