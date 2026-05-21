from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ctx_engine.cli import main
from ctx_engine.security_scan import scan_security


def test_security_scan_missing_scanner_warns_non_strict(tmp_path, monkeypatch):
    monkeypatch.setattr("ctx_engine.security_scan.shutil.which", lambda _name: None)

    result = scan_security(tmp_path, scanner="semgrep", strict=False)

    assert result["status"] == "warn"
    assert result["command_available"] is False
    assert result["scanner_results"][0]["status"] == "unavailable"


def test_security_scan_missing_scanner_fails_strict(tmp_path, monkeypatch):
    monkeypatch.setattr("ctx_engine.security_scan.shutil.which", lambda _name: None)

    result = scan_security(tmp_path, scanner="gitleaks", strict=True)

    assert result["status"] == "fail"
    assert "gitleaks command is not available" in result["errors"]


def test_security_scan_normalizes_semgrep_json(tmp_path, monkeypatch):
    monkeypatch.setattr("ctx_engine.security_scan.shutil.which", lambda name: f"/bin/{name}")
    payload = {
        "results": [
            {
                "check_id": "python.lang.security.audit",
                "path": "app.py",
                "start": {"line": 7},
                "extra": {"message": "audit finding", "severity": "WARNING"},
            }
        ]
    }

    def fake_run(command, timeout):
        return subprocess.CompletedProcess(command, 1, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("ctx_engine.security_scan._run_command", fake_run)

    result = scan_security(tmp_path, scanner="semgrep")

    assert result["status"] == "findings"
    assert result["findings"][0]["scanner"] == "semgrep"
    assert result["findings"][0]["rule_id"] == "python.lang.security.audit"


def test_security_scan_normalizes_gitleaks_json(tmp_path, monkeypatch):
    monkeypatch.setattr("ctx_engine.security_scan.shutil.which", lambda name: f"/bin/{name}")
    payload = [{"RuleID": "generic-api-key", "Description": "secret", "File": ".env", "StartLine": 1}]

    def fake_run(command, timeout):
        return subprocess.CompletedProcess(command, 1, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("ctx_engine.security_scan._run_command", fake_run)

    result = scan_security(tmp_path, scanner="gitleaks")

    assert result["status"] == "findings"
    assert result["findings"][0]["scanner"] == "gitleaks"
    assert result["findings"][0]["path"] == ".env"


def test_security_scan_cli_all_with_mocked_scanners(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("ctx_engine.security_scan.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(command, timeout):
        scanner = Path(command[0]).name
        if scanner == "semgrep":
            return subprocess.CompletedProcess(command, 0, stdout='{"results":[]}', stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")

    monkeypatch.setattr("ctx_engine.security_scan._run_command", fake_run)

    assert main(["security-scan", str(tmp_path), "--all", "--strict"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "pass"
    assert len(out["scanner_results"]) == 2
