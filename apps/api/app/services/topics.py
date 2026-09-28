from uuid import UUID

from sqlalchemy import func, select

from app.models import Topic, watchlist_topics
from app.schemas.topics import TopicCreate, TopicUpdate
from app.services.base import WorkspaceResourceService


class TopicService(WorkspaceResourceService[Topic]):
    model = Topic
    label = "Topic"
    search_fields = ("name",)
    link_table = watchlist_topics
    link_column = "topic_id"

    async def create(self, payload: TopicCreate) -> Topic:
        statement = select(Topic.id).where(
            Topic.workspace_id == self.workspace_id,
            func.lower(Topic.name) == payload.name.lower(),
        )
        if (await self.session.execute(statement)).first():
            from app.core.exceptions import ConflictError

            raise ConflictError("A topic with this name already exists in this workspace")
        topic = Topic(workspace_id=self.workspace_id, **payload.model_dump())
        await self.repository.add(topic)
        await self.session.commit()
        return topic

    async def update(self, topic_id: UUID, payload: TopicUpdate) -> Topic:
        topic = await self.get(topic_id)
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes:
            statement = select(Topic.id).where(
                Topic.workspace_id == self.workspace_id,
                Topic.id != topic_id,
                func.lower(Topic.name) == changes["name"].lower(),
            )
            if (await self.session.execute(statement)).first():
                from app.core.exceptions import ConflictError

                raise ConflictError("A topic with this name already exists in this workspace")
        self.apply_changes(topic, changes)
        await self.session.commit()
        return topic
