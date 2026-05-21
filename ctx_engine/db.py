from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import data_dir, db_path, package_root


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    own = conn is None
    conn = conn or connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version TEXT PRIMARY KEY,
          applied_at TEXT NOT NULL
        )
        """
    )
    migrations_dir = package_root() / "migrations"
    for migration in sorted(migrations_dir.glob("*.sql")):
        version = migration.stem
        exists = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
        ).fetchone()
        if exists:
            continue
        conn.executescript(migration.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, now_iso()),
        )
        conn.commit()
    if own:
        return conn
    return conn


def reset_workspace_index(conn: sqlite3.Connection, workspace_id: str) -> None:
    for table in ("symbols_fts", "docs_fts"):
        conn.execute(f"DELETE FROM {table} WHERE workspace_id = ?", (workspace_id,))
    conn.execute(
        "DELETE FROM symbols WHERE workspace_id = ?",
        (workspace_id,),
    )
    conn.execute("DELETE FROM files WHERE workspace_id = ?", (workspace_id,))
    conn.execute("DELETE FROM docs WHERE workspace_id = ?", (workspace_id,))
    conn.commit()


def sqlite_status() -> dict[str, object]:
    data_dir().mkdir(parents=True, exist_ok=True)
    conn = init_db()
    try:
        fts_ok = True
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(body)")
            conn.execute("DROP TABLE IF EXISTS _fts_probe")
        except sqlite3.DatabaseError:
            fts_ok = False
        return {
            "db_path": str(db_path()),
            "sqlite_version": sqlite3.sqlite_version,
            "fts5": fts_ok,
        }
    finally:
        conn.close()
