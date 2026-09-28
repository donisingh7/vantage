from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.api.deps import get_source_fetcher
from app.main import app
from app.models import CrawlJobStatus, Document, Source, SourceType
from app.services.content_extraction import extract_feed_entries, extract_website_content
from app.services.fetching import FetchedRecord, FetchError, HttpxSourceFetcher
from app.services.url_normalization import InvalidUrlError, normalize_url

API = "/api/v1"

RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Feed</title>
    <item>
      <title>First article</title>
      <link>https://example.com/first-article?utm_source=newsletter</link>
      <author>jane@example.com (Jane Doe)</author>
      <pubDate>Mon, 01 Sep 2025 12:00:00 GMT</pubDate>
      <description>A short summary of the first article.</description>
    </item>
    <item>
      <title>Second article</title>
      <link>https://example.com/second-article</link>
      <pubDate>Tue, 02 Sep 2025 09:30:00 GMT</pubDate>
      <description>A short summary of the second article.</description>
    </item>
  </channel>
</rss>"""

WEBSITE_FIXTURE = """<!DOCTYPE html>
<html>
<head>
  <title>  Example Page  </title>
  <link rel="canonical" href="https://example.com/canonical-page" />
  <style>.hidden { display: none; }</style>
</head>
<body>
  <script>console.log("ignored");</script>
  <h1>Example Page</h1>
  <p>This is the readable content of the page.</p>
</body>
</html>"""


class FakeFetcher:
    def __init__(self, records=None, error: str | None = None):
        self._records = records or []
        self._error = error

    async def fetch(self, source):
        if self._error:
            raise FetchError(self._error)
        return self._records


def _override_fetcher(fetcher):
    app.dependency_overrides[get_source_fetcher] = lambda: fetcher


async def create_source(client, name="Feed", url="https://example.com/feed", source_type="rss"):
    response = await client.post(
        f"{API}/sources", json={"name": name, "url": url, "source_type": source_type}
    )
    assert response.status_code == 201, response.text
    return response.json()


# -- URL normalization -------------------------------------------------------


def test_normalize_url_lowercases_host_and_strips_fragment_and_trailing_slash():
    assert normalize_url("HTTPS://Example.COM/Path/#section") == "https://example.com/Path"


def test_normalize_url_strips_utm_and_tracking_params():
    assert normalize_url("https://example.com/a?utm_source=x&utm_medium=y&ref=z&id=1") == "https://example.com/a?id=1"


def test_normalize_url_rejects_non_http_scheme():
    with pytest.raises(InvalidUrlError):
        normalize_url("javascript:alert(1)")


def test_normalize_url_rejects_blank_or_hostless_url():
    with pytest.raises(InvalidUrlError):
        normalize_url("")
    with pytest.raises(InvalidUrlError):
        normalize_url("http://")


# -- Content extraction -------------------------------------------------------


def test_extract_website_content_reads_title_text_and_canonical_url():
    page = extract_website_content(WEBSITE_FIXTURE)
    assert page.title == "Example Page"
    assert page.canonical_url == "https://example.com/canonical-page"
    assert "readable content" in page.content
    assert "console.log" not in page.content


def test_extract_feed_entries_parses_rss_fixture():
    entries = extract_feed_entries(RSS_FIXTURE)
    assert [entry.title for entry in entries] == ["First article", "Second article"]
    assert entries[0].url == "https://example.com/first-article?utm_source=newsletter"
    assert entries[0].author == "jane@example.com (Jane Doe)"
    assert entries[0].published_at == datetime(2025, 9, 1, 12, 0, tzinfo=UTC)
    assert "first article" in entries[0].content.lower()


# -- HttpxSourceFetcher against mocked HTTP transport (no live internet) ----


async def test_httpx_fetcher_extracts_website_via_mocked_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=WEBSITE_FIXTURE)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = HttpxSourceFetcher(client=client)
    source = Source(
        workspace_id=uuid4(), name="Site", url="https://example.com/page", source_type=SourceType.WEBSITE
    )

    records = await fetcher.fetch(source)
    assert len(records) == 1
    assert records[0].title == "Example Page"
    assert records[0].url == "https://example.com/canonical-page"
    await client.aclose()


async def test_httpx_fetcher_extracts_rss_via_mocked_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=RSS_FIXTURE)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = HttpxSourceFetcher(client=client)
    source = Source(
        workspace_id=uuid4(), name="Feed", url="https://example.com/feed", source_type=SourceType.RSS
    )

    records = await fetcher.fetch(source)
    assert len(records) == 2
    assert records[0].title == "First article"
    await client.aclose()


async def test_httpx_fetcher_raises_fetch_error_on_http_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = HttpxSourceFetcher(client=client)
    source = Source(
        workspace_id=uuid4(), name="Feed", url="https://example.com/feed", source_type=SourceType.RSS
    )

    with pytest.raises(FetchError):
        await fetcher.fetch(source)
    await client.aclose()


# -- Ingestion job success / failure / dedup / isolation --------------------


async def test_ingestion_success_creates_documents_and_updates_job(client, sessions):
    source = await create_source(client)
    records = [
        FetchedRecord(
            url="https://example.com/a?utm_source=x",
            title="Article A",
            content="Body of article A",
            excerpt="Body of article A",
            author="Author A",
            published_at=datetime(2025, 9, 1, tzinfo=UTC),
        ),
        FetchedRecord(
            url="https://example.com/b",
            title="Article B",
            content="Body of article B",
            excerpt="Body of article B",
            author=None,
            published_at=None,
        ),
    ]
    _override_fetcher(FakeFetcher(records))

    response = await client.post(f"{API}/sources/{source['id']}/ingest")
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["status"] == "completed"
    assert job["documents_found"] == 2
    assert job["documents_created"] == 2
    assert job["error_message"] is None

    documents = await client.get(f"{API}/documents")
    assert documents.json()["total"] == 2
    urls = {item["canonical_url"] for item in documents.json()["items"]}
    assert urls == {"https://example.com/a", "https://example.com/b"}

    async with sessions() as session:
        stored = (await session.execute(Document.__table__.select())).all()
        assert len(stored) == 2


async def test_ingestion_is_idempotent_and_prevents_duplicates(client):
    source = await create_source(client)
    records = [
        FetchedRecord(
            url="https://example.com/a",
            title="Article A",
            content="Body of article A",
            excerpt="Body of article A",
            author="Author A",
            published_at=None,
        )
    ]
    _override_fetcher(FakeFetcher(records))

    first = await client.post(f"{API}/sources/{source['id']}/ingest")
    assert first.json()["documents_created"] == 1

    second = await client.post(f"{API}/sources/{source['id']}/ingest")
    assert second.json()["documents_found"] == 1
    assert second.json()["documents_created"] == 0

    documents = await client.get(f"{API}/documents")
    assert documents.json()["total"] == 1


async def test_ingestion_failure_marks_job_failed_with_error_message(client):
    source = await create_source(client)
    _override_fetcher(FakeFetcher(error="upstream host unreachable"))

    response = await client.post(f"{API}/sources/{source['id']}/ingest")
    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "failed"
    assert "upstream host unreachable" in job["error_message"]
    assert job["documents_created"] == 0

    documents = await client.get(f"{API}/documents")
    assert documents.json()["total"] == 0


async def test_ingestion_jobs_list_and_detail_endpoints(client):
    source = await create_source(client)
    _override_fetcher(FakeFetcher([]))
    created = (await client.post(f"{API}/sources/{source['id']}/ingest")).json()

    jobs = await client.get(f"{API}/ingestion/jobs")
    assert jobs.json()["total"] == 1
    assert jobs.json()["items"][0]["id"] == created["id"]

    detail = await client.get(f"{API}/ingestion/jobs/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]

    missing = await client.get(f"{API}/ingestion/jobs/{uuid4()}")
    assert missing.status_code == 404


async def test_ingestion_respects_workspace_isolation(client, sessions, other_workspace):
    source = await create_source(client)
    _override_fetcher(FakeFetcher([]))
    job = (await client.post(f"{API}/sources/{source['id']}/ingest")).json()

    async with sessions() as session:
        foreign_source = Source(
            workspace_id=other_workspace.id,
            name="Foreign feed",
            url="https://foreign.example/feed",
            source_type=SourceType.RSS,
        )
        session.add(foreign_source)
        await session.commit()
        foreign_source_id = foreign_source.id

    ingest_foreign = await client.post(f"{API}/sources/{foreign_source_id}/ingest")
    assert ingest_foreign.status_code == 404

    async with sessions() as session:
        from app.models import CrawlJob

        foreign_job = CrawlJob(
            workspace_id=other_workspace.id,
            source_id=foreign_source_id,
            status=CrawlJobStatus.COMPLETED,
        )
        session.add(foreign_job)
        await session.commit()
        foreign_job_id = foreign_job.id

    assert (await client.get(f"{API}/ingestion/jobs/{foreign_job_id}")).status_code == 404
    own_jobs = await client.get(f"{API}/ingestion/jobs")
    assert [item["id"] for item in own_jobs.json()["items"]] == [job["id"]]
