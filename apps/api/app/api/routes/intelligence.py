from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import (
    EntityIntelligenceServiceDep,
    IntelligenceAnalysisServiceDep,
    IntelligenceBootstrapServiceDep,
    IntelligenceReadServiceDep,
)
from app.api.serialization import to_watchlist_read
from app.models import Sentiment, SignalType
from app.schemas.common import ListResponse
from app.schemas.entity_intelligence import EntityDocumentRef, EntityIntelligenceResponse
from app.schemas.intelligence import (
    AnalyzePendingRequest,
    AnalyzePendingResult,
    IntelligenceBootstrapResponse,
    IntelligenceSignalRead,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/bootstrap", response_model=IntelligenceBootstrapResponse)
async def read_intelligence_bootstrap(service: IntelligenceBootstrapServiceDep) -> IntelligenceBootstrapResponse:
    """Everything the Intelligence page needs for its first render, in one request."""
    data = await service.bootstrap()
    return IntelligenceBootstrapResponse(
        providers=data.providers,
        documents=data.documents,
        signals=data.signals,
        sources=data.sources,
        companies=data.companies,
        topics=data.topics,
    )


@router.get("/entities/{kind}/{entity_id}", response_model=EntityIntelligenceResponse)
async def read_entity_intelligence(
    kind: Literal["company", "topic"], entity_id: UUID, service: EntityIntelligenceServiceDep
) -> EntityIntelligenceResponse:
    """Everything the Entity Intelligence dialog needs for one company/topic, in one request."""
    data = await service.for_entity(kind, entity_id)
    return EntityIntelligenceResponse(
        signals=[IntelligenceSignalRead.model_validate(signal) for signal in data.signals],
        watchlists=[to_watchlist_read(watchlist) for watchlist in data.watchlists],
        documents=[
            EntityDocumentRef(id=doc.id, source_id=doc.source_id, canonical_url=doc.canonical_url)
            for doc in data.documents
        ],
        sources=data.sources,
    )


@router.post("/analyze-pending", response_model=AnalyzePendingResult)
async def analyze_pending(
    service: IntelligenceAnalysisServiceDep, payload: AnalyzePendingRequest | None = None
) -> AnalyzePendingResult:
    limit = payload.limit if payload is not None else 5
    signals = await service.analyze_pending(limit=limit)
    return AnalyzePendingResult(
        analyzed=len(signals), signals=[IntelligenceSignalRead.model_validate(signal) for signal in signals]
    )


@router.get("/signals", response_model=ListResponse[IntelligenceSignalRead])
async def list_signals(
    service: IntelligenceReadServiceDep,
    company_id: UUID | None = Query(default=None),
    topic_id: UUID | None = Query(default=None),
    signal_type: SignalType | None = Query(default=None),
    sentiment: Sentiment | None = Query(default=None),
    min_importance: float | None = Query(default=None, ge=0, le=1),
) -> ListResponse[IntelligenceSignalRead]:
    signals = await service.list_signals(
        company_id=company_id, topic_id=topic_id, signal_type=signal_type,
        sentiment=sentiment, min_importance=min_importance,
    )
    items = [IntelligenceSignalRead.model_validate(signal) for signal in signals]
    return ListResponse(items=items, total=len(items))


@router.get("/signals/{signal_id}", response_model=IntelligenceSignalRead)
async def read_signal(signal_id: UUID, service: IntelligenceReadServiceDep) -> IntelligenceSignalRead:
    return IntelligenceSignalRead.model_validate(await service.get_signal(signal_id))
