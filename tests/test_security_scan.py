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


def test_security_scan_normalizes_secretlint_json(tmp_path, monkeypatch):
    monkeypatch.setattr("ctx_engine.security_scan.shutil.which", lambda name: f"/bin/{name}")
    payload = [{"filePath": "README.md", "messages": [{"ruleId": "@secretlint/secretlint-rule-example", "message": "secret", "line": 3, "severity": 2}]}]

    def fake_run(command, timeout):
        return subprocess.CompletedProcess(command, 1, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("ctx_engine.security_scan._run_command", fake_run)

    result = scan_security(tmp_path, scanner="secretlint")

    assert result["status"] == "findings"
    assert result["findings"][0]["scanner"] == "secretlint"
    assert result["findings"][0]["path"] == "README.md"


def test_security_scan_normalizes_npm_audit_json(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text('{"name":"demo","version":"0.0.0"}', encoding="utf-8")
    monkeypatch.setattr("ctx_engine.security_scan.shutil.which", lambda name: f"/bin/{name}")
    payload = {"vulnerabilities": {"lodash": {"name": "lodash", "severity": "high", "via": [{"source": 123, "title": "prototype pollution"}]}}}

    def fake_run(command, timeout):
        return subprocess.CompletedProcess(command, 1, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("ctx_engine.security_scan._run_command", fake_run)

    result = scan_security(tmp_path, scanner="npm-audit")

    assert result["status"] == "findings"
    assert result["findings"][0]["scanner"] == "npm-audit"
    assert result["findings"][0]["rule_id"] == "123"


def test_security_scan_normalizes_pip_audit_json(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text("demo==0.1.0\n", encoding="utf-8")
    monkeypatch.setattr("ctx_engine.security_scan.shutil.which", lambda name: f"/bin/{name}")
    payload = {"dependencies": [{"name": "demo", "version": "0.1.0", "vulns": [{"id": "PYSEC-1", "description": "bad package"}]}]}

    def fake_run(command, timeout):
        return subprocess.CompletedProcess(command, 1, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("ctx_engine.security_scan._run_command", fake_run)

    result = scan_security(tmp_path, scanner="pip-audit")

    assert result["status"] == "findings"
    assert result["findings"][0]["scanner"] == "pip-audit"
    assert result["findings"][0]["rule_id"] == "PYSEC-1"


def test_security_scan_skips_audit_scanner_without_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr("ctx_engine.security_scan.shutil.which", lambda name: f"/bin/{name}")

    result = scan_security(tmp_path, scanner="npm-audit", strict=True)

    assert result["status"] == "warn"
    assert result["scanner_results"][0]["status"] == "skipped"
    assert not result["errors"]


def test_security_scan_cli_all_with_mocked_scanners(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("ctx_engine.security_scan.shutil.which", lambda name: f"/bin/{name}")

    def fake_run(command, timeout):
        scanner = Path(command[0]).name
        if scanner == "semgrep":
            return subprocess.CompletedProcess(command, 0, stdout='{"results":[]}', stderr="")
        if scanner == "gitleaks":
            return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")
        if scanner == "secretlint":
            return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")
        raise AssertionError(f"unexpected scanner command: {scanner}")

    monkeypatch.setattr("ctx_engine.security_scan._run_command", fake_run)

    assert main(["security-scan", str(tmp_path), "--all", "--strict"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "warn"
    assert len(out["scanner_results"]) == 5
    assert {item["scanner"] for item in out["scanner_results"] if item["status"] == "skipped"} == {"npm-audit", "pip-audit"}
