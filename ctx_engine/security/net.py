"""Outbound HTTP helpers: scheme allow-listing for urllib calls."""

from __future__ import annotations

import urllib.request
from typing import Any
from urllib.parse import urlparse

ALLOWED_SCHEMES = ("http", "https")


class UnsafeUrlError(ValueError):
    """Raised when a URL uses a scheme outside the allow-list."""


def require_http_url(url: str) -> str:
    scheme = urlparse(url).scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"only http/https allowed, got {scheme or '(none)'}: {url!r}")
    return url


def urlopen_checked(target: str | urllib.request.Request, *, timeout: float) -> Any:
    """urlopen with the scheme allow-list enforced.

    urllib also honours file://, ftp:// and data:// URLs. Every endpoint in this
    project comes from a config file or an environment variable, so a wrong or
    hostile value turns an intended HTTP call into an arbitrary file read
    (CWE-939). Routing all outbound calls through here means the check cannot be
    forgotten at an individual call site.
    """
    url = target if isinstance(target, str) else target.full_url
    require_http_url(url)
    # nosemgrep: dynamic-urllib-use-detected -- scheme allow-listed on the line above
    return urllib.request.urlopen(target, timeout=timeout)
