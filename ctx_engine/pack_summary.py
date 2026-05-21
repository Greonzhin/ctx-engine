from __future__ import annotations

import os
from pathlib import Path

from .capsule.builder import CapsuleBuilder
from .db import connect, init_db
from .integrations.rtk import estimate_tokens
from .security.ignore import is_ignored, to_posix_rel
from .security.secrets import looks_sensitive_path
from .workspace import get_workspace


def _load_indexed_files(workspace_id: str) -> list[dict[str, object]]:
    conn = init_db(connect())
    try:
        rows = conn.execute(
            """
            SELECT rel_path, skeleton, size, language
            FROM files
            WHERE workspace_id = ?
            ORDER BY rel_path ASC
            """,
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _tree_from_files(files: list[dict[str, object]]) -> list[dict[str, object]]:
    tree: dict[str, object] = {"name": ".", "tokens": 0, "children": {}}
    for item in files:
        rel = str(item.get("rel_path") or item.get("path"))
        parts = Path(rel).parts
        tokens = int(item.get("tokens") or 0)
        if tokens <= 0:
            tokens = estimate_tokens(str(item.get("skeleton") or "")) or estimate_tokens("x" * int(item.get("size") or 0))
        node = tree
        node["tokens"] = int(node["tokens"]) + int(tokens)
        for part in parts:
            children = node["children"]
            if part not in children:
                children[part] = {"name": part, "tokens": 0, "children": {}}
            node = children[part]
            node["tokens"] = int(node["tokens"]) + int(tokens)

    def flatten(node: dict[str, object]) -> dict[str, object]:
        children = [flatten(child) for child in sorted(node["children"].values(), key=lambda v: str(v["name"]))]
        return {"name": node["name"], "tokens": int(node["tokens"]), "children": children}

    return [flatten(child) for child in sorted(tree["children"].values(), key=lambda v: str(v["name"]))]


def _discover_nonindexed_omissions(root: Path, indexed_paths: set[str], limit: int = 200) -> list[dict[str, object]]:
    omitted: list[dict[str, object]] = []
    for dirpath, dirs, names in os.walk(root):
        current = Path(dirpath)
        for name in names:
            path = current / name
            rel = to_posix_rel(path, root)
            if rel in indexed_paths:
                continue
            reason = None
            if looks_sensitive_path(path):
                reason = "secret_redacted"
            elif is_ignored(rel):
                reason = "ignored_path"
            if not reason:
                continue
            omitted.append(
                {
                    "path": rel,
                    "tokens": 0,
                    "language": "unknown",
                    "reason": reason,
                }
            )
            if len(omitted) >= limit:
                return omitted
    return omitted


def pack_summary(
    query: str,
    workspace_id: str | None = None,
    token_budget: int = 4000,
    max_files: int = 40,
    include_docs: bool = True,
) -> dict[str, object]:
    workspace = get_workspace(workspace_id)
    if not workspace:
        raise ValueError("No workspace is registered. Run `ctx index <path>` first.")
    wid = str(workspace["id"])
    workspace_root = Path(str(workspace["root_path"]))
    indexed = _load_indexed_files(wid)
    indexed_paths = {str(item.get("rel_path")) for item in indexed}
    capsule = CapsuleBuilder().build(
        query,
        token_budget=token_budget,
        include_docs=include_docs,
        workspace_id=wid,
        client_id="pack-summary",
    )
    selected = [str(item.get("path")) for item in capsule.get("selected_files", [])][:max_files]
    selected_set = set(selected)

    selected_rows: list[dict[str, object]] = []
    omitted_rows: list[dict[str, object]] = []
    for row in indexed:
        rel = str(row.get("rel_path"))
        tokens = estimate_tokens(str(row.get("skeleton") or ""))
        item = {"path": rel, "tokens": tokens, "language": row.get("language")}
        if rel in selected_set:
            selected_rows.append(item)
        else:
            item["reason"] = "budget_cut"
            omitted_rows.append(item)

    quarantined_docs = list(capsule.get("omitted_context", {}).get("quarantined_docs", []))
    omitted = omitted_rows[:200]
    omitted.extend(_discover_nonindexed_omissions(workspace_root, indexed_paths, limit=100))
    for doc in quarantined_docs:
        omitted.append(
            {
                "path": doc.get("path"),
                "tokens": 0,
                "language": "docs",
                "reason": doc.get("reason", "quarantined_high_risk_doc"),
            }
        )
    selected_tokens_total = sum(int(item.get("tokens") or 0) for item in selected_rows)
    omitted_tokens_total = sum(int(item.get("tokens") or 0) for item in omitted)

    return {
        "status": "ok",
        "workspace_id": wid,
        "workspace_path": workspace["root_path"],
        "query": query,
        "token_budget": token_budget,
        "selected_files": selected_rows,
        "selected_file_count": len(selected_rows),
        "selected_tokens_total": selected_tokens_total,
        "omitted_files": omitted,
        "omitted_file_count": len(omitted),
        "omitted_tokens_total": omitted_tokens_total,
        "token_tree": _tree_from_files(selected_rows),
    }
