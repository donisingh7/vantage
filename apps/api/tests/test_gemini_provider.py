import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.core.exceptions import ProviderError
from app.models import Document, Source, SourceType
from app.providers.embeddings import GeminiEmbeddingProvider, MockEmbeddingProvider
from app.providers.llm import GeminiLLMProvider
from app.services.indexing import DocumentIndexingService

API = "/api/v1"


class _FakeGenAIClient:
    """Configurable fake for google.genai.Client. Only wires what a given test needs."""

    def __init__(self, *, chat_response=None, chat_error=None, embed_response=None, embed_error=None):
        self.embed_calls: list[dict] = []
        self.generate_calls: list[dict] = []

        async def generate_content(**kwargs):
            self.generate_calls.append(kwargs)
            if chat_error:
                raise chat_error
            return chat_response

        def embed_content(**kwargs):
            self.embed_calls.append(kwargs)
            if embed_error:
                raise embed_error
            return embed_response

        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        self.models = SimpleNamespace(embed_content=embed_content)


class _FakeGenAIClientFactory:
    """Patches google.genai.Client: calling it (as the SDK constructor does) returns a fake."""

    def __init__(self, **client_kwargs):
        self._client_kwargs = client_kwargs
        self.instances: list[_FakeGenAIClient] = []

    def __call__(self, **kwargs):
        instance = _FakeGenAIClient(**self._client_kwargs)
        self.instances.append(instance)
        return instance


def _chat_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def _embed_response(vectors: list[list[float]]) -> SimpleNamespace:
    return SimpleNamespace(embeddings=[SimpleNamespace(values=vector) for vector in vectors])


async def _dev_workspace(session):
    from app.auth.dependencies import DevelopmentCurrentUserProvider
    from app.core.config import get_settings
    from app.services.workspace import resolve_workspace_context

    settings = get_settings()
    current_user = DevelopmentCurrentUserProvider(settings).get_user()
    return await resolve_workspace_context(session, current_user, settings)


async def _insert_document(session, *, workspace_id, source_id, content="x" * 100):
    document = Document(
        workspace_id=workspace_id, source_id=source_id,
        canonical_url=f"https://example.com/{uuid4()}", title="Doc", content=content,
        excerpt=content[:200], author=None, published_at=None,
        content_hash=hashlib.sha256(content.encode()).hexdigest(), fetched_at=datetime.now(UTC),
    )
    session.add(document)
    await session.commit()
    return document.id


# -- Configuration --------------------------------------------------------------


def test_gemini_selected_without_api_key_fails_configuration():
    from app.core.config import Settings

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        Settings(_env_file=None, llm_provider="gemini")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        Settings(_env_file=None, embedding_provider="gemini")


def test_gemini_configuration_succeeds_with_api_key_set():
    from app.core.config import Settings

    settings = Settings(_env_file=None, llm_provider="gemini", embedding_provider="gemini", gemini_api_key="k")
    assert settings.llm_provider == "gemini"
    assert settings.embedding_provider == "gemini"


# -- Dependency wiring ------------------------------------------------------------


def test_get_llm_provider_builds_gemini_adapter_when_selected_and_configured():
    from app.api.deps import get_llm_provider
    from app.core.config import Settings

    settings = Settings(_env_file=None, llm_provider="gemini", gemini_api_key="fake-key")
    with patch("google.genai.Client", _FakeGenAIClientFactory()):
        provider = get_llm_provider(settings)
    assert isinstance(provider, GeminiLLMProvider)


def test_get_embedding_provider_builds_gemini_adapter_when_selected_and_configured():
    from app.api.deps import get_embedding_provider
    from app.core.config import Settings

    settings = Settings(_env_file=None, embedding_provider="gemini", gemini_api_key="fake-key")
    with patch("google.genai.Client", _FakeGenAIClientFactory()):
        provider = get_embedding_provider(settings)
    assert isinstance(provider, GeminiEmbeddingProvider)


# -- Gemini LLM (mocked SDK, no network) ---------------------------------------


async def test_gemini_generate_returns_text_from_mocked_client():
    with patch("google.genai.Client", _FakeGenAIClientFactory(chat_response=_chat_response("Hello from Gemini"))):
        provider = GeminiLLMProvider(api_key="fake-key", model="gemini-2.5-flash")
        result = await provider.generate("hello", system="be nice")
    assert result == "Hello from Gemini"


async def test_gemini_structured_generate_validates_through_pydantic_schema():
    class Simple(BaseModel):
        answer: str
        score: float

    payload = json.dumps({"answer": "42", "score": 0.9})
    with patch("google.genai.Client", _FakeGenAIClientFactory(chat_response=_chat_response(payload))):
        provider = GeminiLLMProvider(api_key="fake-key", model="gemini-2.5-flash")
        result = await provider.structured_generate("prompt", Simple)
    assert result.answer == "42"
    assert result.score == 0.9


async def test_gemini_wraps_sdk_error_without_leaking_api_key():
    from google.genai import errors as genai_errors

    class _FakeAPIError(genai_errors.APIError):
        def __init__(self, message):
            self.message = message

        def __str__(self):
            return self.message

    with patch("google.genai.Client", _FakeGenAIClientFactory(chat_error=_FakeAPIError("connection reset"))):
        provider = GeminiLLMProvider(api_key="super-secret-gemini-key", model="gemini-2.5-flash")
        with pytest.raises(ProviderError) as exc_info:
            await provider.generate("hello")
    assert "super-secret-gemini-key" not in str(exc_info.value)


# -- Gemini embeddings (mocked SDK, no network) --------------------------------


def test_gemini_embed_text_uses_query_retrieval_formatting():
    factory = _FakeGenAIClientFactory(embed_response=_embed_response([[0.1, 0.2]]))
    with patch("google.genai.Client", factory):
        provider = GeminiEmbeddingProvider(api_key="fake-key", model="gemini-embedding-2", dimensions=8)
        vector = provider.embed_text("market conditions")
    assert vector == [0.1, 0.2]
    sent_contents = factory.instances[0].embed_calls[0]["contents"]
    assert sent_contents == "task: search result | query: market conditions"


def test_gemini_embed_documents_uses_document_formatting_and_preserves_order():
    calls: list[dict] = []
    responses = iter([_embed_response([[0.1]]), _embed_response([[0.2]])])

    class _SequencedFakeClient:
        def __init__(self, **kwargs):
            self.models = SimpleNamespace(embed_content=self._embed_content)

        @staticmethod
        def _embed_content(**kwargs):
            calls.append(kwargs)
            return next(responses)

    with patch("google.genai.Client", _SequencedFakeClient):
        provider = GeminiEmbeddingProvider(api_key="fake-key", model="gemini-embedding-2", dimensions=8)
        vectors = provider.embed_documents(["alpha", "beta"])

    assert vectors == [[0.1], [0.2]]
    assert calls[0]["contents"] == "title: none | text: alpha"
    assert calls[1]["contents"] == "title: none | text: beta"


def test_gemini_embed_documents_empty_list_returns_empty_list():
    with patch("google.genai.Client", _FakeGenAIClientFactory()):
        provider = GeminiEmbeddingProvider(api_key="fake-key", model="gemini-embedding-2", dimensions=8)
        assert provider.embed_documents([]) == []


def test_gemini_embedding_fingerprint_includes_model_dimensions_and_retrieval_version():
    with patch("google.genai.Client", _FakeGenAIClientFactory()):
        provider = GeminiEmbeddingProvider(api_key="fake-key", model="gemini-embedding-2", dimensions=768)
    assert provider.fingerprint() == "gemini:gemini-embedding-2:dims=768:retrieval-v1"


def test_gemini_embedding_provider_wraps_sdk_error_without_leaking_api_key():
    from google.genai import errors as genai_errors

    class _FakeAPIError(genai_errors.APIError):
        def __init__(self, message):
            self.message = message

        def __str__(self):
            return self.message

    with patch("google.genai.Client", _FakeGenAIClientFactory(embed_error=_FakeAPIError("boom"))):
        provider = GeminiEmbeddingProvider(api_key="super-secret-gemini-key", model="gemini-embedding-2")
        with pytest.raises(ProviderError) as exc_info:
            provider.embed_documents(["a"])
    assert "super-secret-gemini-key" not in str(exc_info.value)


# -- Fingerprint change invalidates a previously mock-indexed document --------


async def test_switching_from_mock_to_gemini_invalidates_previous_index(sessions):
    async with sessions() as session:
        context = await _dev_workspace(session)
        source = Source(workspace_id=context.workspace.id, name="Feed", url="https://example.com/feed", source_type=SourceType.WEBSITE)
        session.add(source)
        await session.commit()
        document_id = await _insert_document(session, workspace_id=context.workspace.id, source_id=source.id)

        mock_service = DocumentIndexingService(session, context.workspace.id, MockEmbeddingProvider(dimensions=16))
        mock_result = await mock_service.index_document(document_id)
        assert mock_result.skipped is False

        with patch("google.genai.Client", _FakeGenAIClientFactory(embed_response=_embed_response([[0.1] * 768]))):
            gemini_provider = GeminiEmbeddingProvider(api_key="fake-key", model="gemini-embedding-2", dimensions=768)
            gemini_service = DocumentIndexingService(session, context.workspace.id, gemini_provider)
            gemini_result = await gemini_service.index_document(document_id)

        assert gemini_result.skipped is False

        document = await session.get(Document, document_id)
        assert document.indexed_embedding_fingerprint == "gemini:gemini-embedding-2:dims=768:retrieval-v1"


# -- Lambda handler -------------------------------------------------------------


def test_lambda_handler_imports_and_is_callable():
    from app.lambda_handler import handler

    assert callable(handler)


# -- Serverless PostgreSQL connection handling --------------------------------


def test_serverless_postgres_uses_nullpool(monkeypatch):
    from sqlalchemy.pool import NullPool

    captured: dict = {}

    def fake_create_async_engine(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return SimpleNamespace(pool=kwargs.get("poolclass"))

    monkeypatch.setattr("app.db.session.create_async_engine", fake_create_async_engine)
    from app.db.session import create_engine

    create_engine("postgresql+asyncpg://user:pass@host/db", serverless=True)
    assert captured["poolclass"] is NullPool


def test_serverless_postgres_requires_ssl(monkeypatch):
    captured: dict = {}

    def fake_create_async_engine(url, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(pool=kwargs.get("poolclass"))

    monkeypatch.setattr("app.db.session.create_async_engine", fake_create_async_engine)
    from app.db.session import create_engine

    create_engine("postgresql+asyncpg://user:pass@host/db", serverless=True)
    assert captured["connect_args"]["ssl"] is True


def test_serverless_postgres_does_not_disable_prepared_statement_cache(monkeypatch):
    """SQLAlchemy's asyncpg dialect relies on server-side prepared statements, which a
    transaction-mode pooler doesn't support -- this repo does not claim transaction-pooler
    compatibility, and does not attempt to fake it by disabling asyncpg's statement cache.
    The supported production path is a session-mode pooler or a direct connection.
    """
    captured: dict = {}

    def fake_create_async_engine(url, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(pool=kwargs.get("poolclass"))

    monkeypatch.setattr("app.db.session.create_async_engine", fake_create_async_engine)
    from app.db.session import create_engine

    create_engine("postgresql+asyncpg://user:pass@host/db", serverless=True)
    assert "statement_cache_size" not in captured["connect_args"]
    assert captured["connect_args"] == {"ssl": True}


def test_non_serverless_postgres_uses_default_pooling(monkeypatch):
    captured: dict = {}

    def fake_create_async_engine(url, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("app.db.session.create_async_engine", fake_create_async_engine)
    from app.db.session import create_engine

    create_engine("postgresql+asyncpg://user:pass@host/db", serverless=False)
    assert captured.get("pool_pre_ping") is True
    assert "poolclass" not in captured
    assert "connect_args" not in captured


def test_sqlite_ignores_serverless_flag(tmp_path):
    from app.db.session import create_engine

    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'x.db'}", serverless=True)
    assert engine is not None
    assert "sqlite" in str(engine.url)
