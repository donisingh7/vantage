import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from app.core.exceptions import ConflictError
from app.models import CrawlJob, IngestionInterval, Source, SourceType
from app.services.fetching import FetchedRecord, FetchError, HttpxSourceFetcher, WebsitePage
from app.services.ingestion import IngestionService
from app.services.link_discovery import discover_links
from app.services.scheduler import is_due
from app.services.url_safety import UnsafeUrlError, ensure_safe_url

API = "/api/v1"

PAGE_WITH_LINKS = """<!DOCTYPE html>
<html><head><title>Home</title></head>
<body>
  <a href="/articles/first">First article</a>
  <a href="/articles/second">Second article</a>
  <a href="https://example.com/articles/first">Duplicate of first (absolute)</a>
  <a href="https://example.com/articles/first#section">Duplicate with fragment</a>
  <a href="https://other-domain.com/off-site">Off-site link</a>
  <a href="https://facebook.com/example">Social link</a>
  <a href="/login">Login link</a>
  <a href="/assets/photo.jpg">Image asset</a>
  <a href="/assets/app.js">Script asset</a>
  <a href="mailto:hello@example.com">Email us</a>
  <a href="/articles/third">Third article</a>
</body></html>"""


def _many_links_page(count: int) -> str:
    links = "\n".join(f'<a href="/articles/{i}">Article {i}</a>' for i in range(count))
    return f"<html><body>{links}</body></html>"


# -- Link discovery -----------------------------------------------------------


def test_discover_links_filters_offsite_social_login_and_asset_links():
    discovered = discover_links(PAGE_WITH_LINKS, "https://example.com/", limit=10)
    assert discovered == [
        "https://example.com/articles/first",
        "https://example.com/articles/second",
        "https://example.com/articles/third",
    ]


def test_discover_links_respects_same_domain_restriction():
    html = '<a href="https://other-domain.com/x">x</a><a href="https://example.com/y">y</a>'
    discovered = discover_links(html, "https://example.com/", limit=10)
    assert discovered == ["https://example.com/y"]

    unrestricted = discover_links(html, "https://example.com/", limit=10, same_domain=False)
    assert set(unrestricted) == {"https://other-domain.com/x", "https://example.com/y"}


def test_discover_links_is_bounded_by_limit():
    html = _many_links_page(25)
    discovered = discover_links(html, "https://example.com/", limit=10)
    assert len(discovered) == 10


# -- URL safety -----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://10.0.0.5/internal",
        "http://169.254.169.254/latest/meta-data",
        "http://192.168.1.1/",
        "ftp://example.com/file",
        "http://",
    ],
)
def test_ensure_safe_url_rejects_local_private_and_malformed_urls(url):
    with pytest.raises(UnsafeUrlError):
        ensure_safe_url(url)


def test_ensure_safe_url_accepts_public_hosts():
    ensure_safe_url("https://example.com/page")
    ensure_safe_url("http://93.184.216.34/page")  # a public IP literal


# -- Website ingestion with discovery and partial failure --------------------


class FakeWebsiteFetcher:
    def __init__(self, pages: dict[str, WebsitePage], delay: float = 0.0):
        self._pages = pages
        self._delay = delay

    async def fetch(self, source):  # pragma: no cover - website path uses fetch_page
        raise AssertionError("fetch() should not be used for website sources")

    async def fetch_page(self, url: str) -> WebsitePage:
        if self._delay:
            await asyncio.sleep(self._delay)
        if url not in self._pages:
            raise FetchError(f"no fixture configured for {url}")
        return self._pages[url]


def _page(url: str, html: str, title: str = "Title") -> WebsitePage:
    return WebsitePage(
        record=FetchedRecord(url=url, title=title, content=f"Body for {url}", excerpt=None, author=None, published_at=None),
        html=html,
    )


async def create_website_source(client, url="https://example.com/"):
    response = await client.post(
        f"{API}/sources", json={"name": "Site", "url": url, "source_type": "website"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_website_ingestion_discovers_and_fetches_linked_pages(client):
    source = await create_website_source(client)
    home_html = '<a href="/a">a</a><a href="/b">b</a>'
    pages = {
        "https://example.com/": _page("https://example.com/", home_html, title="Home"),
        "https://example.com/a": _page("https://example.com/a", "<html></html>", title="A"),
        "https://example.com/b": _page("https://example.com/b", "<html></html>", title="B"),
    }
    from app.api.deps import get_source_fetcher
    from app.main import app

    app.dependency_overrides[get_source_fetcher] = lambda: FakeWebsiteFetcher(pages)

    response = await client.post(f"{API}/sources/{source['id']}/ingest")
    job = response.json()
    assert job["status"] == "completed"
    assert job["pages_discovered"] == 2
    assert job["pages_failed"] == 0
    assert job["documents_found"] == 3
    assert job["documents_created"] == 3

    documents = await client.get(f"{API}/documents")
    assert documents.json()["total"] == 3


async def test_website_ingestion_one_failed_page_does_not_fail_whole_run(client):
    source = await create_website_source(client)
    home_html = '<a href="/a">a</a><a href="/b">b</a>'
    pages = {
        "https://example.com/": _page("https://example.com/", home_html, title="Home"),
        "https://example.com/a": _page("https://example.com/a", "<html></html>", title="A"),
        # "/b" intentionally missing from fixtures -> fetch_page raises FetchError for it
    }
    from app.api.deps import get_source_fetcher
    from app.main import app

    app.dependency_overrides[get_source_fetcher] = lambda: FakeWebsiteFetcher(pages)

    response = await client.post(f"{API}/sources/{source['id']}/ingest")
    job = response.json()
    assert job["status"] == "completed"
    assert job["pages_discovered"] == 2
    assert job["pages_failed"] == 1
    assert job["documents_found"] == 2
    assert job["documents_created"] == 2


async def test_website_ingestion_fails_job_only_when_main_page_fetch_fails(client):
    source = await create_website_source(client, url="https://example.com/missing")
    from app.api.deps import get_source_fetcher
    from app.main import app

    app.dependency_overrides[get_source_fetcher] = lambda: FakeWebsiteFetcher({})

    response = await client.post(f"{API}/sources/{source['id']}/ingest")
    job = response.json()
    assert job["status"] == "failed"
    assert job["error_message"]


# -- Browser fallback (mocked) --------------------------------------------


class FakeBrowser:
    def __init__(self, html: str):
        self._html = html
        self.calls = 0

    async def render(self, url: str) -> str:
        self.calls += 1
        return self._html


async def test_httpx_fetcher_falls_back_to_browser_when_http_content_is_thin():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body><p>hi</p></body></html>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    browser = FakeBrowser("<html><body>" + ("Rendered content. " * 30) + "</body></html>")
    fetcher = HttpxSourceFetcher(client=client, browser=browser, min_content_length_for_browser=200)

    page = await fetcher.fetch_page("https://example.com/app")
    assert browser.calls == 1
    assert "Rendered content" in (page.record.content or "")
    await client.aclose()


async def test_httpx_fetcher_keeps_http_content_when_it_is_already_sufficient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>" + ("Plenty of readable text. " * 20) + "</body></html>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    browser = FakeBrowser("<html><body>should not be used</body></html>")
    fetcher = HttpxSourceFetcher(client=client, browser=browser, min_content_length_for_browser=50)

    page = await fetcher.fetch_page("https://example.com/article")
    assert browser.calls == 0
    assert "should not be used" not in (page.record.content or "")
    await client.aclose()


async def test_httpx_fetcher_survives_browser_failure_and_keeps_http_result():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>short</body></html>")

    class BrokenBrowser:
        async def render(self, url: str) -> str:
            raise RuntimeError("browser crashed")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = HttpxSourceFetcher(client=client, browser=BrokenBrowser(), min_content_length_for_browser=200)

    page = await fetcher.fetch_page("https://example.com/app")
    assert page.record.content == "short"
    await client.aclose()


async def test_httpx_fetcher_retries_on_server_error_then_succeeds():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(500, text="server error")
        return httpx.Response(200, text="<html><body>ok</body></html>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = HttpxSourceFetcher(client=client, max_retries=2, retry_backoff=0)

    page = await fetcher.fetch_page("https://example.com/")
    assert attempts["count"] == 2
    assert page.record.content == "ok"
    await client.aclose()


async def test_httpx_fetcher_does_not_retry_on_client_error():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404, text="not found")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = HttpxSourceFetcher(client=client, max_retries=3, retry_backoff=0)

    with pytest.raises(FetchError):
        await fetcher.fetch_page("https://example.com/missing")
    assert attempts["count"] == 1


# -- Duplicate concurrent source run protection ------------------------------


class SlowFetcher:
    def __init__(self, delay: float):
        self._delay = delay

    async def fetch(self, source):
        await asyncio.sleep(self._delay)
        return []

    async def fetch_page(self, url: str) -> WebsitePage:  # pragma: no cover - rss path used in this test
        raise AssertionError("not used")


async def test_ingestion_service_blocks_concurrent_runs_for_same_source(sessions):
    async with sessions() as session:
        from app.auth.dependencies import DevelopmentCurrentUserProvider
        from app.core.config import get_settings
        from app.services.workspace import resolve_workspace_context

        settings = get_settings()
        current_user = DevelopmentCurrentUserProvider(settings).get_user()
        context = await resolve_workspace_context(session, current_user, settings)

        source = Source(
            workspace_id=context.workspace.id, name="Feed", url="https://example.com/feed", source_type=SourceType.RSS
        )
        session.add(source)
        await session.commit()

        fetcher = SlowFetcher(delay=0.05)
        service = IngestionService(session, context.workspace.id, fetcher)

        results = await asyncio.gather(
            service.run(source.id), service.run(source.id), return_exceptions=True
        )

    successes = [r for r in results if isinstance(r, CrawlJob)]
    conflicts = [r for r in results if isinstance(r, ConflictError)]
    assert len(successes) == 1
    assert len(conflicts) == 1


# -- Scheduling configuration --------------------------------------------


def _source(interval: IngestionInterval, is_active: bool = True) -> Source:
    return Source(
        id=uuid4(), workspace_id=uuid4(), name="S", url="https://example.com/",
        source_type=SourceType.RSS, is_active=is_active, ingestion_interval=interval,
    )


def test_manual_interval_is_never_due():
    now = datetime.now(UTC)
    assert is_due(_source(IngestionInterval.MANUAL), None, now=now) is False


def test_source_with_no_prior_job_is_due_when_scheduled():
    now = datetime.now(UTC)
    assert is_due(_source(IngestionInterval.EVERY_6_HOURS), None, now=now) is True


def test_source_is_not_due_before_interval_elapses():
    now = datetime.now(UTC)
    last_job = CrawlJob(id=uuid4(), workspace_id=uuid4(), source_id=uuid4(), completed_at=now - timedelta(hours=1))
    assert is_due(_source(IngestionInterval.EVERY_6_HOURS), last_job, now=now) is False


def test_source_is_due_after_interval_elapses():
    now = datetime.now(UTC)
    last_job = CrawlJob(id=uuid4(), workspace_id=uuid4(), source_id=uuid4(), completed_at=now - timedelta(hours=7))
    assert is_due(_source(IngestionInterval.EVERY_6_HOURS), last_job, now=now) is True


def test_inactive_source_is_never_due():
    now = datetime.now(UTC)
    assert is_due(_source(IngestionInterval.EVERY_6_HOURS, is_active=False), None, now=now) is False


async def test_source_api_accepts_and_returns_ingestion_interval(client):
    created = await client.post(
        f"{API}/sources",
        json={"name": "Scheduled", "url": "https://example.com/scheduled", "source_type": "rss", "ingestion_interval": "every_12_hours"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["ingestion_interval"] == "every_12_hours"

    updated = await client.patch(
        f"{API}/sources/{created.json()['id']}", json={"ingestion_interval": "every_24_hours"}
    )
    assert updated.json()["ingestion_interval"] == "every_24_hours"
