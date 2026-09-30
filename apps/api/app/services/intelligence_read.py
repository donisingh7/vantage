"""Read-only intelligence signal queries, deliberately independent of any LLMProvider.

IntelligenceAnalysisService needs an LLMProvider because its write path (analyze_document,
analyze_pending) calls one. Its read methods (list_signals, get_signal, signals_by_document)
never touched the provider at all, but the FastAPI dependency graph for
IntelligenceAnalysisServiceDep still constructs a real Gemini/Azure client for every request
that uses it -- including the read-only /intelligence/signals list/get routes and anything
that needs to display documents' analysis status. IntelligenceReadService duplicates just
those read methods against AsyncSession + workspace_id so listing/reading signals never
requires an AI provider.
"""
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import AnalysisStatus, IntelligenceSignal


class IntelligenceReadService:
    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self.session = session
        self.workspace_id = workspace_id

    async def list_signals(
        self,
        *,
        company_id: UUID | None = None,
        topic_id: UUID | None = None,
        signal_type: str | None = None,
        sentiment: str | None = None,
        min_importance: float | None = None,
    ) -> list[IntelligenceSignal]:
        statement = select(IntelligenceSignal).where(
            IntelligenceSignal.workspace_id == self.workspace_id,
            IntelligenceSignal.analysis_status == AnalysisStatus.COMPLETED,
        )
        if company_id is not None:
            statement = statement.where(IntelligenceSignal.company_id == company_id)
        if topic_id is not None:
            statement = statement.where(IntelligenceSignal.topic_id == topic_id)
        if signal_type is not None:
            statement = statement.where(IntelligenceSignal.signal_type == signal_type)
        if sentiment is not None:
            statement = statement.where(IntelligenceSignal.sentiment == sentiment)
        if min_importance is not None:
            statement = statement.where(IntelligenceSignal.importance_score >= min_importance)
        statement = statement.order_by(
            IntelligenceSignal.importance_score.desc(), IntelligenceSignal.analyzed_at.desc()
        )
        return list((await self.session.execute(statement)).scalars().all())

    async def get_signal(self, signal_id: UUID) -> IntelligenceSignal:
        signal = await self.session.get(IntelligenceSignal, signal_id)
        if signal is None or signal.workspace_id != self.workspace_id:
            raise NotFoundError("Intelligence signal was not found in this workspace")
        return signal

    async def signals_by_document(self, document_ids: Sequence[UUID]) -> dict[UUID, IntelligenceSignal]:
        if not document_ids:
            return {}
        statement = select(IntelligenceSignal).where(
            IntelligenceSignal.workspace_id == self.workspace_id,
            IntelligenceSignal.document_id.in_(document_ids),
        )
        return {signal.document_id: signal for signal in (await self.session.execute(statement)).scalars().all()}
