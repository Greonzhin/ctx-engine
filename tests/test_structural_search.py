from __future__ import annotations

import json
import subprocess

from ctx_engine.cli import main
from ctx_engine.structural_search import search_structural


def test_structural_search_missing_ast_grep_warns_non_strict(tmp_path, monkeypatch):
    monkeypatch.setattr("ctx_engine.structural_search.shutil.which", lambda _name: None)

    result = search_structural(tmp_path, pattern="def $FUNC($$$): $$$", strict=False)

    assert result["status"] == "warn"
    assert result["command_available"] is False
    assert "ast-grep command is not available" in result["warnings"]


def test_structural_search_missing_ast_grep_fails_strict(tmp_path, monkeypatch):
    monkeypatch.setattr("ctx_engine.structural_search.shutil.which", lambda _name: None)

    result = search_structural(tmp_path, pattern="def $FUNC($$$): $$$", strict=True)

    assert result["status"] == "fail"
    assert "ast-grep command is not available" in result["errors"]


def test_structural_search_normalizes_ast_grep_json(tmp_path, monkeypatch):
    monkeypatch.setattr("ctx_engine.structural_search.shutil.which", lambda name: f"/bin/{name}")
    payload = [
        {
            "file": "app.py",
            "range": {"start": {"line": 3, "column": 1}},
            "text": "def authenticate_request(headers):",
            "language": "python",
        }
    ]

    def fake_run(command, timeout):
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("ctx_engine.structural_search._run_command", fake_run)

    result = search_structural(tmp_path, pattern="def $FUNC($$$): $$$", language="python")

    assert result["status"] == "findings"
    assert result["findings"][0]["engine"] == "ast-grep"
    assert result["findings"][0]["path"] == "app.py"
    assert result["findings"][0]["line"] == 3
    assert result["findings"][0]["match"] == "def authenticate_request(headers):"


def test_structural_search_cli_with_mocked_ast_grep(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("ctx_engine.structural_search.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(command, timeout):
        payload = [{"file": "app.py", "start": {"line": 1, "column": 0}, "lines": "def main(): pass"}]
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("ctx_engine.structural_search._run_command", fake_run)

    assert main(["structural-search", str(tmp_path), "--pattern", "def $FUNC($$$): $$$", "--lang", "python", "--strict"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "findings"
    assert out["command_available"] is True
    assert out["findings"][0]["language"] == "python"


def test_structural_search_cli_non_strict_allows_missing_ast_grep(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("ctx_engine.structural_search.shutil.which", lambda _name: None)

    assert main(["structural-search", str(tmp_path), "--pattern", "def $FUNC($$$): $$$", "--lang", "python"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "warn"
