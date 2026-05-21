from __future__ import annotations

import json
import shutil

from ctx_engine.cli import main
from ctx_engine.rules_check import check_rules_drift


def _install_all(root):
    for client in ("codex", "claude", "gemini", "generic"):
        assert main(["install", client, str(root)]) == 0


def test_rules_check_passes_for_generated_files(tmp_path, capsys):
    assert main(["init", str(tmp_path)]) == 0
    capsys.readouterr()
    _install_all(tmp_path)
    capsys.readouterr()

    result = check_rules_drift(tmp_path)

    assert result["status"] == "ok"
    assert not result["errors"]

    assert main(["rules", "check", str(tmp_path), "--strict"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"


def test_rules_check_fails_when_generated_file_drifts(tmp_path, capsys):
    assert main(["init", str(tmp_path)]) == 0
    capsys.readouterr()
    _install_all(tmp_path)
    capsys.readouterr()
    (tmp_path / "AGENTS.md").write_text("manual edit\n", encoding="utf-8")

    assert main(["rules", "check", str(tmp_path), "--strict"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "drift"
    assert any(item["path"] == "AGENTS.md" and item["status"] == "drift" for item in payload["files"])


def test_rules_check_fails_when_rules_are_missing(tmp_path):
    assert check_rules_drift(tmp_path)["status"] == "error"
