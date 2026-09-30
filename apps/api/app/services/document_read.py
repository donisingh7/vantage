"""Read-only document listing, enriched with analysis status and index state.

Constructs no LLM or embedding provider: analysis status comes from IntelligenceReadService
(a plain DB read), and "indexed" is computed via embedding_fingerprint.document_is_indexed(),
which mirrors the configured embedding provider's fingerprint from Settings.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Document
from app.schemas.ingestion import DocumentRead
from app.services.embedding_fingerprint import document_is_indexed
from app.services.intelligence_read import IntelligenceReadService


class DocumentReadService:
    def __init__(self, session: AsyncSession, workspace_id: UUID, settings: Settings) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.settings = settings
        self.reads = IntelligenceReadService(session, workspace_id)

    async def list(self, source_id: UUID | None = None) -> list[DocumentRead]:
        statement = select(Document).where(Document.workspace_id == self.workspace_id)
        if source_id is not None:
            statement = statement.where(Document.source_id == source_id)
        statement = statement.order_by(Document.fetched_at.desc())
        documents = list((await self.session.execute(statement)).scalars().all())

        signals = await self.reads.signals_by_document([document.id for document in documents])
        return [
            DocumentRead.model_validate(document).model_copy(
                update={
                    "analysis_status": signals[document.id].analysis_status.value if document.id in signals else None,
                    "signal_id": signals[document.id].id if document.id in signals else None,
                    "indexed": document_is_indexed(document, self.settings),
                }
            )
            for document in documents
        ]
