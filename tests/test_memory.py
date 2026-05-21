from __future__ import annotations

from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.memory import BuiltInMemoryProvider


def test_memory_retain_and_recall(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    provider = BuiltInMemoryProvider()
    written = provider.retain("Authentication middleware lives in app/middleware.py", workspace_id=result["workspace_id"])
    assert written["id"]
    matches = provider.recall("middleware", workspace_id=result["workspace_id"])
    assert matches
    assert "middleware" in matches[0]["claim"]
