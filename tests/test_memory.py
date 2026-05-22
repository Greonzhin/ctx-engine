from __future__ import annotations

from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.memory import BuiltInMemoryProvider
from ctx_engine.cli import main


def test_memory_retain_and_recall(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    provider = BuiltInMemoryProvider()
    written = provider.retain("Authentication middleware lives in app/middleware.py", workspace_id=result["workspace_id"])
    assert written["id"]
    matches = provider.recall("middleware", workspace_id=result["workspace_id"])
    assert matches
    assert "middleware" in matches[0]["claim"]


def test_memory_report_counts_tiers_namespaces_and_conflicts(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    provider = BuiltInMemoryProvider()
    first = provider.retain("Auth fact", workspace_id=result["workspace_id"], lifecycle_tier="hot", agent_namespace="agent-a")
    second = provider.retain("Auth fact", workspace_id=result["workspace_id"], source="assistant", lifecycle_tier="warm", agent_namespace="agent-a")
    provider.retain("Other auth note", workspace_id=result["workspace_id"], lifecycle_tier="cold", agent_namespace="agent-b")
    provider.verify(first["id"], "verified in middleware")
    provider.supersede(second["id"], first["id"])

    report = provider.report(workspace_id=result["workspace_id"], agent_namespace="agent-a")
    assert report["status"] == "ok"
    assert report["summary"]["total"] == 2
    assert report["summary"]["active"] == 1
    assert report["summary"]["superseded"] == 1
    assert report["summary"]["verified"] == 1
    assert report["summary"]["namespace_counts"]["agent-a"] == 1
    assert report["recent"][0]["id"]


def test_memory_cli_report_and_workspace_scoped_add(fixture_root, capsys):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")

    assert main(["memory", "add", "CLI memory note", "--workspace-id", result["workspace_id"], "--lifecycle-tier", "hot"]) == 0
    capsys.readouterr()

    assert main(["memory", "report", "--workspace-id", result["workspace_id"]]) == 0
    report = __import__("json").loads(capsys.readouterr().out)
    assert report["status"] == "ok"
    assert report["workspace_id"] == result["workspace_id"]
    assert report["summary"]["active"] == 1
