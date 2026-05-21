from __future__ import annotations

from typing import Any

from .providers.cache import CacheProvider, capsule_namespace
from .workspace import get_workspace, list_workspaces, workspace_fingerprint


def verify_capsule_cache(workspace_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    workspaces = [get_workspace(workspace_id)] if workspace_id else list_workspaces()
    workspaces = [workspace for workspace in workspaces if workspace]
    cache = CacheProvider()
    entries: list[dict[str, Any]] = []
    valid = stale = invalid = 0

    for workspace in workspaces:
        wid = str(workspace["id"])
        current = workspace_fingerprint(wid)
        rows = cache.list_namespace(capsule_namespace(wid), limit=limit)
        for row in rows:
            value = row.get("value") if isinstance(row.get("value"), dict) else {}
            entry_fingerprint = value.get("index_fingerprint") if isinstance(value.get("index_fingerprint"), dict) else {}
            entry_hash = entry_fingerprint.get("combined_index_hash")
            current_hash = current.get("combined_index_hash")
            status = "valid"
            evidence: list[str] = []
            if not entry_hash:
                status = "invalid"
                evidence.append("cached capsule is missing index_fingerprint.combined_index_hash")
                invalid += 1
            elif entry_hash != current_hash:
                status = "stale"
                evidence.append("cached capsule fingerprint does not match current workspace fingerprint")
                stale += 1
            else:
                evidence.append("cached capsule fingerprint matches current workspace fingerprint")
                valid += 1

            provenance = value.get("provenance") if isinstance(value.get("provenance"), dict) else {}
            entries.append(
                {
                    "status": status,
                    "workspace_id": wid,
                    "workspace_path": workspace.get("root_path"),
                    "namespace": row.get("namespace"),
                    "cache_key": row.get("key"),
                    "created_at": row.get("created_at"),
                    "expires_at": row.get("expires_at"),
                    "capsule_id": provenance.get("capsule_id"),
                    "task_brief": value.get("task_brief"),
                    "cache_index_hash": entry_hash,
                    "current_index_hash": current_hash,
                    "evidence": evidence,
                }
            )

    status = "ok"
    if invalid:
        status = "invalid"
    elif stale:
        status = "stale"

    return {
        "status": status,
        "filters": {"workspace_id": workspace_id, "limit": limit},
        "summary": {
            "workspace_count": len(workspaces),
            "entry_count": len(entries),
            "valid": valid,
            "stale": stale,
            "invalid": invalid,
        },
        "entries": entries,
    }
