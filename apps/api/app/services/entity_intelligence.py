"""One-request read for the company/topic Entity Intelligence dialog: the entity's signals,
the watchlists containing it, and only the documents/sources those signals actually
reference -- replacing four requests (filtered signals, watchlists-containing, all sources,
all documents), the last two of which pulled the entire workspace's sources and documents
just to resolve a handful of names/URLs.

No LLM/embedding provider construction: signal listing reuses IntelligenceReadService, and
company/topic existence checks reuse the plain CRUD services (session + workspace_id only).
"""
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, IntelligenceSignal, Source, Watchlist
from app.schemas.common import CatalogEntryRead
from app.schemas.entity_intelligence import EntityDocumentRef
from app.services.companies import CompanyService
from app.services.intelligence_read import IntelligenceReadService
from app.services.topics import TopicService
from app.services.watchlists import WatchlistService

EntityKind = Literal["company", "topic"]


class EntityIntelligenceData:
    def __init__(
        self,
        signals: list[IntelligenceSignal],
        watchlists: list[Watchlist],
        documents: list[EntityDocumentRef],
        sources: list[CatalogEntryRead],
    ) -> None:
        self.signals = signals
        self.watchlists = watchlists
        self.documents = documents
        self.sources = sources


class EntityIntelligenceService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.reads = IntelligenceReadService(session, workspace_id)
        self.watchlists = WatchlistService(session, workspace_id)

    async def for_entity(self, kind: EntityKind, entity_id: UUID) -> EntityIntelligenceData:
        # Raises NotFoundError (-> 404) if the entity doesn't exist in this workspace.
        if kind == "company":
            await CompanyService(self.session, self.workspace_id).get(entity_id)
            signals = await self.reads.list_signals(company_id=entity_id)
            watchlists = await self.watchlists.list_containing(company_id=entity_id)
        else:
            await TopicService(self.session, self.workspace_id).get(entity_id)
            signals = await self.reads.list_signals(topic_id=entity_id)
            watchlists = await self.watchlists.list_containing(topic_id=entity_id)

        document_ids = {signal.document_id for signal in signals}
        documents = await self._document_refs(document_ids)
        source_ids = {document.source_id for document in documents}
        sources = await self._source_catalog(source_ids)

        return EntityIntelligenceData(signals=signals, watchlists=watchlists, documents=documents, sources=sources)

    async def _document_refs(self, document_ids: set[UUID]) -> list[EntityDocumentRef]:
        if not document_ids:
            return []
        statement = select(Document.id, Document.source_id, Document.canonical_url).where(
            Document.workspace_id == self.workspace_id, Document.id.in_(document_ids)
        )
        rows = (await self.session.execute(statement)).all()
        return [EntityDocumentRef(id=row.id, source_id=row.source_id, canonical_url=row.canonical_url) for row in rows]

    async def _source_catalog(self, source_ids: set[UUID]) -> list[CatalogEntryRead]:
        if not source_ids:
            return []
        statement = select(Source.id, Source.name).where(
            Source.workspace_id == self.workspace_id, Source.id.in_(source_ids)
        )
        rows = (await self.session.execute(statement)).all()
        return [CatalogEntryRead(id=row.id, name=row.name) for row in rows]
