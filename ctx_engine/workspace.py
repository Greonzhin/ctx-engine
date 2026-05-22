from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .db import connect, init_db, now_iso, stable_json


def normalize_workspace_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def workspace_id_for(path: str | Path) -> str:
    normalized = str(normalize_workspace_path(path))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def register_workspace(path: str | Path, display_name: str | None = None) -> dict[str, str]:
    root = normalize_workspace_path(path)
    wid = workspace_id_for(root)
    conn = init_db(connect())
    try:
        conn.execute(
            """
            INSERT INTO workspaces(id, root_path, display_name, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              root_path = excluded.root_path,
              display_name = excluded.display_name
            """,
            (wid, str(root), display_name or root.name or "workspace", now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": wid, "root_path": str(root), "display_name": display_name or root.name}


def _row_to_workspace(row: Any) -> dict[str, str | None]:
    return dict(row)


def _active_workspace_id(conn) -> str | None:
    row = conn.execute("SELECT value FROM workspace_settings WHERE key = 'active_workspace_id'").fetchone()
    return str(row["value"]) if row else None


def _fallback_workspace_id(conn) -> str | None:
    row = conn.execute(
        "SELECT id FROM workspaces ORDER BY COALESCE(last_indexed_at, created_at) DESC LIMIT 1"
    ).fetchone()
    return str(row["id"]) if row else None


def _effective_active_workspace_id(conn) -> str | None:
    active = _active_workspace_id(conn)
    if active:
        exists = conn.execute("SELECT 1 FROM workspaces WHERE id = ?", (active,)).fetchone()
        if exists:
            return active
        conn.execute("DELETE FROM workspace_settings WHERE key = 'active_workspace_id'")
        conn.commit()
    return _fallback_workspace_id(conn)


def active_workspace_id() -> str | None:
    conn = init_db(connect())
    try:
        return _effective_active_workspace_id(conn)
    finally:
        conn.close()


def set_active_workspace(workspace_id_or_path: str | Path) -> dict[str, str | None]:
    workspace = resolve_workspace(workspace_id_or_path)
    if not workspace:
        raise ValueError(f"workspace not found: {workspace_id_or_path}")
    conn = init_db(connect())
    try:
        conn.execute(
            """
            INSERT INTO workspace_settings(key, value, updated_at)
            VALUES ('active_workspace_id', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (str(workspace["id"]), now_iso()),
        )
        conn.commit()
        workspace["active"] = True
        return workspace
    finally:
        conn.close()


def clear_active_workspace() -> None:
    conn = init_db(connect())
    try:
        conn.execute("DELETE FROM workspace_settings WHERE key = 'active_workspace_id'")
        conn.commit()
    finally:
        conn.close()


def list_workspaces() -> list[dict[str, str | None]]:
    conn = init_db(connect())
    try:
        active = _effective_active_workspace_id(conn)
        rows = conn.execute(
            "SELECT id, root_path, display_name, created_at, last_indexed_at "
            "FROM workspaces ORDER BY COALESCE(last_indexed_at, created_at) DESC"
        ).fetchall()
        items = [_row_to_workspace(row) for row in rows]
        for item in items:
            item["active"] = str(item["id"]) == active
        return items
    finally:
        conn.close()


def get_workspace(workspace_id: str | None = None) -> dict[str, str | None] | None:
    conn = init_db(connect())
    try:
        if workspace_id:
            row = conn.execute(
                "SELECT * FROM workspaces WHERE id = ?", (workspace_id,)
            ).fetchone()
        else:
            active = _effective_active_workspace_id(conn)
            row = None
            if active:
                row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (active,)).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM workspaces ORDER BY COALESCE(last_indexed_at, created_at) DESC LIMIT 1"
                ).fetchone()
        item = _row_to_workspace(row) if row else None
        if item:
            item["active"] = str(item["id"]) == _effective_active_workspace_id(conn)
        return item
    finally:
        conn.close()


def resolve_workspace(workspace_id_or_path: str | Path) -> dict[str, str | None] | None:
    value = str(workspace_id_or_path)
    conn = init_db(connect())
    try:
        row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (value,)).fetchone()
        if row:
            return _row_to_workspace(row)
    finally:
        conn.close()
    return get_workspace_for_path(value)


def workspace_inventory() -> dict[str, object]:
    items: list[dict[str, object]] = []
    for workspace in list_workspaces():
        root_value = workspace.get("root_path")
        exists = Path(str(root_value)).exists() if root_value else False
        fingerprint = workspace_fingerprint(str(workspace["id"]))
        items.append(
            {
                **workspace,
                "exists": exists,
                "indexed": bool(fingerprint.get("code_index_hash") or fingerprint.get("docs_index_hash")),
                "fingerprint": fingerprint,
            }
        )
    missing = [item for item in items if not item["exists"]]
    unindexed = [item for item in items if not item["indexed"]]
    return {
        "status": "attention" if missing else "ok",
        "active_workspace": get_workspace(),
        "workspace_count": len(items),
        "missing_count": len(missing),
        "unindexed_count": len(unindexed),
        "workspaces": items,
    }


def get_workspace_for_path(path: str | Path | None) -> dict[str, str | None] | None:
    if path is None:
        return None
    probe = normalize_workspace_path(path)
    candidates = list_workspaces()
    exact: dict[str, str | None] | None = None
    contained: list[tuple[int, dict[str, str | None]]] = []
    for item in candidates:
        root_value = item.get("root_path")
        if not root_value:
            continue
        root = normalize_workspace_path(str(root_value))
        if probe == root:
            exact = get_workspace(str(item["id"]))
            break
        if root in probe.parents:
            contained.append((len(root.parts), item))
    if exact:
        return exact
    if contained:
        contained.sort(key=lambda pair: pair[0], reverse=True)
        return get_workspace(str(contained[0][1]["id"]))
    return None


def workspace_fingerprint(workspace_id: str) -> dict[str, str | None]:
    conn = init_db(connect())
    try:
        row = conn.execute(
            """
            SELECT code_index_hash, docs_index_hash, last_indexed_at
            FROM workspaces
            WHERE id = ?
            """,
            (workspace_id,),
        ).fetchone()
        if not row:
            return {
                "code_index_hash": None,
                "docs_index_hash": None,
                "combined_index_hash": None,
                "last_indexed_at": None,
            }
        payload = {
            "code": row["code_index_hash"],
            "docs": row["docs_index_hash"],
        }
        combined = hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()
        return {
            "code_index_hash": row["code_index_hash"],
            "docs_index_hash": row["docs_index_hash"],
            "combined_index_hash": combined,
            "last_indexed_at": row["last_indexed_at"],
        }
    finally:
        conn.close()
