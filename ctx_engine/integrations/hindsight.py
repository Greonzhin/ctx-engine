from __future__ import annotations

import os
import json
from urllib import error, request
from ..security.net import urlopen_checked


class ExternalHindsightUnavailable(RuntimeError):
    pass


class HindsightAdapter:
    """First-class optional external Hindsight adapter.

    The adapter is selected with CTX_ENGINE_MEMORY_PROVIDER=hindsight.
    If unavailable, callers should use deterministic sqlite fallback.
    """

    def __init__(self) -> None:
        self.endpoint = (os.environ.get("CTX_ENGINE_HINDSIGHT_ENDPOINT") or "").strip()
        self.selected = (os.environ.get("CTX_ENGINE_MEMORY_PROVIDER", "sqlite") or "sqlite").strip().lower() == "hindsight"
        self.timeout_seconds = max(0.5, float(os.environ.get("CTX_ENGINE_HINDSIGHT_TIMEOUT_SECONDS", "3")))

    def status(self) -> tuple[bool, str | None]:
        if not self.selected:
            return False, "External Hindsight adapter is not selected."
        if not self.endpoint:
            return False, "External Hindsight adapter selected but CTX_ENGINE_HINDSIGHT_ENDPOINT is not set."
        return True, None

    def _url(self, path_env: str, default_path: str) -> str:
        base = self.endpoint.rstrip("/")
        path = (os.environ.get(path_env) or default_path).strip()
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"

    def _post_json(self, path_env: str, default_path: str, payload: dict[str, object]) -> object:
        url = self._url(path_env, default_path)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen_checked(req, timeout=self.timeout_seconds) as resp:
                code = int(getattr(resp, "status", 200))
                raw = resp.read().decode("utf-8", errors="replace")
        except (error.URLError, TimeoutError, OSError) as exc:
            raise ExternalHindsightUnavailable(f"External Hindsight request failed: {exc}") from exc
        if code < 200 or code >= 300:
            raise ExternalHindsightUnavailable(f"External Hindsight returned HTTP {code}.")
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except Exception as exc:
            raise ExternalHindsightUnavailable("External Hindsight returned invalid JSON.") from exc

    def retain(
        self,
        claim: str,
        workspace_id: str | None = None,
        scope: str = "project",
        source: str = "user",
        files: list[str] | None = None,
        symbols: list[str] | None = None,
        docs: list[str] | None = None,
        confidence: float = 0.6,
        lifecycle_tier: str | None = None,
        agent_namespace: str = "default",
    ) -> dict[str, object]:
        payload = {
            "claim": claim,
            "workspace_id": workspace_id,
            "scope": scope,
            "source": source,
            "files": files or [],
            "symbols": symbols or [],
            "docs": docs or [],
            "confidence": confidence,
            "lifecycle_tier": lifecycle_tier,
            "agent_namespace": agent_namespace,
        }
        data = self._post_json("CTX_ENGINE_HINDSIGHT_RETAIN_PATH", "/retain", payload)
        if not isinstance(data, dict):
            raise ExternalHindsightUnavailable("External Hindsight retain response must be an object.")
        data.setdefault("provider_used", "hindsight")
        return data

    def recall(
        self,
        query: str = "",
        workspace_id: str | None = None,
        scope: str = "project",
        limit: int = 10,
        agent_namespace: str = "default",
    ) -> list[dict[str, object]]:
        payload = {
            "query": query,
            "workspace_id": workspace_id,
            "scope": scope,
            "limit": limit,
            "agent_namespace": agent_namespace,
        }
        data = self._post_json("CTX_ENGINE_HINDSIGHT_RECALL_PATH", "/recall", payload)
        if not isinstance(data, dict):
            raise ExternalHindsightUnavailable("External Hindsight recall response must be an object with memories.")
        raw = data.get("memories")
        if not isinstance(raw, list):
            raise ExternalHindsightUnavailable("External Hindsight recall response must include memories array.")
        rows = [item for item in raw if isinstance(item, dict)]
        for row in rows:
            row.setdefault("provider_used", "hindsight")
        return rows

    def apply_lifecycle_policy(
        self,
        workspace_id: str | None = None,
        agent_namespace: str = "default",
        hot_days: int | None = None,
        warm_days: int | None = None,
    ) -> dict[str, object]:
        payload = {
            "workspace_id": workspace_id,
            "agent_namespace": agent_namespace,
            "hot_days": hot_days,
            "warm_days": warm_days,
        }
        data = self._post_json("CTX_ENGINE_HINDSIGHT_POLICY_PATH", "/apply_lifecycle_policy", payload)
        if not isinstance(data, dict):
            raise ExternalHindsightUnavailable("External Hindsight lifecycle response must be an object.")
        data.setdefault("provider_used", "hindsight")
        return data
