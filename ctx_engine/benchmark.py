from __future__ import annotations

import math
from pathlib import Path

from .capsule.builder import CapsuleBuilder
from .db import connect, init_db, stable_json
from .providers.action_ledger import ActionLedger
from .providers.code_graph import CodeGraphProvider
from .providers.local_docs import LocalDocsProvider
from .workspace import get_workspace, workspace_fingerprint


def _tokens_for_chars(chars: int | None) -> int:
    if not chars:
        return 0
    return max(1, math.ceil(chars / 4))


def _context_tokens(capsule: dict[str, object]) -> dict[str, int]:
    skeletons = sum(_tokens_for_chars(len(str(item.get("skeleton", "")))) for item in capsule.get("code_skeletons", []))
    snippets = sum(_tokens_for_chars(len(str(item.get("text", "")))) for item in capsule.get("exact_snippets", []))
    docs = sum(_tokens_for_chars(len(str(item.get("text", "")))) for item in capsule.get("docs_context", []))
    memory = sum(_tokens_for_chars(len(str(item.get("summary", "")))) for item in capsule.get("memory_context", []))
    symbols = sum(_tokens_for_chars(len(str(item.get("signature", "")))) for item in capsule.get("selected_symbols", []))
    build = _tokens_for_chars(len(stable_json(capsule.get("build_test_context", {}))))
    total = skeletons + snippets + docs + memory + symbols + build
    return {
        "skeletons": skeletons,
        "snippets": snippets,
        "docs": docs,
        "memory": memory,
        "symbols": symbols,
        "build": build,
        "total": total,
    }


def _baseline(workspace_id: str) -> dict[str, object]:
    conn = init_db(connect())
    try:
        file_row = conn.execute(
            """
            SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS chars
            FROM files
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchone()
        doc_row = conn.execute(
            """
            SELECT COUNT(*) AS count, COALESCE(SUM(LENGTH(body)), 0) AS chars
            FROM docs
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchone()
        symbol_row = conn.execute(
            "SELECT COUNT(*) AS count FROM symbols WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
    finally:
        conn.close()

    code_tokens = _tokens_for_chars(int(file_row["chars"]))
    docs_tokens = _tokens_for_chars(int(doc_row["chars"]))
    return {
        "files": int(file_row["count"]),
        "symbols": int(symbol_row["count"]),
        "docs": int(doc_row["count"]),
        "code_tokens": code_tokens,
        "docs_tokens": docs_tokens,
        "total_tokens": code_tokens + docs_tokens,
    }


def benchmark_capsule(
    query: str,
    path: str | Path | None = None,
    workspace_id: str | None = None,
    token_budget: int = 4000,
    include_docs: bool = True,
    mode: str = "safe",
    reindex: bool = False,
) -> dict[str, object]:
    indexed: dict[str, object] | None = None
    docs_indexed: dict[str, object] | None = None

    if path is not None:
        root = Path(path).resolve()
        indexed = CodeGraphProvider().index_repository(root)
        docs_indexed = LocalDocsProvider().index(indexed["root_path"], str(indexed["workspace_id"]))
        workspace_id = str(indexed["workspace_id"])
    elif reindex:
        workspace = get_workspace(workspace_id)
        if not workspace:
            raise ValueError("No workspace is registered. Run `ctx index <path>` first.")
        indexed = CodeGraphProvider().index_repository(str(workspace["root_path"]))
        docs_indexed = LocalDocsProvider().index(indexed["root_path"], str(indexed["workspace_id"]))
        workspace_id = str(indexed["workspace_id"])

    workspace = get_workspace(workspace_id)
    if not workspace:
        raise ValueError("No workspace is registered. Run `ctx index <path>` first.")
    wid = str(workspace["id"])

    capsule = CapsuleBuilder(mode=mode).build(
        query,
        token_budget=token_budget,
        include_docs=include_docs,
        workspace_id=wid,
        client_id="benchmark",
    )
    baseline = _baseline(wid)
    context_tokens = _context_tokens(capsule)
    capsule_transport_tokens = _tokens_for_chars(len(stable_json(capsule)))
    capsule_context_tokens = context_tokens["total"]
    baseline_total = int(baseline["total_tokens"])
    selected_paths = sorted({str(item.get("path")) for item in capsule.get("selected_files", [])})
    reduction_ratio = None
    if baseline_total:
        reduction_ratio = round(1 - (capsule_context_tokens / baseline_total), 4)
    warnings = []
    if reduction_ratio is not None and reduction_ratio < 0:
        warnings.append("Capsule context is larger than the indexed baseline; this is common for tiny fixture repositories.")

    result = {
        "status": "ok",
        "query": query,
        "workspace_id": wid,
        "workspace_path": workspace["root_path"],
        "mode": mode,
        "token_budget": token_budget,
        "include_docs": include_docs,
        "index_fingerprint": workspace_fingerprint(wid),
        "baseline": baseline,
        "capsule": {
            "cache": capsule.get("cache"),
            "capsule_id": capsule.get("provenance", {}).get("capsule_id"),
            "context_total_tokens": capsule_context_tokens,
            "transport_total_tokens": capsule_transport_tokens,
            "context_tokens": context_tokens,
            "selected_files": selected_paths,
            "selected_file_count": len(selected_paths),
            "omitted_file_count": max(0, int(baseline["files"]) - len(selected_paths)),
            "selected_symbol_count": len(capsule.get("selected_symbols", [])),
            "docs_context_count": len(capsule.get("docs_context", [])),
            "memory_context_count": len(capsule.get("memory_context", [])),
        },
        "reduction": {
            "baseline_tokens": baseline_total,
            "capsule_context_tokens": capsule_context_tokens,
            "ratio": reduction_ratio,
            "percent": None if reduction_ratio is None else round(reduction_ratio * 100, 2),
        },
        "warnings": warnings,
        "indexed": {"code": indexed, "docs": docs_indexed},
    }
    ActionLedger().record("benchmark", f"benchmark for {query[:80]}", result, client_id="benchmark", workspace_id=wid)
    return result
