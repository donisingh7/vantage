"""Optional development seed data: `python -m app.scripts.seed_dev`.

Safe to re-run. Existing records are left untouched.
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import DevelopmentCurrentUserProvider
from app.core.config import get_settings
from app.db.session import SessionFactory
from app.models import Company, Source, SourceType, Topic, Watchlist
from app.services.workspace import WorkspaceContext, resolve_workspace_context

DEMO_NOTE = "Demo data for local development."

COMPANIES = [
    ("Aster Data", "asterdata.example", f"Sample competitor profile. {DEMO_NOTE}"),
    ("Nova Systems", "novasystems.example", f"Sample competitor profile. {DEMO_NOTE}"),
    ("Harbor Analytics", "harboranalytics.example", f"Sample competitor profile. {DEMO_NOTE}"),
]

TOPICS = [
    ("Cloud infrastructure spend", f"Sample monitoring topic. {DEMO_NOTE}"),
    ("Applied AI hiring", f"Sample monitoring topic. {DEMO_NOTE}"),
    ("Data platform regulation", f"Sample monitoring topic. {DEMO_NOTE}"),
]

SOURCES = [
    ("Example Newsroom", "https://example.com/newsroom", SourceType.NEWS),
    ("Example Engineering Blog", "https://example.com/blog", SourceType.BLOG),
    # Real, publicly fetchable sources so ingestion can be demonstrated end to end.
    ("Example Domain", "https://example.com/", SourceType.WEBSITE),
    ("NASA Breaking News", "https://www.nasa.gov/rss/dyn/breaking_news.rss", SourceType.RSS),
]

WATCHLISTS = [
    ("Competitive landscape", f"Sample watchlist. {DEMO_NOTE}"),
    ("Market regulation", f"Sample watchlist. {DEMO_NOTE}"),
]


async def _seed(session: AsyncSession, context: WorkspaceContext) -> dict[str, int]:
    workspace_id = context.workspace.id
    created = {"companies": 0, "topics": 0, "sources": 0, "watchlists": 0}

    async def existing(model, field: str, value: str):
        statement = select(model).where(model.workspace_id == workspace_id, getattr(model, field) == value)
        return (await session.execute(statement)).scalars().first()

    companies = []
    for name, domain, description in COMPANIES:
        record = await existing(Company, "domain", domain)
        if record is None:
            record = Company(workspace_id=workspace_id, name=name, domain=domain, description=description)
            session.add(record)
            created["companies"] += 1
        companies.append(record)

    topics = []
    for name, description in TOPICS:
        record = await existing(Topic, "name", name)
        if record is None:
            record = Topic(workspace_id=workspace_id, name=name, description=description)
            session.add(record)
            created["topics"] += 1
        topics.append(record)

    sources = []
    for name, url, source_type in SOURCES:
        record = await existing(Source, "url", url)
        if record is None:
            record = Source(workspace_id=workspace_id, name=name, url=url, source_type=source_type)
            session.add(record)
            created["sources"] += 1
        sources.append(record)

    await session.flush()

    for index, (name, description) in enumerate(WATCHLISTS):
        watchlist = await existing(Watchlist, "name", name)
        if watchlist is not None:
            continue
        watchlist = Watchlist(workspace_id=workspace_id, name=name, description=description)
        watchlist.companies = companies if index == 0 else companies[:1]
        watchlist.topics = topics[:2] if index == 0 else topics[2:]
        watchlist.sources = sources[:2] if index == 0 else sources[2:]
        session.add(watchlist)
        created["watchlists"] += 1

    await session.commit()
    return created


async def seed_development_data() -> dict[str, int]:
    settings = get_settings()
    current_user = DevelopmentCurrentUserProvider(settings).get_user()
    async with SessionFactory() as session:
        context = await resolve_workspace_context(session, current_user, settings)
        created = await _seed(session, context)
    return created


def main() -> None:
    created = asyncio.run(seed_development_data())
    summary = ", ".join(f"{count} {name}" for name, count in created.items())
    print(f"Development seed complete. Newly created: {summary}.")


if __name__ == "__main__":
    main()
