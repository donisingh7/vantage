import asyncio
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.core.exceptions import ConflictError, ProviderError
from app.models import Document, IntelligenceSignal, Source, SourceType
from app.providers.embeddings import AzureOpenAIEmbeddingProvider, MockEmbeddingProvider
from app.providers.llm import AzureOpenAILLMProvider, MockLLMProvider
from app.services.analysis_schema import DocumentAnalysisResult
from app.services.indexing import DocumentIndexingService
from app.services.intelligence_analysis import IntelligenceAnalysisService
from app.services.scheduler import should_enable_scheduler

API = "/api/v1"


def _chat_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _embedding_response(vectors: list[list[float]]) -> SimpleNamespace:
    return SimpleNamespace(data=[SimpleNamespace(embedding=vector) for vector in vectors])


class _FakeChatCompletions:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    async def create(self, **kwargs):
        if self._error:
            raise self._error
        return self._response


class _FakeAsyncAzureOpenAI:
    def __init__(self, response=None, error=None):
        self._response, self._error = response, error

    def __call__(self, **kwargs):
        client = SimpleNamespace()
        client.chat = SimpleNamespace(completions=_FakeChatCompletions(self._response, self._error))
        return client


class _FakeEmbeddings:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    def create(self, **kwargs):
        if self._error:
            raise self._error
        return self._response


class _FakeAzureOpenAI:
    def __init__(self, response=None, error=None):
        self._response, self._error = response, error

    def __call__(self, **kwargs):
        client = SimpleNamespace()
        client.embeddings = _FakeEmbeddings(self._response, self._error)
        return client


async def insert_document(sessions, *, workspace_id, source_id, title="Doc", content="x" * 100, url=None):
    async with sessions() as session:
        document = Document(
            workspace_id=workspace_id, source_id=source_id,
            canonical_url=url or f"https://example.com/{uuid4()}", title=title, content=content,
            excerpt=content[:200] if content else None, author=None, published_at=None,
            content_hash=hashlib.sha256((content or title).encode()).hexdigest(), fetched_at=datetime.now(UTC),
        )
        session.add(document)
        await session.commit()
        return document.id


# -- Azure OpenAI LLM adapter (mocked SDK, no network) ------------------------


async def test_azure_llm_generate_returns_text_from_mocked_client():
    with patch("openai.AsyncAzureOpenAI", _FakeAsyncAzureOpenAI(response=_chat_response("Hello from Azure OpenAI"))):
        provider = AzureOpenAILLMProvider(
            endpoint="https://example.openai.azure.com", api_key="key",
            api_version="2024-08-01-preview", chat_deployment="gpt-4o",
        )
        result = await provider.generate("hello", system="be nice")
    assert result == "Hello from Azure OpenAI"


async def test_azure_llm_structured_generate_parses_json_into_schema():
    class Simple(BaseModel):
        answer: str
        score: float

    payload = json.dumps({"answer": "42", "score": 0.9})
    with patch("openai.AsyncAzureOpenAI", _FakeAsyncAzureOpenAI(response=_chat_response(payload))):
        provider = AzureOpenAILLMProvider(
            endpoint="https://example.openai.azure.com", api_key="key", api_version="v", chat_deployment="gpt-4o"
        )
        result = await provider.structured_generate("prompt", Simple)
    assert result.answer == "42"
    assert result.score == 0.9


async def test_azure_llm_structured_generate_matches_document_analysis_schema():
    payload = json.dumps(
        {
            "relevant": True, "relevance_score": 0.8, "signal_type": "funding", "title": "T",
            "executive_summary": "S", "importance_score": 0.7, "sentiment": "positive",
            "key_entities": ["Acme"], "key_points": ["point"], "business_impact": "B",
            "confidence_score": 0.9, "evidence_excerpt": "E",
        }
    )
    with patch("openai.AsyncAzureOpenAI", _FakeAsyncAzureOpenAI(response=_chat_response(payload))):
        provider = AzureOpenAILLMProvider(
            endpoint="https://example.openai.azure.com", api_key="key", api_version="v", chat_deployment="gpt-4o"
        )
        result = await provider.structured_generate("prompt", DocumentAnalysisResult, system="analyze")
    assert isinstance(result, DocumentAnalysisResult)
    assert result.signal_type.value == "funding"


async def test_azure_llm_wraps_sdk_error_without_leaking_api_key():
    from openai import OpenAIError

    class _FakeSDKError(OpenAIError):
        pass

    with patch("openai.AsyncAzureOpenAI", _FakeAsyncAzureOpenAI(error=_FakeSDKError("connection reset"))):
        provider = AzureOpenAILLMProvider(
            endpoint="https://example.openai.azure.com", api_key="super-secret-key",
            api_version="v", chat_deployment="gpt-4o",
        )
        with pytest.raises(ProviderError) as exc_info:
            await provider.generate("hello")
    assert "super-secret-key" not in str(exc_info.value)


# -- Azure OpenAI embedding adapter (mocked SDK, no network) ------------------


def test_azure_embedding_provider_returns_vectors_from_mocked_client():
    with patch("openai.AzureOpenAI", _FakeAzureOpenAI(response=_embedding_response([[0.1, 0.2], [0.3, 0.4]]))):
        provider = AzureOpenAIEmbeddingProvider(
            endpoint="https://example.openai.azure.com", api_key="key",
            api_version="v", embedding_deployment="text-embedding-3-small",
        )
        vectors = provider.embed_documents(["a", "b"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_azure_embedding_provider_embed_text_uses_first_vector():
    with patch("openai.AzureOpenAI", _FakeAzureOpenAI(response=_embedding_response([[0.5, 0.6]]))):
        provider = AzureOpenAIEmbeddingProvider(
            endpoint="https://example.openai.azure.com", api_key="key",
            api_version="v", embedding_deployment="text-embedding-3-small",
        )
        vector = provider.embed_text("hello")
    assert vector == [0.5, 0.6]


def test_azure_embedding_provider_wraps_sdk_error_without_leaking_api_key():
    from openai import OpenAIError

    class _FakeSDKError(OpenAIError):
        pass

    with patch("openai.AzureOpenAI", _FakeAzureOpenAI(error=_FakeSDKError("boom"))):
        provider = AzureOpenAIEmbeddingProvider(
            endpoint="https://example.openai.azure.com", api_key="super-secret",
            api_version="v", embedding_deployment="text-embedding-3-small",
        )
        with pytest.raises(ProviderError) as exc_info:
            provider.embed_documents(["a"])
    assert "super-secret" not in str(exc_info.value)


def test_azure_embedding_provider_returns_empty_list_for_no_documents():
    provider = AzureOpenAIEmbeddingProvider(
        endpoint="https://example.openai.azure.com", api_key="key", api_version="v", embedding_deployment="d"
    )
    assert provider.embed_documents([]) == []


# -- Provider dependency wiring -------------------------------------------------


def test_get_llm_provider_selects_mock_by_default():
    from app.api.deps import get_llm_provider
    from app.core.config import Settings

    provider = get_llm_provider(Settings(_env_file=None))
    assert isinstance(provider, MockLLMProvider)


def test_get_llm_provider_builds_azure_adapter_when_selected_and_configured():
    from app.api.deps import get_llm_provider
    from app.core.config import Settings

    settings = Settings(
        _env_file=None, llm_provider="azure_openai",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_api_key="key", azure_openai_chat_deployment="gpt-4o",
    )
    with patch("openai.AsyncAzureOpenAI", _FakeAsyncAzureOpenAI()):
        provider = get_llm_provider(settings)
    assert isinstance(provider, AzureOpenAILLMProvider)


def test_get_embedding_provider_builds_azure_adapter_when_selected_and_configured():
    from app.api.deps import get_embedding_provider
    from app.core.config import Settings

    settings = Settings(
        _env_file=None, embedding_provider="azure_openai",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_api_key="key", azure_openai_embedding_deployment="text-embedding-3-small",
    )
    with patch("openai.AzureOpenAI", _FakeAzureOpenAI()):
        provider = get_embedding_provider(settings)
    assert isinstance(provider, AzureOpenAIEmbeddingProvider)


# -- Scheduler explicitly disabled in test mode --------------------------------


def test_scheduler_disabled_in_test_mode_even_if_flag_true():
    assert should_enable_scheduler(enable_scheduler=True, app_env="test") is False


def test_scheduler_respects_flag_outside_test_mode():
    assert should_enable_scheduler(enable_scheduler=True, app_env="development") is True
    assert should_enable_scheduler(enable_scheduler=False, app_env="development") is False


# -- Source-creation SSRF hardening -------------------------------------------


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1/feed", "http://169.254.169.254/latest/meta-data", "http://localhost/feed", "http://10.0.0.5/feed"]
)
async def test_source_creation_rejects_private_and_local_urls(client, url):
    response = await client.post(f"{API}/sources", json={"name": "Bad", "url": url, "source_type": "website"})
    assert response.status_code == 422, response.text


async def test_source_creation_accepts_public_url(client):
    response = await client.post(
        f"{API}/sources", json={"name": "Good", "url": "https://example.com/feed", "source_type": "website"}
    )
    assert response.status_code == 201, response.text


# -- Concurrent analyze/index duplicate-run protection ------------------------


async def _dev_workspace(session):
    from app.auth.dependencies import DevelopmentCurrentUserProvider
    from app.core.config import get_settings
    from app.services.workspace import resolve_workspace_context

    settings = get_settings()
    current_user = DevelopmentCurrentUserProvider(settings).get_user()
    return await resolve_workspace_context(session, current_user, settings)


async def test_analyze_document_blocks_concurrent_runs_for_same_document(sessions):
    async with sessions() as session:
        context = await _dev_workspace(session)
        source = Source(workspace_id=context.workspace.id, name="Feed", url="https://example.com/feed", source_type=SourceType.WEBSITE)
        session.add(source)
        await session.commit()

        document_id = await insert_document(sessions, workspace_id=context.workspace.id, source_id=source.id)
        service = IntelligenceAnalysisService(session, context.workspace.id, MockLLMProvider())

        results = await asyncio.gather(
            service.analyze_document(document_id), service.analyze_document(document_id), return_exceptions=True
        )

    successes = [r for r in results if isinstance(r, IntelligenceSignal)]
    conflicts = [r for r in results if isinstance(r, ConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1


async def test_index_document_blocks_concurrent_runs_for_same_document(sessions):
    async with sessions() as session:
        context = await _dev_workspace(session)
        source = Source(workspace_id=context.workspace.id, name="Feed", url="https://example.com/feed", source_type=SourceType.WEBSITE)
        session.add(source)
        await session.commit()

        document_id = await insert_document(sessions, workspace_id=context.workspace.id, source_id=source.id)
        service = DocumentIndexingService(session, context.workspace.id, MockEmbeddingProvider(dimensions=8))

        results = await asyncio.gather(
            service.index_document(document_id), service.index_document(document_id), return_exceptions=True
        )

    successes = [r for r in results if not isinstance(r, Exception)]
    conflicts = [r for r in results if isinstance(r, ConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1
