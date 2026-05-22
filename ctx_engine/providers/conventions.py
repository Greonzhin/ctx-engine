from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ..db import connect, init_db
from ..workspace import get_workspace, get_workspace_for_path


def _top(counter: Counter[str], limit: int) -> list[dict[str, object]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _file_root(rel_path: str) -> str:
    parts = Path(rel_path).parts
    return parts[0] if len(parts) > 1 else "."


def _looks_like_test_path(rel_path: str) -> bool:
    lowered = rel_path.lower().replace("\\", "/")
    return "/tests/" in f"/{lowered}" or lowered.startswith("tests/") or lowered.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", "_test.py"))


def _normalize_import(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    match = re.search(r"^\s*from\s+([A-Za-z0-9_.]+)\s+import\b", text)
    if match:
        return match.group(1).split(".")[0]
    match = re.search(r"^\s*import\s+([A-Za-z0-9_.]+)", text)
    if match and not text.startswith("import {"):
        return match.group(1).split(".")[0]
    match = re.search(r"\bfrom\s+['\"]([^'\"]+)['\"]", text)
    if match:
        value = match.group(1)
        return "relative" if value.startswith(".") else value.split("/")[0] or value
    match = re.search(r"\brequire\(['\"]([^'\"]+)['\"]\)", text)
    if match:
        value = match.group(1)
        return "relative" if value.startswith(".") else value.split("/")[0] or value
    return None


class ConventionProvider:
    def _resolve_workspace(self, workspace_id: str | None = None, path: str | Path | None = None) -> dict[str, Any] | None:
        if workspace_id:
            return get_workspace(workspace_id)
        if path:
            return get_workspace_for_path(path) or get_workspace()
        return get_workspace_for_path(Path.cwd()) or get_workspace()

    def summarize(
        self,
        workspace_id: str | None = None,
        path: str | Path | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        workspace = self._resolve_workspace(workspace_id, path)
        if not workspace:
            return {"status": "empty", "workspace_id": None, "summary": {}, "warnings": ["No workspace is registered. Run `ctx index <path>` first."]}

        wid = str(workspace["id"])
        root = Path(str(workspace["root_path"]))
        conn = init_db(connect())
        try:
            file_rows = conn.execute(
                """
                SELECT rel_path, language
                FROM files
                WHERE workspace_id = ?
                ORDER BY rel_path
                """,
                (wid,),
            ).fetchall()
            symbol_rows = conn.execute(
                """
                SELECT s.name, s.kind, s.signature, s.route_like, s.test_name,
                       s.imports_json, s.exports_json, f.rel_path, f.language
                FROM symbols s
                JOIN files f ON f.id = s.file_id
                WHERE s.workspace_id = ?
                ORDER BY f.rel_path, s.start_line
                """,
                (wid,),
            ).fetchall()
        finally:
            conn.close()

        languages: Counter[str] = Counter()
        source_roots: Counter[str] = Counter()
        test_roots: Counter[str] = Counter()
        suffixes: Counter[str] = Counter()
        for row in file_rows:
            rel_path = str(row["rel_path"])
            language = str(row["language"])
            languages[language] += 1
            suffixes[Path(rel_path).suffix.lower() or "none"] += 1
            if _looks_like_test_path(rel_path):
                test_roots[_file_root(rel_path)] += 1
            else:
                source_roots[_file_root(rel_path)] += 1

        imports: Counter[str] = Counter()
        route_symbols: list[dict[str, object]] = []
        test_symbols: list[dict[str, object]] = []
        for row in symbol_rows:
            rel_path = str(row["rel_path"])
            if bool(row["route_like"]):
                route_symbols.append({"name": row["name"], "kind": row["kind"], "path": rel_path, "signature": row["signature"]})
            if bool(row["test_name"]) or _looks_like_test_path(rel_path):
                test_symbols.append({"name": row["name"], "kind": row["kind"], "path": rel_path, "signature": row["signature"]})
            for item in json.loads(str(row["imports_json"] or "[]")):
                normalized = _normalize_import(str(item))
                if normalized:
                    imports[normalized] += 1

        build_tools: list[str] = []
        if (root / "pyproject.toml").exists():
            build_tools.append("pyproject")
        if (root / "pytest.ini").exists() or test_roots or any(str(item.get("name", "")).startswith("test_") for item in test_symbols):
            build_tools.append("pytest")
        if (root / "package.json").exists():
            build_tools.append("package.json")

        route_paths = Counter(str(item["path"]) for item in route_symbols)
        test_paths = Counter(str(item["path"]) for item in test_symbols)
        warnings: list[str] = []
        if not file_rows:
            warnings.append("workspace has no indexed source files")
        if not test_symbols and not test_roots:
            warnings.append("no test conventions detected")

        return {
            "status": "ok",
            "workspace_id": wid,
            "workspace_path": str(root),
            "summary": {
                "file_count": len(file_rows),
                "symbol_count": len(symbol_rows),
                "build_tools": build_tools,
                "languages": _top(languages, limit),
                "file_suffixes": _top(suffixes, limit),
                "source_roots": _top(source_roots, limit),
                "test_roots": _top(test_roots, limit),
                "import_roots": _top(imports, limit),
                "route_count": len(route_symbols),
                "test_symbol_count": len(test_symbols),
            },
            "routes": {
                "path_patterns": _top(route_paths, limit),
                "samples": route_symbols[:limit],
            },
            "tests": {
                "path_patterns": _top(test_paths, limit),
                "samples": test_symbols[:limit],
            },
            "warnings": warnings,
        }
