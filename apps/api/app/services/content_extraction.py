"""Extracts readable content from fetched website pages and RSS/Atom feeds."""
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser

import feedparser


@dataclass
class ExtractedWebPage:
    title: str | None
    content: str
    canonical_url: str | None


@dataclass
class ExtractedFeedEntry:
    url: str
    title: str | None
    published_at: datetime | None
    author: str | None
    content: str | None


class _HTMLTextExtractor(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.canonical_url: str | None = None
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "link":
            attr_dict = dict(attrs)
            if (attr_dict.get("rel") or "").lower() == "canonical" and attr_dict.get("href"):
                self.canonical_url = attr_dict["href"]

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
            return
        stripped = data.strip()
        if stripped:
            self.text_parts.append(stripped)


def extract_website_content(html: str) -> ExtractedWebPage:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    parser.close()
    title = " ".join("".join(parser.title_parts).split()) or None
    content = "\n".join(parser.text_parts)
    return ExtractedWebPage(title=title, content=content, canonical_url=parser.canonical_url)


def extract_feed_entries(raw_feed: str | bytes) -> list[ExtractedFeedEntry]:
    parsed = feedparser.parse(raw_feed)
    entries: list[ExtractedFeedEntry] = []
    for entry in parsed.entries:
        link = entry.get("link")
        if not link:
            continue
        published = _parsed_time_to_datetime(entry.get("published_parsed") or entry.get("updated_parsed"))
        content_value = None
        if entry.get("content"):
            content_value = entry["content"][0].get("value")
        elif entry.get("summary"):
            content_value = entry.get("summary")
        entries.append(
            ExtractedFeedEntry(
                url=link,
                title=entry.get("title"),
                published_at=published,
                author=entry.get("author"),
                content=content_value,
            )
        )
    return entries


def _parsed_time_to_datetime(parsed_time) -> datetime | None:
    if not parsed_time:
        return None
    return datetime(*parsed_time[:6], tzinfo=UTC)
