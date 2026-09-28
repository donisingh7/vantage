"""Discovers a bounded set of same-domain page links from a fetched HTML page.

This is not a general spider: depth is limited to the links found on one page,
and the caller further limits how many discovered pages get fetched.
"""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from app.services.url_normalization import InvalidUrlError, normalize_url

ASSET_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".css", ".js", ".mjs", ".json",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".gz", ".tar", ".rar",
    ".mp3", ".mp4", ".mov", ".avi", ".wav",
}
SKIP_HOST_FRAGMENTS = (
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com",
    "youtube.com", "pinterest.com", "reddit.com", "tiktok.com", "whatsapp.com",
)
SKIP_PATH_FRAGMENTS = (
    "login", "signin", "sign-in", "signup", "sign-up", "logout", "register", "share",
)
SKIP_SCHEMES = {"mailto", "tel", "javascript"}


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def _is_asset(path: str) -> bool:
    lowered = path.lower()
    return any(lowered.endswith(extension) for extension in ASSET_EXTENSIONS)


def _is_skippable(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme in SKIP_SCHEMES:
        return True
    host = (parts.hostname or "").lower()
    if any(fragment in host for fragment in SKIP_HOST_FRAGMENTS):
        return True
    path_and_query = f"{parts.path}?{parts.query}".lower()
    if any(fragment in path_and_query for fragment in SKIP_PATH_FRAGMENTS):
        return True
    return _is_asset(parts.path)


def _host_of(url: str) -> str:
    host = urlsplit(url).hostname or ""
    host = host.lower()
    return host.removeprefix("www.")


def discover_links(html: str, base_url: str, *, limit: int = 10, same_domain: bool = True) -> list[str]:
    parser = _LinkExtractor()
    parser.feed(html)
    parser.close()

    if limit <= 0:
        return []

    base_host = _host_of(base_url)
    try:
        base_normalized = normalize_url(base_url)
    except InvalidUrlError:
        base_normalized = None

    discovered: list[str] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        absolute = urljoin(base_url, href)
        if _is_skippable(absolute):
            continue
        try:
            normalized = normalize_url(absolute)
        except InvalidUrlError:
            continue
        if normalized == base_normalized or normalized in seen:
            continue
        if same_domain and _host_of(normalized) != base_host:
            continue

        seen.add(normalized)
        discovered.append(normalized)
        if len(discovered) >= limit:
            break
    return discovered
