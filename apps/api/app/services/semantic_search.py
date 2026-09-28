"""Workspace-scoped semantic retrieval over indexed DocumentChunks.

The brute-force cosine scan here is a placeholder for a future PostgreSQL/pgvector
`ORDER BY embedding <=> query LIMIT k` query; callers only see `search()`, so that
swap would not change this service's interface.
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, Source
from app.providers.embeddings import EmbeddingProvider
from app.services.vector_math import cosine_similarity

MAX_TOP_K = 20
DEFAULT_TOP_K = 5
EXCERPT_LENGTH = 320


@dataclass
class SearchResult:
    document_id: UUID
    title: str | None
    source_name: str
    source_url: str
    canonical_url: str
    excerpt: str
    chunk_content: str
    similarity: float


class SemanticSearchService:
    def __init__(self, session: AsyncSession, workspace_id: UUID, embeddings: EmbeddingProvider) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.embeddings = embeddings

    async def search(self, query: str, *, top_k: int = DEFAULT_TOP_K) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        top_k = max(1, min(top_k, MAX_TOP_K))

        query_vector = self.embeddings.embed_text(query)
        statement = select(DocumentChunk).where(DocumentChunk.workspace_id == self.workspace_id)
        chunks = (await self.session.execute(statement)).scalars().all()
        if not chunks:
            return []

        scored = sorted(
            ((cosine_similarity(query_vector, chunk.embedding), chunk) for chunk in chunks),
            key=lambda pair: pair[0],
            reverse=True,
        )[:top_k]

        document_ids = {chunk.document_id for _, chunk in scored}
        documents = {
            document.id: document
            for document in (
                await self.session.execute(select(Document).where(Document.id.in_(document_ids)))
            ).scalars().all()
        }
        source_ids = {document.source_id for document in documents.values()}
        sources = {
            source.id: source
            for source in (
                await self.session.execute(select(Source).where(Source.id.in_(source_ids)))
            ).scalars().all()
        }

        results: list[SearchResult] = []
        for score, chunk in scored:
            document = documents.get(chunk.document_id)
            if document is None:
                continue
            source = sources.get(document.source_id)
            results.append(
                SearchResult(
                    document_id=document.id,
                    title=document.title,
                    source_name=source.name if source else "Unknown source",
                    source_url=source.url if source else document.canonical_url,
                    canonical_url=document.canonical_url,
                    excerpt=chunk.content[:EXCERPT_LENGTH],
                    chunk_content=chunk.content,
                    similarity=round(score, 4),
                )
            )
        return results
