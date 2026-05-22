from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.migration_assistant import migration_plan
from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.local_docs import LocalDocsProvider


def _index_fixture(root):
    code = CodeGraphProvider().index_repository(root)
    LocalDocsProvider().index(root, str(code["workspace_id"]))
    return code


def test_migration_plan_combines_code_docs_decisions_and_tests(fixture_root):
    root = fixture_root / "python_app"
    code = _index_fixture(root)

    result = migration_plan("migrate auth middleware", root, workspace_id=str(code["workspace_id"]), limit=10)

    assert result["status"] == "ok"
    assert result["workspace_id"] == code["workspace_id"]
    assert result["selected_files"]
    assert "app/middleware.py" in {item["path"] for item in result["selected_files"]}
    assert result["test_plan"]
    assert any("tests/test_auth.py" in item["command"] for item in result["test_plan"])
    assert [phase["name"] for phase in result["phases"]] == ["inventory", "implementation", "verification"]


def test_migration_plan_empty_without_index(tmp_path):
    result = migration_plan("migrate auth", tmp_path)

    assert result["status"] == "empty"
    assert "Run `ctx index <path>` first." in result["warnings"][0]


def test_migration_cli(fixture_root, capsys):
    root = fixture_root / "python_app"
    code = _index_fixture(root)

    assert main(["migration", "plan", "auth", str(root), "--workspace-id", str(code["workspace_id"]), "--strict"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["phases"][0]["name"] == "inventory"
