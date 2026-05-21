from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ..db import now_iso
from ..integrations.context7 import Context7Client
from ..integrations.rtk import estimate_tokens
from ..security.prompt_scanner import PromptScanner
from .cache import CacheProvider
from .egress import EgressProvider
from .safety import SafetyProvider, SafetyViolation

KNOWN_LIBRARIES = {
    "codex": "/openai/codex",
    "codex cli": "/openai/codex",
    "context7": "/upstash/context7",
    "docker": "/docker/docs",
    "gemini": "/google-gemini/gemini-cli",
    "gemini cli": "/google-gemini/gemini-cli",
    "claude": "/anthropics/claude-code",
    "claude code": "/anthropics/claude-code",
    "mcp": "/modelcontextprotocol/python-sdk",
    "mcp python sdk": "/modelcontextprotocol/python-sdk",
    "next": "/vercel/next.js",
    "next.js": "/vercel/next.js",
    "python": "/python/cpython",
    "py-tree-sitter": "/tree-sitter/py-tree-sitter",
    "react": "/facebook/react",
    "setuptools": "/pypa/setuptools",
    "sqlite": "/python/cpython",
    "sqlite3": "/python/cpython",
    "supabase": "/supabase/supabase",
    "fastapi": "/tiangolo/fastapi",
    "pydantic": "/pydantic/pydantic",
    "litellm": "/berriai/litellm",
    "pytest": "/pytest-dev/pytest",
    "tree-sitter": "/tree-sitter/tree-sitter",
    "tree-sitter-language-pack": "/kreuzberg-dev/tree-sitter-language-pack",
}


@dataclass(frozen=True)
class DocsResult:
    library_id: str
    query: str
    text: str
    source_url: str
    retrieved_at: str
    trust_tier: str = "public_docs"

    def as_context(self) -> dict[str, object]:
        return {
            "provider": "Context7DocsProvider",
            "library_id": self.library_id,
            "query": self.query,
            "text": self.text,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at,
            "trust_tier": self.trust_tier,
            "token_estimate": estimate_tokens(self.text),
        }


class Context7DocsProvider:
    def __init__(self, mode: str = "safe") -> None:
        self.mode = mode
        self.safety = SafetyProvider()
        self.cache = CacheProvider()
        self.client = Context7Client()
        self.scanner = PromptScanner()
        self.egress = EgressProvider()

    @staticmethod
    def _version_hint(query: str) -> str:
        match = re.search(r"\b(v?\d+\.\d+(?:\.\d+)?)\b", query, re.IGNORECASE)
        if match:
            return match.group(1)
        return "unknown"

    def resolve(self, query: str) -> dict[str, object]:
        decision = self.safety.guard_external_docs_query(query)
        cleaned = decision.text.lower().strip()
        if cleaned.startswith("/"):
            library_id = cleaned
        else:
            library_id = KNOWN_LIBRARIES.get(cleaned) or KNOWN_LIBRARIES.get(cleaned.replace(" ", ""))
        if not library_id:
            for key, value in KNOWN_LIBRARIES.items():
                if key in cleaned:
                    library_id = value
                    break
        return {
            "query": decision.text,
            "library_id": library_id,
            "status": "resolved" if library_id else "not_found",
            "redactions": decision.redactions,
            "public_docs_only": True,
            "version_hint": self._version_hint(decision.text),
        }

    def query(self, library_id: str, query: str) -> dict[str, object]:
        decision = self.safety.guard_external_docs_query(query)
        cache_key = {"library_id": library_id, "query": decision.text}
        cached = self.cache.get("docs_cache", cache_key)
        if cached:
            cached["cache"] = "hit"
            self.egress.record(
                provider="context7",
                query=decision.text,
                endpoint=self.client.endpoint,
                status="ok_cache_hit",
                latency_ms=0,
                response_bytes=len(str(cached.get("text", "")).encode("utf-8", errors="replace")),
                cache_hit=True,
                library_id=library_id,
            )
            return cached
        if self.mode == "offline":
            result = DocsResult(
                library_id=library_id,
                query=decision.text,
                text="Offline mode: no live Context7 request was made. Use cached public docs or switch to dev mode.",
                source_url=f"https://context7.com{library_id}",
                retrieved_at=now_iso(),
            )
            egress_status = "skipped_offline"
            latency_ms = 0
            response_bytes = 0
        elif os.environ.get("CTX_ENGINE_CONTEXT7_LIVE") == "1":
            try:
                live = self.client.query_library_docs(library_id, decision.text)
                result = DocsResult(
                    library_id=library_id,
                    query=decision.text,
                    text=str(live.get("text") or "Context7 returned no content."),
                    source_url=f"https://context7.com{library_id}",
                    retrieved_at=now_iso(),
                )
                egress_status = "ok_live"
                latency_ms = int(live.get("latency_ms") or 0)
                response_bytes = int(live.get("response_bytes") or 0)
            except Exception as exc:
                result = DocsResult(
                    library_id=library_id,
                    query=decision.text,
                    text=f"Context7 live request failed; using safe fallback. Reason: {type(exc).__name__}",
                    source_url=f"https://context7.com{library_id}",
                    retrieved_at=now_iso(),
                )
                egress_status = f"error_{type(exc).__name__}"
                latency_ms = 0
                response_bytes = 0
        else:
            result = DocsResult(
                library_id=library_id,
                query=decision.text,
                text="Context7 live fetch is disabled by default in P0. Set CTX_ENGINE_CONTEXT7_LIVE=1 in dev mode to fetch public docs.",
                source_url=f"https://context7.com{library_id}",
                retrieved_at=now_iso(),
            )
            egress_status = "skipped_live_disabled"
            latency_ms = 0
            response_bytes = 0
        value = result.as_context()
        scan = self.scanner.scan(value["text"])
        value["risk_level"] = scan.risk_level
        value["risk_flags"] = scan.risk_flags
        value["quarantined"] = scan.quarantined
        if scan.quarantined:
            value["text"] = (
                "Context7 result was quarantined by prompt scanner due to high-risk patterns. "
                "Review source_url manually."
            )
        value["cache"] = "miss"
        self.cache.set("docs_cache", cache_key, value)
        self.egress.record(
            provider="context7",
            query=decision.text,
            endpoint=self.client.endpoint,
            status=egress_status,
            latency_ms=latency_ms,
            response_bytes=response_bytes,
            cache_hit=False,
            library_id=library_id,
        )
        return value


__all__ = ["Context7DocsProvider", "SafetyViolation"]
