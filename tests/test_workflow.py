from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.workflow import list_workflows, show_workflow, suggest_workflow


def test_workflow_list_show_and_suggest_are_deterministic():
    listed = list_workflows()
    assert listed["status"] == "ok"
    assert listed["count"] == 5
    assert [item["name"] for item in listed["recipes"]] == sorted(item["name"] for item in listed["recipes"])

    shown = show_workflow("fix-failing-test")
    assert shown["status"] == "ok"
    assert shown["intent"] == "debug_or_test"

    assert suggest_workflow("fix failing auth test")["selected"] == "fix-failing-test"
    assert suggest_workflow("update README docs")["selected"] == "update-docs"


def test_workflow_cli(capsys):
    assert main(["workflow", "suggest", "fix failing auth test"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selected"] == "fix-failing-test"

    assert main(["workflow", "show", "missing"]) == 1
    missing = json.loads(capsys.readouterr().out)
    assert missing["status"] == "not_found"
