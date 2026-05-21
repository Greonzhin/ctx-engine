from __future__ import annotations

import json
from pathlib import Path

from .base import ClientAdapter


class GenericAdapter(ClientAdapter):
    client_id = "generic"

    def expected_files(self, root: Path) -> list[Path]:
        return [root / ".ctx-engine" / "mcp.json"]

    def read_configured_endpoint(self, root: Path) -> str | None:
        config = root / ".ctx-engine" / "mcp.json"
        if not config.exists():
            return None
        data = json.loads(config.read_text(encoding="utf-8"))
        server = data.get("mcpServers", {}).get("ctx-engine", {})
        endpoint = server.get("url")
        return str(endpoint) if endpoint else None

    def write_files(self, root: Path, endpoint: str) -> list[Path]:
        out = root / ".ctx-engine" / "mcp.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "ctx-engine": {
                            "type": "http",
                            "url": endpoint,
                        }
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return [out]
