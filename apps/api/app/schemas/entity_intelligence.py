from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import CatalogEntryRead
from app.schemas.intelligence import IntelligenceSignalRead
from app.schemas.watchlists import WatchlistRead


class EntityDocumentRef(BaseModel):
    """Narrow reference to a document backing one of the entity's signals -- just enough
    for the dialog's "open original source" link, never the full document body."""

    id: UUID
    source_id: UUID
    canonical_url: str


class EntityIntelligenceResponse(BaseModel):
    signals: list[IntelligenceSignalRead]
    watchlists: list[WatchlistRead]
    documents: list[EntityDocumentRef]
    sources: list[CatalogEntryRead]
