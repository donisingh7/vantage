from pydantic import BaseModel, Field

from app.models import Sentiment, SignalType


class DocumentAnalysisResult(BaseModel):
    """Structured-output contract the LLM provider fills in for one document."""

    relevant: bool
    relevance_score: float = Field(ge=0, le=1)
    signal_type: SignalType
    title: str
    executive_summary: str
    importance_score: float = Field(ge=0, le=1)
    sentiment: Sentiment
    key_entities: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    business_impact: str
    confidence_score: float = Field(ge=0, le=1)
    evidence_excerpt: str
