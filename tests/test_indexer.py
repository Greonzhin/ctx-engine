from __future__ import annotations

from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.local_docs import LocalDocsProvider
from ctx_engine.workspace import workspace_fingerprint


def test_indexer_indexes_python_symbols(fixture_root):
    root = fixture_root / "python_app"
    result = CodeGraphProvider().index_repository(root)
    docs = LocalDocsProvider().index(result["root_path"], result["workspace_id"])
    assert result["files"] >= 2
    assert result["symbols"] >= 3
    assert result["code_index_hash"]
    assert docs["docs_index_hash"]
    fingerprint = workspace_fingerprint(result["workspace_id"])
    assert fingerprint["code_index_hash"] == result["code_index_hash"]
    assert fingerprint["docs_index_hash"] == docs["docs_index_hash"]
    matches = CodeGraphProvider().search_symbols("authenticate", result["workspace_id"])
    assert any(item["name"] == "authenticate_request" for item in matches)


def test_indexer_indexes_typescript_symbols(fixture_root):
    root = fixture_root / "ts_app"
    result = CodeGraphProvider().index_repository(root)
    matches = CodeGraphProvider().search_symbols("authenticateToken", result["workspace_id"])
    assert any(item["name"] == "authenticateToken" for item in matches)
    assert result["files"] >= 2
