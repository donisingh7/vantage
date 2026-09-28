from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel

from app.models import Watchlist
from app.schemas.companies import CompanyRead
from app.schemas.sources import SourceRead
from app.schemas.topics import TopicRead
from app.schemas.watchlists import WatchlistCounts, WatchlistDetail, WatchlistRead


def with_watchlist_counts[SchemaT: BaseModel](
    schema: type[SchemaT], entities: Sequence[object], counts: dict[UUID, int]
) -> list[SchemaT]:
    return [
        schema.model_validate(entity).model_copy(
            update={"watchlist_count": counts.get(entity.id, 0)}
        )
        for entity in entities
    ]


def to_watchlist_read(watchlist: Watchlist) -> WatchlistRead:
    return WatchlistRead(
        id=watchlist.id,
        workspace_id=watchlist.workspace_id,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
        name=watchlist.name,
        description=watchlist.description,
        is_active=watchlist.is_active,
        counts=WatchlistCounts(
            companies=len(watchlist.companies),
            topics=len(watchlist.topics),
            sources=len(watchlist.sources),
        ),
    )


def to_watchlist_detail(
    watchlist: Watchlist,
    company_counts: dict[UUID, int],
    topic_counts: dict[UUID, int],
    source_counts: dict[UUID, int],
) -> WatchlistDetail:
    base = to_watchlist_read(watchlist)
    return WatchlistDetail(
        **base.model_dump(),
        companies=with_watchlist_counts(CompanyRead, watchlist.companies, company_counts),
        topics=with_watchlist_counts(TopicRead, watchlist.topics, topic_counts),
        sources=with_watchlist_counts(SourceRead, watchlist.sources, source_counts),
    )
