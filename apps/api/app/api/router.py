from fastapi import APIRouter

from app.api.routes import (
    ask,
    companies,
    documents,
    ingestion,
    intelligence,
    search,
    sources,
    system,
    topics,
    watchlists,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(workspaces.router, tags=["workspace"])
api_router.include_router(watchlists.router)
api_router.include_router(companies.router)
api_router.include_router(topics.router)
api_router.include_router(sources.router)
api_router.include_router(ingestion.router)
api_router.include_router(documents.router)
api_router.include_router(intelligence.router)
api_router.include_router(search.router)
api_router.include_router(ask.router)
