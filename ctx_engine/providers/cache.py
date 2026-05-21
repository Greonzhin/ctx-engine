from __future__ import annotations

import hashlib
import json

from ..db import connect, init_db, now_iso, stable_json


def cache_key(parts: object) -> str:
    raw = stable_json(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def capsule_namespace(workspace_id: str) -> str:
    return f"capsule_cache:{workspace_id}"


class CacheProvider:
    def get(self, namespace: str, key: object) -> object | None:
        conn = init_db(connect())
        try:
            row = conn.execute(
                "SELECT value_json FROM caches WHERE namespace = ? AND key = ?",
                (namespace, cache_key(key)),
            ).fetchone()
            return json.loads(row["value_json"]) if row else None
        finally:
            conn.close()

    def set(self, namespace: str, key: object, value: object, expires_at: str | None = None) -> None:
        conn = init_db(connect())
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO caches(namespace, key, value_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (namespace, cache_key(key), stable_json(value), now_iso(), expires_at),
            )
            conn.commit()
        finally:
            conn.close()

    def clear_namespace(self, namespace: str) -> int:
        conn = init_db(connect())
        try:
            cursor = conn.execute("DELETE FROM caches WHERE namespace = ?", (namespace,))
            conn.commit()
            return int(cursor.rowcount)
        finally:
            conn.close()

    def clear_capsule_workspace(self, workspace_id: str) -> int:
        return self.clear_namespace(capsule_namespace(workspace_id))
