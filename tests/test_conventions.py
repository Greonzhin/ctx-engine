from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.conventions import ConventionProvider


def _names(items: list[dict[str, object]]) -> set[str]:
    return {str(item["name"]) for item in items}


def test_conventions_detect_python_source_tests_and_imports(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    report = ConventionProvider().summarize(workspace_id=result["workspace_id"])

    assert report["status"] == "ok"
    assert "python" in _names(report["summary"]["languages"])
    assert "app" in _names(report["summary"]["source_roots"])
    assert "tests" in _names(report["summary"]["test_roots"])
    assert "app" in _names(report["summary"]["import_roots"])
    assert report["summary"]["test_symbol_count"] >= 1
    assert any(item["name"] == "test_authenticate_request_accepts_valid_token" for item in report["tests"]["samples"])


def test_conventions_detect_typescript_routes_and_tests(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "ts_app")
    report = ConventionProvider().summarize(workspace_id=result["workspace_id"])

    assert report["status"] == "ok"
    assert "typescript" in _names(report["summary"]["languages"])
    assert "src" in _names(report["summary"]["source_roots"])
    assert "tests" in _names(report["summary"]["test_roots"])
    assert "relative" in _names(report["summary"]["import_roots"])
    assert report["summary"]["route_count"] >= 1
    assert any("route" in str(item["kind"]) for item in report["routes"]["samples"])


def test_conventions_cli_and_capsule_context(fixture_root, capsys):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")

    assert main(["conventions", "--workspace-id", result["workspace_id"]]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["workspace_id"] == result["workspace_id"]

    assert main(["capsule", "fix failing auth test", "--workspace-id", result["workspace_id"], "--token-budget", "1200"]) == 0
    capsule = json.loads(capsys.readouterr().out)
    assert capsule["project_conventions"]["status"] == "ok"
    assert "tests" in _names(capsule["project_conventions"]["summary"]["test_roots"])
