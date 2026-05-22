from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .decisions import decision_report
from .providers.action_ledger import ActionLedger
from .providers.memory import BuiltInMemoryProvider
from .workspace import get_workspace, get_workspace_for_path, workspace_fingerprint
from .db import now_iso


CONTEXT_EXPORT_VERSION = 1


def _resolve_workspace(path: str | Path = ".", workspace_id: str | None = None) -> dict[str, Any] | None:
    if workspace_id:
        return get_workspace(workspace_id)
    return get_workspace_for_path(path) or get_workspace()


def export_context(
    path: str | Path = ".",
    workspace_id: str | None = None,
    include_memories: bool = True,
    include_ledger: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    root = Path(path).resolve()
    workspace = _resolve_workspace(root, workspace_id)
    if not workspace:
        return {
            "status": "empty",
            "version": CONTEXT_EXPORT_VERSION,
            "exported_at": now_iso(),
            "workspace": None,
            "memories": [],
            "decisions": [],
            "ledger": [],
            "warnings": ["No workspace is registered. Run `ctx index <path>` first."],
        }

    wid = str(workspace["id"])
    workspace_root = Path(str(workspace["root_path"]))
    memory_provider = BuiltInMemoryProvider()
    memory_report = memory_provider.report(workspace_id=wid, limit=limit) if include_memories else {"recent": []}
    decisions = decision_report(workspace_root, limit=limit)
    ledger = ActionLedger().tail(limit=limit) if include_ledger else []

    return {
        "status": "ok",
        "version": CONTEXT_EXPORT_VERSION,
        "exported_at": now_iso(),
        "workspace": {
            "id": wid,
            "root_path": str(workspace_root),
            "display_name": workspace.get("display_name"),
            "fingerprint": workspace_fingerprint(wid),
        },
        "memory_summary": memory_report.get("summary", {}),
        "memories": memory_report.get("recent", []),
        "decision_summary": decisions.get("summary", {}),
        "decisions": decisions.get("decisions", []),
        "ledger": ledger,
        "warnings": [],
    }


def write_context_export(payload: dict[str, Any], output: str | Path) -> dict[str, Any]:
    path = Path(output).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    path.write_text(text + "\n", encoding="utf-8")
    return {"status": "ok", "path": str(path), "bytes": len(text.encode("utf-8"))}


def load_context_export(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("context export must be a JSON object")
    if int(payload.get("version") or 0) != CONTEXT_EXPORT_VERSION:
        raise ValueError(f"unsupported context export version: {payload.get('version')}")
    return payload


def import_context(
    input_path: str | Path,
    workspace_id: str | None = None,
    apply: bool = False,
    agent_namespace: str = "imported",
    limit: int = 100,
) -> dict[str, Any]:
    payload = load_context_export(input_path)
    target_workspace = get_workspace(workspace_id)
    target_workspace_id = str(target_workspace["id"]) if target_workspace else str((payload.get("workspace") or {}).get("id") or "global")
    memories = [item for item in payload.get("memories", []) if isinstance(item, dict)][:limit]
    warnings: list[str] = []
    imported: list[dict[str, Any]] = []

    for item in memories:
        claim = str(item.get("claim") or "").strip()
        if not claim:
            warnings.append(f"skipped memory without claim: {item.get('id')}")
            continue
        preview = {
            "source_id": item.get("id"),
            "claim": claim,
            "workspace_id": target_workspace_id,
            "agent_namespace": agent_namespace,
            "lifecycle_tier": item.get("lifecycle_tier") or "warm",
            "linked_files": item.get("linked_files") or [],
            "linked_symbols": item.get("linked_symbols") or [],
            "linked_docs": item.get("linked_docs") or [],
        }
        if apply:
            written = BuiltInMemoryProvider().retain(
                claim,
                workspace_id=target_workspace_id,
                source=f"import:{item.get('source') or 'context-export'}",
                files=list(preview["linked_files"]),
                symbols=list(preview["linked_symbols"]),
                docs=list(preview["linked_docs"]),
                lifecycle_tier=str(preview["lifecycle_tier"]),
                agent_namespace=agent_namespace,
            )
            preview["imported_id"] = written.get("id")
        imported.append(preview)

    return {
        "status": "ok",
        "mode": "apply" if apply else "dry-run",
        "input": str(Path(input_path).resolve()),
        "source_workspace": payload.get("workspace"),
        "target_workspace_id": target_workspace_id,
        "memories_seen": len(memories),
        "memories_imported": len(imported) if apply else 0,
        "imports": imported,
        "warnings": warnings,
    }
