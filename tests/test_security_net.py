"""Scheme allow-list for outbound urllib calls.

The point of the guard is not that a bad URL raises — it is that it raises
*before* urllib is handed the value. `file:///etc/passwd` reaching urlopen is
already the vulnerability (CWE-939), so the network-touch test below asserts the
call never happens rather than just checking the exception type.
"""

from __future__ import annotations

import pytest

from ctx_engine.security.net import UnsafeUrlError, require_http_url, urlopen_checked


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/health",
        "https://example.test/mcp",
        "HTTP://UPPER.test/x",
    ],
)
def test_http_schemes_pass_through(url: str) -> None:
    assert require_http_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "file://C:/Windows/win.ini",
        "ftp://host/file",
        "data:text/plain,hello",
        "/etc/passwd",
        "",
    ],
)
def test_non_http_schemes_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        require_http_url(url)


def test_guard_runs_before_urllib_is_touched(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    def spy(*args: object, **kwargs: object) -> object:
        calls.append(args)
        raise AssertionError("urlopen must not be reached for a rejected scheme")

    monkeypatch.setattr("urllib.request.urlopen", spy)

    with pytest.raises(UnsafeUrlError):
        urlopen_checked("file:///etc/passwd", timeout=1.0)

    assert calls == []


def test_request_objects_are_checked_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three of the four call sites pass a Request, not a string."""
    import urllib.request

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: pytest.fail("urlopen must not be reached"),
    )

    with pytest.raises(UnsafeUrlError):
        urlopen_checked(urllib.request.Request("file:///etc/passwd"), timeout=1.0)
