from __future__ import annotations

import json
from pathlib import Path

from .db import connect, init_db
from .providers.action_ledger import ActionLedger
from .providers.code_graph import CodeGraphProvider
from .providers.local_docs import LocalDocsProvider
from .workspace import get_workspace


def _default_cases(workspace_id: str, limit: int = 20) -> list[dict[str, str]]:
    conn = init_db(connect())
    try:
        rows = conn.execute(
            """
            SELECT name
            FROM symbols
            WHERE workspace_id = ?
              AND kind NOT IN ('route', 'test', 'it', 'describe')
            GROUP BY name
            ORDER BY COUNT(*) DESC, MIN(start_line) ASC
            LIMIT ?
            """,
            (workspace_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [{"query": str(row["name"]), "expected": str(row["name"])} for row in rows if str(row["name"]).strip()]


def _load_cases(cases_file: str | Path | None, workspace_id: str) -> list[dict[str, str]]:
    if not cases_file:
        return _default_cases(workspace_id)
    payload = json.loads(Path(cases_file).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("retrieval benchmark cases file must be a JSON array")
    cases: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        expected = str(item.get("expected") or query).strip()
        if query and expected:
            cases.append({"query": query, "expected": expected})
    return cases


def run_retrieval_benchmark(
    path: str | Path | None = None,
    workspace_id: str | None = None,
    cases_file: str | Path | None = None,
    top_k: int = 3,
) -> dict[str, object]:
    indexed = None
    if path is not None:
        root = Path(path).resolve()
        indexed = CodeGraphProvider().index_repository(root)
        LocalDocsProvider().index(indexed["root_path"], str(indexed["workspace_id"]))
        workspace_id = str(indexed["workspace_id"])
    workspace = get_workspace(workspace_id)
    if not workspace:
        raise ValueError("No workspace is registered. Run `ctx index <path>` first.")
    wid = str(workspace["id"])
    top_k = max(1, min(int(top_k), 20))

    cases = _load_cases(cases_file, wid)
    results: list[dict[str, object]] = []
    top1_hits = 0
    topk_hits = 0
    for case in cases:
        rows = CodeGraphProvider().search_symbols(case["query"], workspace_id=wid, limit=top_k)
        names = [str(item.get("name")) for item in rows]
        top1 = bool(names and names[0] == case["expected"])
        topk = case["expected"] in names
        if top1:
            top1_hits += 1
        if topk:
            topk_hits += 1
        results.append(
            {
                "query": case["query"],
                "expected": case["expected"],
                "top1_hit": top1,
                f"top{top_k}_hit": topk,
                "candidates": names,
            }
        )
    total = len(results)
    top1_ratio = round(top1_hits / total, 4) if total else 0.0
    topk_ratio = round(topk_hits / total, 4) if total else 0.0

    output = {
        "status": "ok",
        "workspace_id": wid,
        "workspace_path": workspace["root_path"],
        "top_k": top_k,
        "cases_total": total,
        "metrics": {
            "top1_hits": top1_hits,
            "top1_ratio": top1_ratio,
            f"top{top_k}_hits": topk_hits,
            f"top{top_k}_ratio": topk_ratio,
        },
        "cases": results,
        "indexed": indexed,
    }
    ActionLedger().record("retrieval_benchmark", "retrieval benchmark run", output, client_id="benchmark", workspace_id=wid)
    return output

