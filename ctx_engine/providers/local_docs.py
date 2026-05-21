from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from ..db import connect, init_db, now_iso, stable_json
from ..graph.indexer import sha256_text
from ..providers.safety import SafetyProvider
from ..security.prompt_scanner import PromptScanner
from ..security.ignore import is_ignored, to_posix_rel
from ..security.redaction import redact_text
from .cache import CacheProvider

DOC_FILE_NAMES = {"README.md", "AGENTS.md", "CLAUDE.md", "GEMINI.md"}
DOC_DIRS = {"docs", "adr", "architecture", "runbooks"}
OPENAPI_RE = re.compile(r"^openapi.*\.(ya?ml|json)$", re.IGNORECASE)


def is_doc_path(rel_path: str) -> bool:
    rel = rel_path.replace("\\", "/")
    name = Path(rel).name
    top = rel.split("/", 1)[0]
    return name in DOC_FILE_NAMES or top in DOC_DIRS or bool(OPENAPI_RE.match(name))


def doc_id(workspace_id: str, rel_path: str) -> str:
    return hashlib.sha256(f"doc:{workspace_id}:{rel_path}".encode("utf-8")).hexdigest()[:24]


def title_for(text: str, rel_path: str) -> str:
    for line in text.splitlines()[:20]:
        if line.startswith("#"):
            return line.lstrip("#").strip() or rel_path
    return rel_path


class LocalDocsProvider:
    def __init__(self) -> None:
        self.safety = SafetyProvider()
        self.scanner = PromptScanner()

    def index(self, root: str | Path, workspace_id: str) -> dict[str, object]:
        root_path = Path(root).resolve()
        conn = init_db(connect())
        count = 0
        redactions = 0
        doc_fingerprints: list[dict[str, object]] = []
        try:
            conn.execute("DELETE FROM docs WHERE workspace_id = ?", (workspace_id,))
            conn.execute("DELETE FROM docs_fts WHERE workspace_id = ?", (workspace_id,))
            for dirpath, dirs, names in os.walk(root_path):
                current = Path(dirpath)
                dirs[:] = [
                    name
                    for name in dirs
                    if not is_ignored(to_posix_rel(current / name, root_path))
                    and not is_ignored(f"{to_posix_rel(current / name, root_path)}/")
                ]
                for name in names:
                    path = current / name
                    rel = to_posix_rel(path, root_path)
                    if not is_doc_path(rel) or is_ignored(rel):
                        continue
                    decision = self.safety.can_read_file(path, root_path)
                    if not decision.allowed:
                        continue
                    raw = path.read_text(encoding="utf-8", errors="replace")
                    sha256 = sha256_text(raw)
                    body, item_redactions = redact_text(raw)
                    redactions += item_redactions
                    scan = self.scanner.scan(body)
                    did = doc_id(workspace_id, rel)
                    title = title_for(body, rel)
                    doc_fingerprints.append(
                        {
                            "rel_path": rel,
                            "sha256": sha256,
                            "size": len(raw.encode("utf-8", errors="replace")),
                        }
                    )
                    conn.execute(
                        """
                        INSERT INTO docs(id, workspace_id, path, rel_path, title, body, sha256, indexed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            did,
                            workspace_id,
                            str(path),
                            rel,
                            title,
                            body,
                            sha256,
                            now_iso(),
                        ),
                    )
                    conn.execute(
                        """
                        UPDATE docs
                        SET risk_level = ?, risk_flags_json = ?, quarantined = ?, scanned_at = ?
                        WHERE id = ?
                        """,
                        (
                            scan.risk_level,
                            stable_json(scan.risk_flags),
                            1 if scan.quarantined else 0,
                            now_iso(),
                            did,
                        ),
                    )
                    conn.execute(
                        "INSERT INTO docs_fts(doc_id, workspace_id, title, body, path) VALUES (?, ?, ?, ?, ?)",
                        (did, workspace_id, title, body, rel),
                    )
                    count += 1
            docs_index_hash = sha256_text(
                stable_json(
                    {
                        "indexer": "ctx-engine-docs-v1",
                        "docs": sorted(doc_fingerprints, key=lambda item: str(item["rel_path"])),
                    }
                )
            )
            conn.execute(
                "UPDATE workspaces SET docs_index_hash = ? WHERE id = ?",
                (docs_index_hash, workspace_id),
            )
            conn.commit()
            CacheProvider().clear_capsule_workspace(workspace_id)
            return {
                "docs": count,
                "redactions": redactions,
                "docs_index_hash": docs_index_hash,
            }
        finally:
            conn.close()

    def query(
        self,
        query: str,
        workspace_id: str,
        limit: int = 5,
        include_quarantined: bool = False,
    ) -> list[dict[str, object]]:
        conn = init_db(connect())
        like = f"%{query}%"
        try:
            quarantine_filter = "" if include_quarantined else "AND quarantined = 0"
            rows = conn.execute(
                """
                SELECT id, rel_path, path, title, substr(body, 1, 1200) AS body, sha256,
                       risk_level, risk_flags_json, quarantined, scanned_at
                FROM docs
                WHERE workspace_id = ? AND (title LIKE ? OR body LIKE ? OR rel_path LIKE ?)
                  {quarantine_filter}
                ORDER BY length(body) ASC LIMIT ?
                """.replace("{quarantine_filter}", quarantine_filter),
                (workspace_id, like, like, like, limit),
            ).fetchall()
            items = [dict(row) for row in rows]
            for item in items:
                item["risk_flags"] = json.loads(item.get("risk_flags_json") or "[]")
            return items
        finally:
            conn.close()

    def risk_summary(self, workspace_id: str, limit: int = 2000) -> dict[str, object]:
        conn = init_db(connect())
        try:
            rows = conn.execute(
                """
                SELECT id, rel_path, body
                FROM docs
                WHERE workspace_id = ?
                LIMIT ?
                """,
                (workspace_id, limit),
            ).fetchall()
            updates: list[tuple[str, str, int, str, str]] = []
            counts = {"clean": 0, "low": 0, "medium": 0, "high": 0}
            flag_counts: dict[str, int] = {}
            high_docs: list[str] = []
            now = now_iso()
            for row in rows:
                scan = self.scanner.scan(str(row["body"]))
                counts[scan.risk_level] += 1
                for flag in scan.risk_flags:
                    flag_counts[flag] = int(flag_counts.get(flag, 0)) + 1
                if scan.risk_level == "high":
                    high_docs.append(str(row["rel_path"]))
                updates.append(
                    (
                        scan.risk_level,
                        stable_json(scan.risk_flags),
                        1 if scan.quarantined else 0,
                        now,
                        str(row["id"]),
                    )
                )
            conn.executemany(
                """
                UPDATE docs
                SET risk_level = ?, risk_flags_json = ?, quarantined = ?, scanned_at = ?
                WHERE id = ?
                """,
                updates,
            )
            conn.commit()
            ordered_flags = sorted(flag_counts.items(), key=lambda item: (-int(item[1]), str(item[0])))
            return {
                "status": "ok",
                "workspace_id": workspace_id,
                "scanned_docs": len(rows),
                "risk_counts": counts,
                "flag_counts": dict(ordered_flags),
                "top_flags": [name for name, _count in ordered_flags[:5]],
                "high_risk_docs": high_docs[:20],
            }
        finally:
            conn.close()
