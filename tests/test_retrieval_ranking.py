from __future__ import annotations

from ctx_engine.graph.parsers import javascript_parser, python_parser
from ctx_engine.providers.code_graph import CodeGraphProvider


def test_retrieval_exact_symbol_match_is_ranked_first(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    rows = CodeGraphProvider().search_symbols("authenticate_request", result["workspace_id"], limit=5)
    assert rows
    assert rows[0]["name"] == "authenticate_request"


def test_retrieval_partial_match_beats_path_only(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    partial = CodeGraphProvider().search_symbols("authenticate", result["workspace_id"], limit=5)
    path_only = CodeGraphProvider().search_symbols("middleware", result["workspace_id"], limit=5)
    assert partial
    assert path_only
    assert partial[0]["name"] == "authenticate_request"
    assert "middleware.py" in str(path_only[0]["rel_path"])


def test_retrieval_is_stable_with_and_without_tree_sitter(fixture_root, monkeypatch):
    root = fixture_root / "python_app"
    monkeypatch.setattr(python_parser, "tree_sitter_available", lambda _lang, _text: False)
    monkeypatch.setattr(javascript_parser, "tree_sitter_available", lambda _lang, _text: False)
    result_no_tree = CodeGraphProvider().index_repository(root)
    no_tree_rows = CodeGraphProvider().search_symbols("authenticate_request", result_no_tree["workspace_id"], limit=3)
    assert no_tree_rows and no_tree_rows[0]["name"] == "authenticate_request"

    monkeypatch.setattr(python_parser, "tree_sitter_available", lambda _lang, _text: True)
    monkeypatch.setattr(javascript_parser, "tree_sitter_available", lambda _lang, _text: True)
    result_tree = CodeGraphProvider().index_repository(root)
    tree_rows = CodeGraphProvider().search_symbols("authenticate_request", result_tree["workspace_id"], limit=3)
    assert tree_rows and tree_rows[0]["name"] == "authenticate_request"


def test_retrieval_smoke_topk_metrics(fixture_root):
    scenarios = [
        (fixture_root / "python_app", "authenticate_request", "authenticate_request"),
        (fixture_root / "python_app", "AuthMiddleware", "AuthMiddleware"),
        (fixture_root / "ts_app", "authenticateToken", "authenticateToken"),
    ]
    top1 = 0
    top3 = 0
    total = len(scenarios)
    for root, query, expected in scenarios:
        result = CodeGraphProvider().index_repository(root)
        rows = CodeGraphProvider().search_symbols(query, result["workspace_id"], limit=3)
        names = [str(item.get("name")) for item in rows]
        if names and names[0] == expected:
            top1 += 1
        if expected in names:
            top3 += 1
    top1_ratio = top1 / total
    top3_ratio = top3 / total
    assert top1_ratio >= 0.66
    assert top3_ratio == 1.0
