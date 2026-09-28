import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes.system import ready
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db.session import SessionFactory
from app.services.scheduler import IngestionScheduler

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("vantage")
scheduler = IngestionScheduler(
    SessionFactory, enabled=settings.enable_scheduler, interval_seconds=settings.scheduler_interval_seconds
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug and settings.app_env == "development",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.app_env != "production" else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(settings.frontend_url).rstrip("/")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)
app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)
app.add_api_route("/ready", ready, methods=["GET"], tags=["system"])


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
