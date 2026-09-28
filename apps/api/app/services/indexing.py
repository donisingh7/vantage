"""Document -> deterministic chunks -> embeddings -> persisted DocumentChunk rows."""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Document, DocumentChunk
from app.providers.embeddings import EmbeddingProvider
from app.services.chunking import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, chunk_text
from app.services.concurrency import InProcessKeyGuard

MAX_INDEX_PENDING_LIMIT = 25

_indexing_guard = InProcessKeyGuard(conflict_message="Indexing is already running for this document")


@dataclass
class IndexResult:
    document_id: UUID
    chunks_created: int
    total_chunks: int
    skipped: bool


class DocumentIndexingService:
    def __init__(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        embeddings: EmbeddingProvider,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.embeddings = embeddings
        self.chunk_size = chunk_size
        self.overlap = overlap

    async def _get_document(self, document_id: UUID) -> Document:
        document = await self.session.get(Document, document_id)
        if document is None or document.workspace_id != self.workspace_id:
            raise NotFoundError("Document was not found in this workspace")
        return document

    async def _chunk_count(self, document_id: UUID) -> int:
        statement = select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.workspace_id == self.workspace_id, DocumentChunk.document_id == document_id
        )
        return int((await self.session.execute(statement)).scalar_one())

    def is_current(self, document: Document) -> bool:
        """True iff `document`'s persisted chunks match both its current content AND the
        embedding provider/config configured on this service instance. The single
        definition of "currently indexed", shared by the skip check, the pending query,
        and read-only callers (e.g. the documents list endpoint) so they can't drift apart.
        """
        return (
            document.content_hash is not None
            and document.indexed_content_hash == document.content_hash
            and document.indexed_embedding_fingerprint == self.embeddings.fingerprint()
        )

    async def index_document(self, document_id: UUID, *, force: bool = False) -> IndexResult:
        async with _indexing_guard.acquire(document_id):
            return await self._index_document(document_id, force=force)

    async def _index_document(self, document_id: UUID, *, force: bool) -> IndexResult:
        document = await self._get_document(document_id)
        fingerprint = self.embeddings.fingerprint()

        if self.is_current(document) and not force:
            return IndexResult(
                document_id=document.id,
                chunks_created=0,
                total_chunks=await self._chunk_count(document.id),
                skipped=True,
            )

        await self.session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.workspace_id == self.workspace_id, DocumentChunk.document_id == document.id
            )
        )

        text = document.content or document.excerpt or document.title or ""
        pieces = chunk_text(text, chunk_size=self.chunk_size, overlap=self.overlap)
        vectors = self.embeddings.embed_documents(pieces) if pieces else []
        for index, (piece, vector) in enumerate(zip(pieces, vectors, strict=True)):
            self.session.add(
                DocumentChunk(
                    workspace_id=self.workspace_id,
                    document_id=document.id,
                    chunk_index=index,
                    content=piece,
                    embedding=vector,
                )
            )

        document.indexed_content_hash = document.content_hash
        document.indexed_embedding_fingerprint = fingerprint
        await self.session.commit()
        return IndexResult(document_id=document.id, chunks_created=len(pieces), total_chunks=len(pieces), skipped=False)

    async def index_pending(self, *, limit: int = 5) -> list[IndexResult]:
        """Indexes up to `limit` documents that are new or changed since their last index."""
        limit = max(1, min(limit, MAX_INDEX_PENDING_LIMIT))
        pending_ids = await self._pending_document_ids(limit)
        return [await self.index_document(document_id) for document_id in pending_ids]

    async def _pending_document_ids(self, limit: int) -> list[UUID]:
        fingerprint = self.embeddings.fingerprint()
        statement = (
            select(Document.id)
            .where(
                Document.workspace_id == self.workspace_id,
                (Document.indexed_content_hash.is_(None))
                | (Document.indexed_content_hash != Document.content_hash)
                | (Document.indexed_embedding_fingerprint.is_(None))
                | (Document.indexed_embedding_fingerprint != fingerprint),
            )
            .order_by(Document.fetched_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())
