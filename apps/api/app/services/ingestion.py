"""Orchestrates source -> discover -> fetch -> extract -> normalize -> deduplicate -> persist."""
import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models import CrawlJob, CrawlJobStatus, Document, Source, SourceType
from app.services.fetching import FetchedRecord, FetchError, SourceFetcher
from app.services.link_discovery import discover_links
from app.services.url_normalization import InvalidUrlError, normalize_url
from app.services.url_safety import UnsafeUrlError, ensure_safe_url

ERROR_MESSAGE_LIMIT = 2000

# In-process guard against overlapping ingestion runs for the same source.
# This is intentionally not a distributed lock: scheduling here is single-process.
_running_source_ids: set[UUID] = set()


class IngestionService:
    def __init__(
        self,
        session: AsyncSession,
        workspace_id: UUID,
        fetcher: SourceFetcher,
        *,
        max_discovered_pages: int = 10,
    ) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.fetcher = fetcher
        self.max_discovered_pages = max_discovered_pages

    async def _get_source(self, source_id: UUID) -> Source:
        source = await self.session.get(Source, source_id)
        if source is None or source.workspace_id != self.workspace_id:
            raise NotFoundError("Source was not found in this workspace")
        return source

    async def run(self, source_id: UUID) -> CrawlJob:
        if source_id in _running_source_ids:
            raise ConflictError("Ingestion is already running for this source")
        _running_source_ids.add(source_id)
        try:
            return await self._run(source_id)
        finally:
            _running_source_ids.discard(source_id)

    async def _run(self, source_id: UUID) -> CrawlJob:
        source = await self._get_source(source_id)
        job = CrawlJob(workspace_id=self.workspace_id, source_id=source.id, status=CrawlJobStatus.QUEUED)
        self.session.add(job)
        await self.session.flush()

        job.status = CrawlJobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        await self.session.flush()

        try:
            if source.source_type == SourceType.WEBSITE:
                records, discovered_count, failed_count = await self._collect_website(source)
            else:
                records = await self.fetcher.fetch(source)
                discovered_count = len(records)
                failed_count = 0
        except FetchError as exc:
            job.status = CrawlJobStatus.FAILED
            job.completed_at = datetime.now(UTC)
            job.error_message = str(exc)[:ERROR_MESSAGE_LIMIT]
            await self.session.commit()
            return job

        job.pages_discovered = discovered_count
        job.pages_failed = failed_count
        job.documents_found = len(records)

        created = 0
        skipped = 0
        for record in records:
            if await self._store_record(source, record):
                created += 1
            else:
                skipped += 1

        job.documents_created = created
        job.documents_skipped = skipped
        job.status = CrawlJobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        await self.session.commit()
        return job

    async def _collect_website(self, source: Source) -> tuple[list[FetchedRecord], int, int]:
        """Fetches the source page plus a bounded set of same-domain links found on it.

        One failed discovered page is skipped and counted, not raised; only a failure
        to fetch the source page itself fails the whole run.
        """
        main_page = await self.fetcher.fetch_page(source.url)
        records = [main_page.record]

        try:
            discovered_urls = discover_links(main_page.html, source.url, limit=self.max_discovered_pages)
        except Exception:
            discovered_urls = []

        failed = 0
        for url in discovered_urls:
            try:
                ensure_safe_url(url)
                page = await self.fetcher.fetch_page(url)
            except (FetchError, UnsafeUrlError):
                failed += 1
                continue
            records.append(page.record)

        return records, len(discovered_urls), failed

    async def _store_record(self, source: Source, record: FetchedRecord) -> bool:
        try:
            canonical_url = normalize_url(record.url)
        except InvalidUrlError:
            return False

        content_hash = hashlib.sha256(
            (record.content or record.title or canonical_url).encode("utf-8")
        ).hexdigest()

        existing_by_url = (
            await self.session.execute(
                select(Document).where(
                    Document.workspace_id == self.workspace_id,
                    Document.canonical_url == canonical_url,
                )
            )
        ).scalar_one_or_none()
        if existing_by_url is not None:
            existing_by_url.content_hash = content_hash
            existing_by_url.title = record.title or existing_by_url.title
            existing_by_url.content = record.content or existing_by_url.content
            existing_by_url.excerpt = record.excerpt or existing_by_url.excerpt
            existing_by_url.author = record.author or existing_by_url.author
            existing_by_url.published_at = record.published_at or existing_by_url.published_at
            existing_by_url.fetched_at = datetime.now(UTC)
            return False

        duplicate_by_hash = (
            await self.session.execute(
                select(Document).where(
                    Document.workspace_id == self.workspace_id,
                    Document.source_id == source.id,
                    Document.content_hash == content_hash,
                )
            )
        ).scalar_one_or_none()
        if duplicate_by_hash is not None:
            return False

        document = Document(
            workspace_id=self.workspace_id,
            source_id=source.id,
            canonical_url=canonical_url,
            title=record.title,
            content=record.content,
            excerpt=record.excerpt,
            author=record.author,
            published_at=record.published_at,
            content_hash=content_hash,
            fetched_at=datetime.now(UTC),
        )
        self.session.add(document)
        await self.session.flush()
        return True

    async def list_jobs(self, source_id: UUID | None = None) -> list[CrawlJob]:
        statement = select(CrawlJob).where(CrawlJob.workspace_id == self.workspace_id)
        if source_id is not None:
            statement = statement.where(CrawlJob.source_id == source_id)
        statement = statement.order_by(CrawlJob.created_at.desc())
        return list((await self.session.execute(statement)).scalars().all())

    async def get_job(self, job_id: UUID) -> CrawlJob:
        job = await self.session.get(CrawlJob, job_id)
        if job is None or job.workspace_id != self.workspace_id:
            raise NotFoundError("Ingestion job was not found in this workspace")
        return job

    async def list_documents(self, source_id: UUID | None = None) -> list[Document]:
        statement = select(Document).where(Document.workspace_id == self.workspace_id)
        if source_id is not None:
            statement = statement.where(Document.source_id == source_id)
        statement = statement.order_by(Document.fetched_at.desc())
        return list((await self.session.execute(statement)).scalars().all())
