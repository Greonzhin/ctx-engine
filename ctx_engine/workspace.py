from __future__ import annotations

import hashlib
from pathlib import Path

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
            ON CONFLICT(id) DO UPDATE SET root_path = excluded.root_path
            """,
            (wid, str(root), display_name or root.name or "workspace", now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": wid, "root_path": str(root), "display_name": display_name or root.name}


def list_workspaces() -> list[dict[str, str | None]]:
    conn = init_db(connect())
    try:
        rows = conn.execute(
            "SELECT id, root_path, display_name, created_at, last_indexed_at "
            "FROM workspaces ORDER BY COALESCE(last_indexed_at, created_at) DESC"
        ).fetchall()
        return [dict(row) for row in rows]
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
            row = conn.execute(
                "SELECT * FROM workspaces ORDER BY COALESCE(last_indexed_at, created_at) DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


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
