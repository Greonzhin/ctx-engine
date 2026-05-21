from __future__ import annotations

import json
import time
import urllib.request
from typing import Any
from urllib.parse import urlparse

CONTEXT7_MCP_URL = "https://mcp.context7.com/mcp"


class Context7Client:
    """Small optional Context7 MCP client.

    Live access is opt-in via CTX_ENGINE_CONTEXT7_LIVE=1. The provider catches
    failures and falls back to safe cached text, so P0 stays reliable offline.
    """

    def __init__(self, endpoint: str = CONTEXT7_MCP_URL, timeout: float = 8.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def get_library_docs(self, library_id: str, query: str) -> str:
        return self.query_library_docs(library_id, query)["text"]

    def query_library_docs(self, library_id: str, query: str) -> dict[str, object]:
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "query-docs",
                "arguments": {
                    "libraryId": library_id,
                    "query": query,
                },
            },
        }
        started = time.perf_counter()
        response, response_bytes = self._post(payload)
        latency_ms = int((time.perf_counter() - started) * 1000)
        result = response.get("result", {})
        content = result.get("content") or []
        chunks = [item.get("text", "") for item in content if isinstance(item, dict)]
        text = "\n".join(chunk for chunk in chunks if chunk)
        return {
            "text": text,
            "response_bytes": response_bytes,
            "latency_ms": latency_ms,
            "endpoint_host": urlparse(self.endpoint).hostname,
            "status": "ok",
        }

    def _post(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-06-18",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
        return parse_mcp_response(raw), len(raw.encode("utf-8", errors="replace"))


def parse_mcp_response(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("event:") or raw.startswith("data:"):
        for line in raw.splitlines():
            if line.startswith("data:"):
                return json.loads(line.split("data:", 1)[1].strip())
    return json.loads(raw)
