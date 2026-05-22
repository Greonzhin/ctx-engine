from __future__ import annotations

from pathlib import Path
from typing import Any

from .decisions import decision_report
from .providers.build_test import BuildTestProvider
from .providers.code_graph import CodeGraphProvider
from .providers.conventions import ConventionProvider
from .providers.local_docs import LocalDocsProvider
from .workspace import get_workspace, get_workspace_for_path


def _resolve_workspace(path: Path, workspace_id: str | None = None) -> dict[str, Any] | None:
    if workspace_id:
        return get_workspace(workspace_id)
    return get_workspace_for_path(path) or get_workspace()


def _unique_commands(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        command = str(item.get("command") or "")
        if not command or command in seen:
            continue
        seen.add(command)
        unique.append(item)
    return unique


def migration_plan(
    query: str,
    path: str | Path = ".",
    workspace_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    root = Path(path).resolve()
    workspace = _resolve_workspace(root, workspace_id)
    warnings: list[str] = []
    if not workspace:
        return {
            "status": "empty",
            "query": query,
            "path": str(root),
            "workspace_id": None,
            "selected_files": [],
            "docs": [],
            "decisions": [],
            "test_plan": [],
            "phases": [],
            "risks": [],
            "warnings": ["No workspace is registered. Run `ctx index <path>` first."],
        }

    wid = str(workspace["id"])
    workspace_root = Path(str(workspace["root_path"]))
    code = CodeGraphProvider()
    blast = code.blast_radius(query, workspace_id=wid, depth=2, limit=limit)
    selected_files = [
        {
            "path": item.get("path"),
            "reasons": item.get("reasons", []),
            "semantic_confidence": item.get("semantic_confidence", item.get("confidence_label", "inferred")),
            "edge_evidence": item.get("edge_evidence", []),
        }
        for item in blast.get("related_files", [])[:limit]
    ]
    selected_paths = [str(item["path"]) for item in selected_files if item.get("path")]

    docs = [
        {
            "path": item.get("rel_path"),
            "title": item.get("title"),
            "risk_level": item.get("risk_level"),
            "risk_flags": item.get("risk_flags", []),
        }
        for item in LocalDocsProvider().query(query, wid, limit=min(8, limit), include_quarantined=False)
    ]
    decisions_payload = decision_report(workspace_root, limit=min(12, limit))
    decision_items = [
        {
            "id": item.get("id"),
            "path": item.get("path"),
            "line": item.get("line"),
            "status": item.get("status"),
            "category": item.get("category"),
            "text": item.get("text"),
        }
        for item in decisions_payload.get("decisions", [])[: min(12, limit)]
    ]
    conventions = ConventionProvider().summarize(workspace_id=wid, limit=5)
    build_test = BuildTestProvider().detect(workspace_root, selected_paths)
    test_plan = _unique_commands(list(build_test.get("test_plan", [])))
    if not test_plan:
        test_plan = [
            {
                "target": "project",
                "command": item.get("command"),
                "source": item.get("source"),
                "reason": "fallback detected project command",
                "source_files": selected_paths,
            }
            for item in build_test.get("commands", [])[:3]
        ]

    risks: list[str] = []
    guardrails = [item for item in decision_items if item.get("status") == "guardrail"]
    if guardrails:
        risks.append("Local decision graph contains guardrails that should be preserved during migration.")
    if not selected_files:
        risks.append("No code files matched the migration query; index or query may need refinement.")
    if not test_plan:
        risks.append("No verification command was detected for the selected files.")
    if docs and any(item.get("risk_level") == "medium" for item in docs):
        risks.append("Some documentation context carries medium prompt-injection risk flags.")

    phases = [
        {
            "name": "inventory",
            "goal": "Identify affected files, local docs, decisions, and project conventions before edits.",
            "inputs": ["selected_files", "docs", "decisions", "project_conventions"],
            "commands": ["ctx blast-radius \"" + query + "\"", "ctx decisions report .", "ctx conventions ."],
        },
        {
            "name": "implementation",
            "goal": "Apply the smallest migration changes in the selected files while preserving guardrails.",
            "inputs": ["selected_files", "semantic_edges", "guardrail_decisions"],
            "commands": [],
        },
        {
            "name": "verification",
            "goal": "Run targeted tests first, then the local quality gate.",
            "inputs": ["test_plan", "build_test_context"],
            "commands": [str(item.get("command")) for item in test_plan if item.get("command")] + ["scripts/quality_gate.ps1"],
        },
    ]

    if str(workspace_root).lower() != str(root).lower():
        warnings.append(f"using registered workspace root: {workspace_root}")

    return {
        "status": "ok",
        "query": query,
        "path": str(root),
        "workspace_id": wid,
        "workspace_path": str(workspace_root),
        "selected_files": selected_files,
        "docs": docs,
        "decisions": decision_items,
        "decision_summary": decisions_payload.get("summary", {}),
        "project_conventions": conventions.get("summary", {}),
        "test_plan": test_plan,
        "phases": phases,
        "risks": risks,
        "warnings": warnings,
    }
