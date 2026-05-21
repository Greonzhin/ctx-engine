from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .client_adapters import ClaudeAdapter, CodexAdapter, GeminiAdapter, GenericAdapter
from .config import load_endpoint_from_rules, rules_path


def check_rules_drift(path: str | Path = ".") -> dict[str, Any]:
    root = Path(path).resolve()
    rules = rules_path(root)
    if not rules.exists():
        return {"status": "error", "workspace_path": str(root), "errors": ["missing .ctx-engine/rules.yaml"], "files": []}

    endpoint = load_endpoint_from_rules(root)
    adapters = [CodexAdapter(), ClaudeAdapter(), GeminiAdapter(), GenericAdapter()]
    files: list[dict[str, Any]] = []
    errors: list[str] = []

    with tempfile.TemporaryDirectory(prefix="ctx-rules-check-") as tmp:
        expected_root = Path(tmp)
        for adapter in adapters:
            adapter.write_files(expected_root, endpoint)

        expected_paths: set[str] = set()
        for adapter in adapters:
            for expected in adapter.expected_files(expected_root):
                rel = expected.relative_to(expected_root).as_posix()
                expected_paths.add(rel)
                actual = root / rel
                expected_text = expected.read_text(encoding="utf-8")
                if not actual.exists():
                    files.append({"path": rel, "status": "missing", "client_id": adapter.client_id})
                    errors.append(f"{rel}: missing generated file")
                    continue
                actual_text = actual.read_text(encoding="utf-8", errors="replace")
                status = "ok" if actual_text == expected_text else "drift"
                files.append({"path": rel, "status": status, "client_id": adapter.client_id})
                if status == "drift":
                    errors.append(f"{rel}: generated file drift")

    overall = "ok" if not errors else "drift"
    return {
        "status": overall,
        "workspace_path": str(root),
        "rules_path": str(rules),
        "endpoint": endpoint,
        "checked_files": sorted(expected_paths),
        "files": sorted(files, key=lambda item: str(item["path"])),
        "errors": sorted(errors),
    }
