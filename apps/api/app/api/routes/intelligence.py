from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import IntelligenceAnalysisServiceDep
from app.models import Sentiment, SignalType
from app.schemas.common import ListResponse
from app.schemas.intelligence import (
    AnalyzePendingRequest,
    AnalyzePendingResult,
    IntelligenceSignalRead,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


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
    service: IntelligenceAnalysisServiceDep,
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
async def read_signal(signal_id: UUID, service: IntelligenceAnalysisServiceDep) -> IntelligenceSignalRead:
    return IntelligenceSignalRead.model_validate(await service.get_signal(signal_id))
