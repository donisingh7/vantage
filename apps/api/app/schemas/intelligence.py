from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import AnalysisStatus, Sentiment, SignalType
from app.schemas.common import EntityBase


class IntelligenceSignalRead(EntityBase):
    document_id: UUID
    company_id: UUID | None
    topic_id: UUID | None
    signal_type: SignalType | None
    title: str | None
    executive_summary: str | None
    relevance_score: float
    importance_score: float
    sentiment: Sentiment | None
    key_entities: list[str]
    key_points: list[str]
    business_impact: str | None
    confidence_score: float
    evidence_excerpt: str | None
    analysis_status: AnalysisStatus
    analyzed_at: datetime


class AnalyzePendingRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=25)


class AnalyzePendingResult(BaseModel):
    analyzed: int
    signals: list[IntelligenceSignalRead]
