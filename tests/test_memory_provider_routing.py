from __future__ import annotations

from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.memory import BuiltInMemoryProvider


def test_memory_provider_hindsight_falls_back_to_sqlite_with_warning(fixture_root, monkeypatch):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    monkeypatch.setenv("CTX_ENGINE_MEMORY_PROVIDER", "hindsight")
    monkeypatch.delenv("CTX_ENGINE_HINDSIGHT_ENDPOINT", raising=False)

    provider = BuiltInMemoryProvider()
    written = provider.retain("Auth token logic is in middleware", workspace_id=result["workspace_id"])
    assert written["provider_used"] == "sqlite_fallback"
    assert "provider_warning" in written

    rows = provider.recall("middleware", workspace_id=result["workspace_id"])
    assert rows
    assert rows[0]["provider_used"] == "sqlite_fallback"
    assert "provider_warning" in rows[0]
