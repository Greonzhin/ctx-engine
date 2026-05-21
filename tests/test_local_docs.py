from __future__ import annotations

from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.local_docs import LocalDocsProvider


def test_local_docs_indexes_readme(fixture_root):
    root = fixture_root / "python_app"
    result = CodeGraphProvider().index_repository(root)
    docs = LocalDocsProvider().index(root, result["workspace_id"])
    assert docs["docs"] >= 1
    found = LocalDocsProvider().query("Authentication", result["workspace_id"])
    assert found
    assert found[0]["rel_path"] == "README.md"
