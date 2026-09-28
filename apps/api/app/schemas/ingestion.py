from datetime import datetime
from uuid import UUID

from app.models import CrawlJobStatus
from app.schemas.common import EntityBase


class CrawlJobRead(EntityBase):
    source_id: UUID
    status: CrawlJobStatus
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    documents_found: int
    documents_created: int
    documents_skipped: int
    pages_discovered: int
    pages_failed: int


class DocumentRead(EntityBase):
    source_id: UUID
    canonical_url: str
    title: str | None
    excerpt: str | None
    author: str | None
    published_at: datetime | None
    fetched_at: datetime
    analysis_status: str | None = None
    signal_id: UUID | None = None
    indexed: bool = False
