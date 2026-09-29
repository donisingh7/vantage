from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.providers.embeddings import (
    AzureOpenAIEmbeddingProvider,
    EmbeddingProvider,
    GeminiEmbeddingProvider,
    MockEmbeddingProvider,
)
from app.providers.llm import (
    AzureOpenAILLMProvider,
    GeminiLLMProvider,
    LLMProvider,
    MockLLMProvider,
)
from app.services.ask_vantage import AskVantageService
from app.services.companies import CompanyService
from app.services.fetching import HttpxSourceFetcher, PlaywrightBrowserFetcher, SourceFetcher
from app.services.indexing import DocumentIndexingService
from app.services.ingestion import IngestionService
from app.services.intelligence_analysis import IntelligenceAnalysisService
from app.services.semantic_search import SemanticSearchService
from app.services.sources import SourceService
from app.services.topics import TopicService
from app.services.watchlists import WatchlistService
from app.services.workspace import WorkspaceContext, resolve_workspace_context

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_workspace_context(
    session: SessionDep,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkspaceContext:
    return await resolve_workspace_context(session, current_user, settings)


WorkspaceContextDep = Annotated[WorkspaceContext, Depends(get_workspace_context)]


def get_watchlist_service(session: SessionDep, context: WorkspaceContextDep) -> WatchlistService:
    return WatchlistService(session, context.workspace.id)


def get_company_service(session: SessionDep, context: WorkspaceContextDep) -> CompanyService:
    return CompanyService(session, context.workspace.id)


def get_topic_service(session: SessionDep, context: WorkspaceContextDep) -> TopicService:
    return TopicService(session, context.workspace.id)


def get_source_service(session: SessionDep, context: WorkspaceContextDep) -> SourceService:
    return SourceService(session, context.workspace.id)


def get_source_fetcher(settings: Annotated[Settings, Depends(get_settings)]) -> SourceFetcher:
    browser = PlaywrightBrowserFetcher() if settings.enable_browser_fallback else None
    return HttpxSourceFetcher(
        connect_timeout=settings.ingestion_connect_timeout_seconds,
        read_timeout=settings.ingestion_read_timeout_seconds,
        max_retries=settings.ingestion_max_retries,
        retry_backoff=settings.ingestion_retry_backoff_seconds,
        browser=browser,
        min_content_length_for_browser=settings.ingestion_min_content_length_for_browser,
    )


SourceFetcherDep = Annotated[SourceFetcher, Depends(get_source_fetcher)]


def get_ingestion_service(
    session: SessionDep,
    context: WorkspaceContextDep,
    fetcher: SourceFetcherDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> IngestionService:
    return IngestionService(
        session, context.workspace.id, fetcher, max_discovered_pages=settings.ingestion_max_discovered_pages
    )


def get_llm_provider(settings: Annotated[Settings, Depends(get_settings)]) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    if settings.llm_provider == "gemini":
        # Settings.validate_provider_configuration already guarantees this is set
        # whenever llm_provider == "gemini"; the assert below just satisfies typing.
        assert settings.gemini_api_key
        return GeminiLLMProvider(api_key=settings.gemini_api_key, model=settings.gemini_chat_model)
    # Settings.validate_provider_configuration already guarantees these are set
    # whenever llm_provider == "azure_openai"; str()/asserts below just satisfy typing.
    assert settings.azure_openai_endpoint and settings.azure_openai_api_key and settings.azure_openai_chat_deployment
    return AzureOpenAILLMProvider(
        endpoint=str(settings.azure_openai_endpoint),
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        chat_deployment=settings.azure_openai_chat_deployment,
    )


LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]


def get_intelligence_service(
    session: SessionDep, context: WorkspaceContextDep, llm: LLMProviderDep
) -> IntelligenceAnalysisService:
    return IntelligenceAnalysisService(session, context.workspace.id, llm)


def get_embedding_provider(settings: Annotated[Settings, Depends(get_settings)]) -> EmbeddingProvider:
    if settings.embedding_provider == "mock":
        return MockEmbeddingProvider(dimensions=settings.embedding_dimensions)
    if settings.embedding_provider == "gemini":
        assert settings.gemini_api_key
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_embedding_model,
            dimensions=settings.gemini_embedding_dimensions,
        )
    assert settings.azure_openai_endpoint and settings.azure_openai_api_key and settings.azure_openai_embedding_deployment
    return AzureOpenAIEmbeddingProvider(
        endpoint=str(settings.azure_openai_endpoint),
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        embedding_deployment=settings.azure_openai_embedding_deployment,
        dimensions=settings.azure_openai_embedding_dimensions,
    )


EmbeddingProviderDep = Annotated[EmbeddingProvider, Depends(get_embedding_provider)]


def get_indexing_service(
    session: SessionDep, context: WorkspaceContextDep, embeddings: EmbeddingProviderDep
) -> DocumentIndexingService:
    return DocumentIndexingService(session, context.workspace.id, embeddings)


def get_search_service(
    session: SessionDep, context: WorkspaceContextDep, embeddings: EmbeddingProviderDep
) -> SemanticSearchService:
    return SemanticSearchService(session, context.workspace.id, embeddings)


IndexingServiceDep = Annotated[DocumentIndexingService, Depends(get_indexing_service)]
SearchServiceDep = Annotated[SemanticSearchService, Depends(get_search_service)]


def get_ask_service(
    search: SearchServiceDep, llm: LLMProviderDep, settings: Annotated[Settings, Depends(get_settings)]
) -> AskVantageService:
    return AskVantageService(search, llm, provider_name=settings.llm_provider)


AskServiceDep = Annotated[AskVantageService, Depends(get_ask_service)]


WatchlistServiceDep = Annotated[WatchlistService, Depends(get_watchlist_service)]
CompanyServiceDep = Annotated[CompanyService, Depends(get_company_service)]
TopicServiceDep = Annotated[TopicService, Depends(get_topic_service)]
SourceServiceDep = Annotated[SourceService, Depends(get_source_service)]
IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]
IntelligenceAnalysisServiceDep = Annotated[IntelligenceAnalysisService, Depends(get_intelligence_service)]
