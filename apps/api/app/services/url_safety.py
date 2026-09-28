"""Practical SSRF guardrails for fetching discovered URLs. Not a full security framework."""
import ipaddress
from urllib.parse import urlsplit

BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}


class UnsafeUrlError(ValueError):
    pass


def ensure_safe_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrlError("Only http and https URLs are allowed")

    host = parts.hostname
    if not host:
        raise UnsafeUrlError("URL must include a host")
    host = host.lower()

    if host in BLOCKED_HOSTNAMES or host.endswith(".local"):
        raise UnsafeUrlError("Requests to local hosts are not allowed")

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return  # A regular hostname; DNS-level SSRF protection is out of scope here.

    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    ):
        raise UnsafeUrlError("Requests to private or internal addresses are not allowed")
