"""Fetches source content over HTTP, with bounded retries and an optional browser fallback."""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from app.models import Source, SourceType
from app.services.content_extraction import extract_feed_entries, extract_website_content
from app.services.url_safety import ensure_safe_url

USER_AGENT = "VantageIngestionBot/0.1 (+https://vantage.local)"
EXCERPT_LENGTH = 280


@dataclass
class FetchedRecord:
    url: str
    title: str | None
    content: str | None
    excerpt: str | None
    author: str | None
    published_at: datetime | None


@dataclass
class WebsitePage:
    record: FetchedRecord
    html: str


class FetchError(Exception):
    pass


class SourceFetcher(Protocol):
    async def fetch(self, source: Source) -> list[FetchedRecord]: ...

    async def fetch_page(self, url: str) -> WebsitePage: ...


class BrowserFetcher(Protocol):
    async def render(self, url: str) -> str: ...


class PlaywrightBrowserFetcher:
    """Renders JavaScript-heavy pages with a headless browser.

    Requires the `playwright` package and its browser binaries
    (`playwright install chromium`). Used only as a fallback when plain
    HTTP extraction yields too little content; never used first.
    """

    def __init__(self, timeout_ms: int = 15000) -> None:
        self._timeout_ms = timeout_ms

    async def render(self, url: str) -> str:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=self._timeout_ms, wait_until="networkidle")
                return await page.content()
            finally:
                await browser.close()


class HttpxSourceFetcher:
    """Fetches website pages and RSS/Atom feeds over HTTP with bounded, backed-off retries."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        connect_timeout: float = 5.0,
        read_timeout: float = 15.0,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        browser: BrowserFetcher | None = None,
        min_content_length_for_browser: int = 200,
    ) -> None:
        self._client = client
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._browser = browser
        self._min_content_length_for_browser = min_content_length_for_browser

    async def fetch(self, source: Source) -> list[FetchedRecord]:
        if source.source_type == SourceType.WEBSITE:
            page = await self.fetch_page(source.url)
            return [page.record]
        if source.source_type == SourceType.RSS:
            return await self._fetch_rss(source.url)
        raise FetchError(f"Fetching is not implemented for source type '{source.source_type.value}'")

    async def fetch_page(self, url: str) -> WebsitePage:
        response = await self._get(url)
        page = extract_website_content(response.text)
        html = response.text

        content_length = len((page.content or "").strip())
        if self._browser is not None and content_length < self._min_content_length_for_browser:
            try:
                rendered_html = await self._browser.render(url)
                rendered_page = extract_website_content(rendered_html)
                if len((rendered_page.content or "").strip()) > content_length:
                    page = rendered_page
                    html = rendered_html
            except Exception:
                pass  # The browser fallback is best-effort; keep the HTTP result on failure.

        canonical = page.canonical_url or str(response.url)
        excerpt = page.content[:EXCERPT_LENGTH].strip() if page.content else None
        record = FetchedRecord(
            url=canonical,
            title=page.title,
            content=page.content or None,
            excerpt=excerpt or None,
            author=None,
            published_at=None,
        )
        return WebsitePage(record=record, html=html)

    async def _fetch_rss(self, url: str) -> list[FetchedRecord]:
        response = await self._get(url)
        entries = extract_feed_entries(response.text)
        records = []
        for entry in entries:
            excerpt = entry.content[:EXCERPT_LENGTH].strip() if entry.content else None
            records.append(
                FetchedRecord(
                    url=entry.url,
                    title=entry.title,
                    content=entry.content,
                    excerpt=excerpt or None,
                    author=entry.author,
                    published_at=entry.published_at,
                )
            )
        return records

    async def _get(self, url: str) -> httpx.Response:
        ensure_safe_url(url)
        client = self._client
        owns_client = client is None
        if owns_client:
            timeout = httpx.Timeout(
                connect=self._connect_timeout,
                read=self._read_timeout,
                write=self._read_timeout,
                pool=self._read_timeout,
            )
            client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)
        try:
            last_error: Exception | None = None
            for attempt in range(self._max_retries + 1):
                try:
                    response = await client.get(url, headers={"User-Agent": USER_AGENT})
                    response.raise_for_status()
                    return response
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code < 500:
                        raise FetchError(f"Could not fetch {url}: {exc}") from exc
                    last_error = exc
                except httpx.HTTPError as exc:
                    last_error = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_backoff * (2**attempt))
            raise FetchError(f"Could not fetch {url}: {last_error}") from last_error
        finally:
            if owns_client:
                await client.aclose()
