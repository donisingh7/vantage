from urllib.parse import urlsplit

MAX_DOMAIN_LENGTH = 253


def normalize_domain(value: str | None) -> str | None:
    """Accepts pasted URLs or bare hostnames and stores a comparable host."""
    if value is None:
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    if "//" in candidate:
        candidate = urlsplit(candidate).netloc or candidate
    candidate = candidate.split("/")[0].split("@")[-1].split(":")[0]
    candidate = candidate.removeprefix("www.")
    candidate = candidate.strip(".")
    if not candidate or "." not in candidate or " " in candidate:
        raise ValueError("Enter a valid domain, for example example.com")
    if len(candidate) > MAX_DOMAIN_LENGTH:
        raise ValueError("Domain is too long")
    return candidate


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None
