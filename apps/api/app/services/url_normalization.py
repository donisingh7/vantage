"""Canonicalizes URLs so ingestion can deduplicate by a stable, comparable form."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {"gclid", "fbclid", "mc_cid", "mc_eid", "igshid", "ref"}
DEFAULT_PORTS = {"http": 80, "https": 443}


class InvalidUrlError(ValueError):
    pass


def normalize_url(raw_url: str) -> str:
    candidate = (raw_url or "").strip()
    if not candidate:
        raise InvalidUrlError("URL cannot be blank")

    parts = urlsplit(candidate)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise InvalidUrlError("Only http and https URLs are supported")

    host = parts.hostname
    if not host:
        raise InvalidUrlError("URL must include a host")
    host = host.lower()
    port = parts.port
    netloc = host if port is None or port == DEFAULT_PORTS.get(scheme) else f"{host}:{port}"

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"

    query_pairs = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    )
    query = urlencode(query_pairs)

    return urlunsplit((scheme, netloc, path, query, ""))
