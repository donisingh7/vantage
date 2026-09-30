"""One-request read for the Intelligence page's first render: documents, initial unfiltered
signals, and the narrow lookup catalogs (sources/companies/topics) and provider metadata the
page needs -- replacing the previous six-request refresh() (documents, signals, sources,
companies, topics, system/info).

Builds everything directly from AsyncSession/Settings. Deliberately constructs no LLM or
embedding provider -- documents come from DocumentReadService (shared with GET /documents),
signals from IntelligenceReadService.
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Company, Source, Topic
from app.schemas.common import CatalogEntryRead, ProviderInfo
from app.schemas.ingestion import DocumentRead
from app.schemas.intelligence import IntelligenceSignalRead
from app.services.document_read import DocumentReadService
from app.services.intelligence_read import IntelligenceReadService


class IntelligenceBootstrapData:
    def __init__(
        self,
        providers: ProviderInfo,
        documents: list[DocumentRead],
        signals: list[IntelligenceSignalRead],
        sources: list[CatalogEntryRead],
        companies: list[CatalogEntryRead],
        topics: list[CatalogEntryRead],
    ) -> None:
        self.providers = providers
        self.documents = documents
        self.signals = signals
        self.sources = sources
        self.companies = companies
        self.topics = topics


class IntelligenceBootstrapService:
    def __init__(self, session: AsyncSession, workspace_id: UUID, settings: Settings) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.settings = settings
        self.reads = IntelligenceReadService(session, workspace_id)
        self.documents = DocumentReadService(session, workspace_id, settings)

    async def bootstrap(self) -> IntelligenceBootstrapData:
        document_reads = await self.documents.list()
        signals = await self.reads.list_signals()

        return IntelligenceBootstrapData(
            providers=ProviderInfo(
                llm_provider=self.settings.llm_provider, embedding_provider=self.settings.embedding_provider
            ),
            documents=document_reads,
            signals=[IntelligenceSignalRead.model_validate(signal) for signal in signals],
            sources=await self._catalog_entries(Source),
            companies=await self._catalog_entries(Company),
            topics=await self._catalog_entries(Topic),
        )

    async def _catalog_entries(self, model: type[Company] | type[Topic] | type[Source]) -> list[CatalogEntryRead]:
        statement = (
            select(model.id, model.name).where(model.workspace_id == self.workspace_id).order_by(func.lower(model.name))
        )
        rows = (await self.session.execute(statement)).all()
        return [CatalogEntryRead(id=row.id, name=row.name) for row in rows]
