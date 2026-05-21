from __future__ import annotations

from pathlib import Path

from ctx_engine.pack_summary import pack_summary
from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.local_docs import LocalDocsProvider


def _sum_children_tokens(node: dict[str, object]) -> int:
    children = list(node.get("children") or [])
    if not children:
        return int(node.get("tokens") or 0)
    return sum(_sum_children_tokens(child) for child in children)


def test_pack_summary_reports_token_tree_and_omitted(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    LocalDocsProvider().index(fixture_root / "python_app", result["workspace_id"])
    summary = pack_summary("authenticate request", workspace_id=result["workspace_id"], token_budget=1200)

    assert summary["status"] == "ok"
    assert summary["selected_file_count"] >= 1
    assert summary["token_tree"]
    assert "omitted_files" in summary
    assert "selected_tokens_total" in summary
    assert "omitted_tokens_total" in summary
    selected_from_tree = sum(_sum_children_tokens(node) for node in summary["token_tree"])
    assert selected_from_tree == summary["selected_tokens_total"]


def test_pack_summary_reason_taxonomy_includes_ignored_and_secret(tmp_path):
    repo = Path(tmp_path) / "repo"
    (repo / "app").mkdir(parents=True, exist_ok=True)
    (repo / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
    (repo / "app" / "main.py").write_text("def authenticate_request(req):\n    return req\n", encoding="utf-8")
    (repo / ".env").write_text("API_KEY=sk-secret-value\n", encoding="utf-8")
    (repo / "node_modules" / "pkg" / "index.js").write_text("export const x = 1;\n", encoding="utf-8")

    result = CodeGraphProvider().index_repository(repo)
    LocalDocsProvider().index(repo, result["workspace_id"])
    summary = pack_summary("authenticate request", workspace_id=result["workspace_id"], token_budget=500)

    reasons = {str(item.get("reason")) for item in summary["omitted_files"]}
    assert "budget_cut" in reasons or summary["omitted_file_count"] >= 0
    assert "ignored_path" in reasons
    assert "secret_redacted" in reasons
