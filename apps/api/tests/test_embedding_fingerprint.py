"""A document's index must be invalidated by an embedding provider/config switch,
not just by a content change -- otherwise stale, dimension-mismatched vectors from a
previous provider silently remain in DocumentChunk. See DocumentIndexingService.is_current.
"""
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from app.models import Document, Source, SourceType
from app.providers.embeddings import MockEmbeddingProvider
from app.services.indexing import DocumentIndexingService

CONTENT = "x" * 100


class FakeAzureEmbeddingProvider:
    """Mimics a real, differently-fingerprinted provider without any SDK/network dependency."""

    def __init__(self, dimensions: int = 8) -> None:
        self._dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return [[0.1] * self._dimensions for _ in documents]

    def fingerprint(self) -> str:
        return f"azure_openai:fake-deployment:dims={self._dimensions}"


class FailingEmbeddingProvider:
    def fingerprint(self) -> str:
        return "mock:dims=16"

    def embed_text(self, text: str) -> list[float]:
        raise RuntimeError("embedding backend unavailable")

    def embed_documents(self, documents: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding backend unavailable")


async def _dev_workspace(session):
    from app.auth.dependencies import DevelopmentCurrentUserProvider
    from app.core.config import get_settings
    from app.services.workspace import resolve_workspace_context

    settings = get_settings()
    current_user = DevelopmentCurrentUserProvider(settings).get_user()
    return await resolve_workspace_context(session, current_user, settings)


async def _insert_document(session, *, workspace_id, source_id, content=CONTENT):
    document = Document(
        workspace_id=workspace_id, source_id=source_id,
        canonical_url=f"https://example.com/{uuid4()}", title="Doc", content=content,
        excerpt=content[:200], author=None, published_at=None,
        content_hash=hashlib.sha256(content.encode()).hexdigest(), fetched_at=datetime.now(UTC),
    )
    session.add(document)
    await session.commit()
    return document.id


async def test_same_content_and_fingerprint_is_skipped(sessions):
    async with sessions() as session:
        context = await _dev_workspace(session)
        source = Source(workspace_id=context.workspace.id, name="Feed", url="https://example.com/feed", source_type=SourceType.WEBSITE)
        session.add(source)
        await session.commit()
        document_id = await _insert_document(session, workspace_id=context.workspace.id, source_id=source.id)

        service = DocumentIndexingService(session, context.workspace.id, MockEmbeddingProvider(dimensions=16))
        first = await service.index_document(document_id)
        assert first.skipped is False

        second = await service.index_document(document_id)
        assert second.skipped is True
        assert second.chunks_created == 0


async def test_same_content_but_changed_embedding_dimensions_forces_reindex(sessions):
    async with sessions() as session:
        context = await _dev_workspace(session)
        source = Source(workspace_id=context.workspace.id, name="Feed", url="https://example.com/feed", source_type=SourceType.WEBSITE)
        session.add(source)
        await session.commit()
        document_id = await _insert_document(session, workspace_id=context.workspace.id, source_id=source.id)

        first_service = DocumentIndexingService(session, context.workspace.id, MockEmbeddingProvider(dimensions=16))
        first = await first_service.index_document(document_id)
        assert first.skipped is False

        second_service = DocumentIndexingService(session, context.workspace.id, MockEmbeddingProvider(dimensions=32))
        second = await second_service.index_document(document_id)
        assert second.skipped is False
        assert second.chunks_created > 0


async def test_switching_from_mock_to_a_different_provider_invalidates_previous_index(sessions):
    async with sessions() as session:
        context = await _dev_workspace(session)
        source = Source(workspace_id=context.workspace.id, name="Feed", url="https://example.com/feed", source_type=SourceType.WEBSITE)
        session.add(source)
        await session.commit()
        document_id = await _insert_document(session, workspace_id=context.workspace.id, source_id=source.id)

        mock_service = DocumentIndexingService(session, context.workspace.id, MockEmbeddingProvider(dimensions=16))
        mock_result = await mock_service.index_document(document_id)
        assert mock_result.skipped is False

        azure_service = DocumentIndexingService(session, context.workspace.id, FakeAzureEmbeddingProvider(dimensions=8))
        azure_result = await azure_service.index_document(document_id)
        assert azure_result.skipped is False

        document = await session.get(Document, document_id)
        assert document.indexed_embedding_fingerprint == "azure_openai:fake-deployment:dims=8"

        # Chunks now only hold 8-dimension Azure-shaped vectors, not the earlier 16-dim mock ones.
        from sqlalchemy import select

        from app.models import DocumentChunk

        chunks = (await session.execute(select(DocumentChunk).where(DocumentChunk.document_id == document_id))).scalars().all()
        assert all(len(chunk.embedding) == 8 for chunk in chunks)


async def test_fingerprint_is_not_persisted_when_indexing_fails(sessions):
    async with sessions() as session:
        context = await _dev_workspace(session)
        source = Source(workspace_id=context.workspace.id, name="Feed", url="https://example.com/feed", source_type=SourceType.WEBSITE)
        session.add(source)
        await session.commit()
        document_id = await _insert_document(session, workspace_id=context.workspace.id, source_id=source.id)

        service = DocumentIndexingService(session, context.workspace.id, FailingEmbeddingProvider())
        try:
            await service.index_document(document_id)
            raised = False
        except RuntimeError:
            raised = True
        assert raised

        document = await session.get(Document, document_id)
        assert document.indexed_content_hash is None
        assert document.indexed_embedding_fingerprint is None
