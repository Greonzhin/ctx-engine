from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .providers.local_docs import is_doc_path, title_for
from .providers.safety import SafetyProvider
from .security.ignore import is_ignored, to_posix_rel


DECISION_KEYWORDS = (
    "decision",
    "decide",
    "adopt",
    "keep",
    "done:",
    "implemented",
    "not implemented",
    "do not",
    "must",
    "optional",
    "fallback",
    "out of scope",
    "candidate",
    "later",
    "tamamlandi",
    "hedef",
    "durum",
)

CATEGORY_KEYWORDS = {
    "mcp": ("mcp", "gateway", "tool", "descriptor", "allowlist"),
    "safety": ("safety", "security", "secret", "private", "egress", "policy", "prompt injection"),
    "memory": ("memory", "hindsight", "sqlite", "lifecycle", "recall"),
    "docker": ("docker", "compose", "container", "non-root"),
    "ci": ("ci", "github actions", "quality gate", "pytest"),
    "docs": ("docs", "documentation", "context7", "adr", "readme"),
    "workflow": ("workflow", "recipe", "hook", "skill", "feedback"),
    "graph": ("graph", "kuzu", "lsp", "scip", "semantic", "symbol"),
}

SKIPPED_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    ".venv",
    ".ctx-engine-data",
    ".tmp",
    "__pycache__",
    "ctx_engine.egg-info",
}


def _decision_id(path: str, line: int, text: str) -> str:
    return hashlib.sha256(f"{path}:{line}:{text}".encode("utf-8")).hexdigest()[:16]


def _status_for(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("do not", "not implemented", "out of scope", "keep-out", "yasak")):
        return "guardrail"
    if any(term in lowered for term in ("done:", "implemented", "tamamlandi", "completed")):
        return "implemented"
    if any(term in lowered for term in ("candidate", "later", "future", "optional", "p2", "p1/p2")):
        return "planned"
    return "decided"


def _category_for(text: str) -> str:
    lowered = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "general"


def _looks_like_decision(line: str, heading: str) -> bool:
    lowered = f"{heading}\n{line}".lower()
    if any(keyword in lowered for keyword in DECISION_KEYWORDS):
        return True
    return bool(re.search(r"\b(p0|p1|p2)\b", lowered) and re.search(r"\b(add|keep|skip|use|default|fallback)\b", lowered))


def _iter_doc_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirs, names in os.walk(root):
        current = Path(dirpath)
        dirs[:] = [
            name
            for name in dirs
            if name not in SKIPPED_DIR_NAMES
            and not name.startswith(".cache")
            if not is_ignored(to_posix_rel(current / name, root))
            and not is_ignored(f"{to_posix_rel(current / name, root)}/")
        ]
        for name in names:
            path = current / name
            rel = to_posix_rel(path, root)
            if is_doc_path(rel) and not is_ignored(rel):
                files.append(path)
    return sorted(files)


def _extract_file_decisions(path: Path, root: Path, limit: int) -> list[dict[str, Any]]:
    rel_path = to_posix_rel(path, root)
    text = path.read_text(encoding="utf-8", errors="replace")
    doc_title = title_for(text, rel_path)
    heading = doc_title
    decisions: list[dict[str, Any]] = []

    for index, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            heading = line.lstrip("#").strip() or doc_title
        candidate = line
        if line.startswith(("-", "*")):
            candidate = line.lstrip("-* ").strip()
        if not _looks_like_decision(candidate, heading):
            continue
        status = _status_for(candidate)
        category = _category_for(f"{heading}\n{candidate}")
        decisions.append(
            {
                "id": _decision_id(rel_path, index, candidate),
                "path": rel_path,
                "line": index,
                "title": heading,
                "text": candidate[:500],
                "status": status,
                "category": category,
            }
        )
        if len(decisions) >= limit:
            break
    return decisions


def _build_edges(decisions: list[dict[str, Any]], limit: int) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    by_category: dict[str, list[dict[str, Any]]] = {}
    by_path: dict[str, list[dict[str, Any]]] = {}
    for decision in decisions:
        by_category.setdefault(str(decision["category"]), []).append(decision)
        by_path.setdefault(str(decision["path"]), []).append(decision)

    for items in by_path.values():
        ordered = sorted(items, key=lambda item: int(item["line"]))
        for left, right in zip(ordered, ordered[1:]):
            edges.append({"source": str(left["id"]), "target": str(right["id"]), "relation": "same_document_next"})
            if len(edges) >= limit:
                return edges

    for category, items in by_category.items():
        if len(items) < 2:
            continue
        anchor = items[0]
        for item in items[1:]:
            edges.append({"source": str(anchor["id"]), "target": str(item["id"]), "relation": f"same_category:{category}"})
            if len(edges) >= limit:
                return edges
    return edges


def decision_report(path: str | Path = ".", limit: int = 50) -> dict[str, Any]:
    root = Path(path).resolve()
    safety = SafetyProvider()
    warnings: list[str] = []
    decisions: list[dict[str, Any]] = []
    scanned = 0

    for doc_path in _iter_doc_files(root):
        if len(decisions) >= limit:
            break
        allowed = safety.can_read_file(doc_path, root)
        if not allowed.allowed:
            continue
        scanned += 1
        decisions.extend(_extract_file_decisions(doc_path, root, max(0, limit - len(decisions))))

    if scanned == 0:
        warnings.append("no local documentation files found")

    status_counts = Counter(str(item["status"]) for item in decisions)
    category_counts = Counter(str(item["category"]) for item in decisions)
    edges = _build_edges(decisions, limit)

    return {
        "status": "ok" if scanned else "warn",
        "path": str(root),
        "documents_scanned": scanned,
        "decision_count": len(decisions),
        "summary": {
            "by_status": dict(sorted(status_counts.items())),
            "by_category": dict(sorted(category_counts.items())),
        },
        "decisions": decisions[:limit],
        "edges": edges,
        "warnings": warnings,
    }
