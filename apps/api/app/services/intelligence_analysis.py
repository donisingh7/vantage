"""Turns a collected Document into a structured IntelligenceSignal via the LLMProvider.

Flow: document -> already analyzed? -> structured LLM request -> validate -> discard when
irrelevant -> persist -> deterministic company/topic association -> return.
"""
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import AnalysisStatus, Company, Document, IntelligenceSignal, Source, Topic
from app.providers.llm import LLMProvider
from app.services.analysis_prompts import ANALYSIS_SYSTEM_PROMPT, build_analysis_prompt
from app.services.analysis_schema import DocumentAnalysisResult
from app.services.concurrency import InProcessKeyGuard

MAX_ANALYZE_PENDING_LIMIT = 25
ERROR_MESSAGE_LIMIT = 1500

_analysis_guard = InProcessKeyGuard(conflict_message="Analysis is already running for this document")


class IntelligenceAnalysisService:
    def __init__(self, session: AsyncSession, workspace_id: UUID, llm: LLMProvider) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.llm = llm

    async def _get_document(self, document_id: UUID) -> Document:
        document = await self.session.get(Document, document_id)
        if document is None or document.workspace_id != self.workspace_id:
            raise NotFoundError("Document was not found in this workspace")
        return document

    async def _find_existing(self, document_id: UUID) -> IntelligenceSignal | None:
        statement = select(IntelligenceSignal).where(
            IntelligenceSignal.workspace_id == self.workspace_id,
            IntelligenceSignal.document_id == document_id,
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def analyze_document(self, document_id: UUID, *, force: bool = False) -> IntelligenceSignal:
        async with _analysis_guard.acquire(document_id):
            return await self._analyze_document(document_id, force=force)

    async def _analyze_document(self, document_id: UUID, *, force: bool) -> IntelligenceSignal:
        document = await self._get_document(document_id)
        existing = await self._find_existing(document_id)
        if existing is not None and not force:
            return existing

        source = await self.session.get(Source, document.source_id)
        source_name = source.name if source else "Unknown source"
        source_url = source.url if source else document.canonical_url

        prompt = build_analysis_prompt(
            document_title=document.title,
            document_content=document.content or document.excerpt,
            source_name=source_name,
            source_url=source_url,
        )

        try:
            raw_result = await self.llm.structured_generate(
                prompt, DocumentAnalysisResult, system=ANALYSIS_SYSTEM_PROMPT
            )
            result = (
                raw_result
                if isinstance(raw_result, DocumentAnalysisResult)
                else DocumentAnalysisResult.model_validate(raw_result)
            )
        except Exception as exc:
            return await self._persist_failed(document, existing, str(exc))

        return await self._persist_result(document, existing, result)

    async def _persist_failed(
        self, document: Document, existing: IntelligenceSignal | None, message: str
    ) -> IntelligenceSignal:
        signal = existing or IntelligenceSignal(workspace_id=self.workspace_id, document_id=document.id)
        signal.analysis_status = AnalysisStatus.FAILED
        signal.executive_summary = f"Analysis failed: {message}"[:ERROR_MESSAGE_LIMIT]
        signal.analyzed_at = datetime.now(UTC)
        self.session.add(signal)
        await self.session.commit()
        return signal

    async def _persist_result(
        self, document: Document, existing: IntelligenceSignal | None, result: DocumentAnalysisResult
    ) -> IntelligenceSignal:
        signal = existing or IntelligenceSignal(workspace_id=self.workspace_id, document_id=document.id)

        if not result.relevant:
            signal.analysis_status = AnalysisStatus.IRRELEVANT
            signal.relevance_score = result.relevance_score
            signal.importance_score = 0.0
            signal.signal_type = None
            signal.title = None
            signal.executive_summary = None
            signal.sentiment = None
            signal.key_entities = []
            signal.key_points = []
            signal.business_impact = None
            signal.confidence_score = result.confidence_score
            signal.evidence_excerpt = None
            signal.company_id = None
            signal.topic_id = None
        else:
            company_id, topic_id = await self._match_entities(result.key_entities)
            signal.analysis_status = AnalysisStatus.COMPLETED
            signal.signal_type = result.signal_type
            signal.title = result.title
            signal.executive_summary = result.executive_summary
            signal.relevance_score = result.relevance_score
            signal.importance_score = result.importance_score
            signal.sentiment = result.sentiment
            signal.key_entities = result.key_entities
            signal.key_points = result.key_points
            signal.business_impact = result.business_impact
            signal.confidence_score = result.confidence_score
            signal.evidence_excerpt = result.evidence_excerpt
            signal.company_id = company_id
            signal.topic_id = topic_id

        signal.analyzed_at = datetime.now(UTC)
        self.session.add(signal)
        await self.session.commit()
        return signal

    async def _match_entities(self, key_entities: list[str]) -> tuple[UUID | None, UUID | None]:
        """Deterministic, exact/substring name matching only -- no fuzzy matching or entity-resolution AI."""
        if not key_entities:
            return None, None
        lowered_entities = [entity.lower() for entity in key_entities if entity]

        company_id = None
        companies = (
            await self.session.execute(select(Company).where(Company.workspace_id == self.workspace_id))
        ).scalars().all()
        for company in companies:
            name = company.name.lower()
            if any(name == entity or name in entity or entity in name for entity in lowered_entities):
                company_id = company.id
                break

        topic_id = None
        topics = (
            await self.session.execute(select(Topic).where(Topic.workspace_id == self.workspace_id))
        ).scalars().all()
        for topic in topics:
            name = topic.name.lower()
            if any(name == entity or name in entity or entity in name for entity in lowered_entities):
                topic_id = topic.id
                break

        return company_id, topic_id

    async def analyze_pending(self, *, limit: int = 5) -> list[IntelligenceSignal]:
        """Analyzes up to `limit` not-yet-analyzed documents synchronously. No worker queue."""
        limit = max(1, min(limit, MAX_ANALYZE_PENDING_LIMIT))
        pending_ids = await self._pending_document_ids(limit)
        return [await self.analyze_document(document_id) for document_id in pending_ids]

    async def _pending_document_ids(self, limit: int) -> list[UUID]:
        analyzed_subquery = select(IntelligenceSignal.document_id).where(
            IntelligenceSignal.workspace_id == self.workspace_id
        )
        statement = (
            select(Document.id)
            .where(Document.workspace_id == self.workspace_id, Document.id.not_in(analyzed_subquery))
            .order_by(Document.fetched_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(statement)).scalars().all())

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
