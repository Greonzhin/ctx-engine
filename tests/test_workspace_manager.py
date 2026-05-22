from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.workspace import get_workspace, register_workspace, set_active_workspace, workspace_inventory


def test_workspace_manager_tracks_active_workspace(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    one = register_workspace(first, display_name="One")
    two = register_workspace(second, display_name="Two")

    active = set_active_workspace(one["id"])
    assert active["id"] == one["id"]
    assert get_workspace()["id"] == one["id"]
    assert get_workspace(two["id"])["active"] is False

    active = set_active_workspace(second)
    assert active["id"] == two["id"]
    assert get_workspace()["id"] == two["id"]

    inventory = workspace_inventory()
    assert inventory["status"] == "ok"
    assert inventory["workspace_count"] == 2
    assert inventory["active_workspace"]["id"] == two["id"]
    assert [item for item in inventory["workspaces"] if item["active"]][0]["id"] == two["id"]


def test_workspace_cli_add_use_list_check(tmp_path, capsys):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    assert main(["workspace", "add", str(first), "--name", "First", "--activate"]) == 0
    added = json.loads(capsys.readouterr().out)
    first_id = added["workspace"]["id"]
    assert added["activated"] is True

    assert main(["workspace", "add", str(second), "--name", "Second"]) == 0
    second_id = json.loads(capsys.readouterr().out)["workspace"]["id"]

    assert main(["workspace", "use", second_id]) == 0
    used = json.loads(capsys.readouterr().out)
    assert used["active_workspace"]["id"] == second_id

    assert main(["workspace", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["status"] == "ok"
    assert listed["workspace_count"] == 2
    assert listed["active_workspace"]["id"] == second_id

    assert main(["workspace", "use", str(first / "nested" / "file.py")]) == 0
    nested = json.loads(capsys.readouterr().out)
    assert nested["active_workspace"]["id"] == first_id

    assert main(["workspace", "check", "--strict"]) == 0


def test_workspace_cli_strict_check_fails_without_workspaces(capsys):
    assert main(["workspace", "check", "--strict"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["workspace_count"] == 0


def test_workspace_inventory_marks_indexed(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    inventory = workspace_inventory()
    assert inventory["workspace_count"] == 1
    assert inventory["workspaces"][0]["id"] == result["workspace_id"]
    assert inventory["workspaces"][0]["indexed"] is True
    assert inventory["workspaces"][0]["active"] is True
