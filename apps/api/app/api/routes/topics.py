from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import TopicServiceDep
from app.api.serialization import with_watchlist_counts
from app.schemas.common import ListResponse
from app.schemas.topics import TopicCreate, TopicRead, TopicUpdate

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=ListResponse[TopicRead])
async def list_topics(
    service: TopicServiceDep, search: str | None = Query(default=None, max_length=200)
) -> ListResponse[TopicRead]:
    topics = await service.list(search)
    counts = await service.watchlist_counts([topic.id for topic in topics])
    items = with_watchlist_counts(TopicRead, topics, counts)
    return ListResponse(items=items, total=len(items))


@router.post("", response_model=TopicRead, status_code=status.HTTP_201_CREATED)
async def create_topic(payload: TopicCreate, service: TopicServiceDep) -> TopicRead:
    return TopicRead.model_validate(await service.create(payload))


@router.get("/{topic_id}", response_model=TopicRead)
async def read_topic(topic_id: UUID, service: TopicServiceDep) -> TopicRead:
    topic = await service.get(topic_id)
    counts = await service.watchlist_counts([topic.id])
    return with_watchlist_counts(TopicRead, [topic], counts)[0]


@router.patch("/{topic_id}", response_model=TopicRead)
async def update_topic(topic_id: UUID, payload: TopicUpdate, service: TopicServiceDep) -> TopicRead:
    return TopicRead.model_validate(await service.update(topic_id, payload))


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(topic_id: UUID, service: TopicServiceDep) -> None:
    await service.delete(topic_id)
