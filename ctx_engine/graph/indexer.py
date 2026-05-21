from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from ..db import connect, init_db, now_iso, reset_workspace_index, stable_json
from ..providers.cache import CacheProvider
from ..providers.safety import SafetyProvider
from ..security.ignore import is_ignored, to_posix_rel
from ..security.redaction import redact_text
from ..workspace import register_workspace
from .parsers import JavaScriptParser, PythonParser, TypeScriptParser
from .skeletons import build_skeleton

CODE_SUFFIXES = {
    ".py": PythonParser(),
    ".js": JavaScriptParser(),
    ".jsx": JavaScriptParser(),
    ".mjs": JavaScriptParser(),
    ".cjs": JavaScriptParser(),
    ".ts": TypeScriptParser(),
    ".tsx": TypeScriptParser(),
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def file_id(workspace_id: str, rel_path: str) -> str:
    return hashlib.sha256(f"{workspace_id}:{rel_path}".encode("utf-8")).hexdigest()[:24]


def symbol_id(workspace_id: str, rel_path: str, name: str, line: int) -> str:
    raw = f"{workspace_id}:{rel_path}:{name}:{line}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirs, names in os.walk(root):
        current = Path(dirpath)
        dirs[:] = [
            name
            for name in dirs
            if not is_ignored(to_posix_rel(current / name, root))
            and not is_ignored(f"{to_posix_rel(current / name, root)}/")
        ]
        for name in names:
            path = current / name
            rel = to_posix_rel(path, root)
            if path.suffix.lower() in CODE_SUFFIXES and not is_ignored(rel):
                files.append(path)
    return sorted(files)


class RepositoryIndexer:
    def __init__(self) -> None:
        self.safety = SafetyProvider()

    def index(self, root: str | Path) -> dict[str, object]:
        workspace = register_workspace(root)
        workspace_id = workspace["id"]
        root_path = Path(workspace["root_path"])
        conn = init_db(connect())
        indexed_files = 0
        indexed_symbols = 0
        parser_backends: set[str] = set()
        file_fingerprints: list[dict[str, object]] = []
        try:
            reset_workspace_index(conn, workspace_id)
            for path in iter_source_files(root_path):
                decision = self.safety.can_read_file(path, root_path)
                if not decision.allowed:
                    continue
                raw = path.read_text(encoding="utf-8", errors="replace")
                rel = to_posix_rel(path, root_path)
                parser = CODE_SUFFIXES[path.suffix.lower()]
                parsed = parser.parse(raw, str(path))
                parser_backends.add(parsed.parser_backend)
                sha256 = sha256_text(raw)
                size = len(raw.encode("utf-8", errors="replace"))
                file_fingerprints.append(
                    {
                        "rel_path": rel,
                        "sha256": sha256,
                        "size": size,
                        "language": parsed.language,
                        "parser_backend": parsed.parser_backend,
                    }
                )
                skeleton, redactions = redact_text(
                    build_skeleton(raw, parsed.symbols, parsed.imports)
                )
                fid = file_id(workspace_id, rel)
                conn.execute(
                    """
                    INSERT INTO files(id, workspace_id, path, rel_path, language, sha256, size, skeleton, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fid,
                        workspace_id,
                        str(path),
                        rel,
                        parsed.language,
                        sha256,
                        size,
                        skeleton,
                        now_iso(),
                    ),
                )
                indexed_files += 1
                for symbol in parsed.symbols:
                    sid = symbol_id(workspace_id, rel, symbol.name, symbol.start_line)
                    conn.execute(
                        """
                        INSERT INTO symbols(
                          id, workspace_id, file_id, name, kind, signature, start_line, end_line,
                          container, imports_json, exports_json, route_like, test_name
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sid,
                            workspace_id,
                            fid,
                            symbol.name,
                            symbol.kind,
                            symbol.signature,
                            symbol.start_line,
                            symbol.end_line,
                            symbol.container,
                            json.dumps(symbol.imports, ensure_ascii=False),
                            json.dumps(symbol.exports, ensure_ascii=False),
                            1 if symbol.route_like else 0,
                            1 if symbol.test_name else 0,
                        ),
                    )
                    conn.execute(
                        "INSERT INTO symbols_fts(symbol_id, workspace_id, name, kind, signature, path) VALUES (?, ?, ?, ?, ?, ?)",
                        (sid, workspace_id, symbol.name, symbol.kind, symbol.signature, rel),
                    )
                    indexed_symbols += 1
            code_index_hash = sha256_text(
                stable_json(
                    {
                        "indexer": "ctx-engine-code-v1",
                        "files": sorted(file_fingerprints, key=lambda item: str(item["rel_path"])),
                    }
                )
            )
            conn.execute(
                "UPDATE workspaces SET last_indexed_at = ?, code_index_hash = ? WHERE id = ?",
                (now_iso(), code_index_hash, workspace_id),
            )
            conn.commit()
            CacheProvider().clear_capsule_workspace(workspace_id)
            return {
                "workspace_id": workspace_id,
                "root_path": str(root_path),
                "files": indexed_files,
                "symbols": indexed_symbols,
                "parser_backends": sorted(parser_backends),
                "code_index_hash": code_index_hash,
            }
        finally:
            conn.close()
