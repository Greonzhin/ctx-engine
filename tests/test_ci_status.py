from __future__ import annotations

import json
import subprocess

from ctx_engine.ci_status import ci_status
from ctx_engine.cli import main


WORKFLOW = """name: ci

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  test:
    name: python-quality-gate
    runs-on: windows-latest
    steps:
      - run: python -m pytest -q
  docker:
    name: docker-runtime-smoke
    runs-on: ubuntu-latest
    steps:
      - run: ./scripts/docker_smoke.ps1
"""


def test_ci_status_reads_github_actions_workflows(tmp_path):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(WORKFLOW, encoding="utf-8")

    result = ci_status(tmp_path)

    assert result["status"] == "ok"
    assert result["diagnosis"]["category"] == "ci-runtime-unchecked"
    assert result["workflow_count"] == 1
    assert result["workflows"][0]["name"] == "ci"
    assert result["workflows"][0]["triggers"] == ["pull_request", "push", "workflow_dispatch"]
    assert {job["name"] for job in result["workflows"][0]["jobs"]} == {"python-quality-gate", "docker-runtime-smoke"}


def test_ci_status_missing_workflows_warns_or_fails_strict(tmp_path):
    non_strict = ci_status(tmp_path, strict=False)
    strict = ci_status(tmp_path, strict=True)

    assert non_strict["status"] == "warn"
    assert strict["status"] == "fail"
    assert "no GitHub Actions workflow files found" in strict["errors"]


def test_ci_status_run_missing_gh_warns_non_strict(tmp_path, monkeypatch):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(WORKFLOW, encoding="utf-8")
    monkeypatch.setattr("ctx_engine.ci_status.shutil.which", lambda _name: None)

    result = ci_status(tmp_path, run=True, strict=False)

    assert result["status"] == "warn"
    assert result["diagnosis"]["category"] == "ci-runtime-unavailable"
    assert result["runtime"]["checked"] is True
    assert result["runtime"]["command_available"] is False
    assert "gh command is not available" in result["warnings"]


def test_ci_status_normalizes_gh_run_json_and_strict_failure(tmp_path, monkeypatch):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(WORKFLOW, encoding="utf-8")
    monkeypatch.setattr("ctx_engine.ci_status.shutil.which", lambda name: f"/bin/{name}")
    payload = [
        {
            "databaseId": 123,
            "workflowName": "ci",
            "displayTitle": "bad change",
            "headBranch": "main",
            "status": "completed",
            "conclusion": "failure",
            "createdAt": "2026-05-22T12:00:00Z",
            "url": "https://github.example/run/123",
        }
    ]

    jobs_payload = {
        "jobs": [
            {
                "databaseId": 456,
                "name": "python-quality-gate",
                "status": "completed",
                "conclusion": "failure",
                "startedAt": "2026-05-22T12:00:01Z",
                "completedAt": "2026-05-22T12:00:03Z",
                "url": "https://github.example/job/456",
                "steps": [],
            }
        ]
    }

    def fake_run(command, cwd, timeout):
        if command[:3] == ["gh", "run", "view"]:
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(jobs_payload), stderr="")
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("ctx_engine.ci_status._run_command", fake_run)

    result = ci_status(tmp_path, run=True, strict=True)

    assert result["status"] == "fail"
    assert result["diagnosis"]["category"] == "ci-failed"
    assert result["runtime"]["runs"][0]["database_id"] == 123
    assert result["runtime"]["failing_runs"][0]["display_title"] == "bad change"
    assert result["runtime"]["job_diagnostics"][0]["empty_step_jobs"][0]["name"] == "python-quality-gate"
    assert result["runtime"]["empty_step_failures"][0]["step_count"] == 0
    assert "GitHub Actions has failing completed runs" in result["errors"]
    assert any("zero recorded steps" in warning for warning in result["warnings"])


def test_ci_status_cli(tmp_path, capsys):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(WORKFLOW, encoding="utf-8")

    assert main(["ci", "status", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["diagnosis"]["category"] == "ci-runtime-unchecked"
    assert out["workflow_count"] == 1


def test_ci_status_diagnoses_zero_step_failures_without_strict(tmp_path, monkeypatch):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(WORKFLOW, encoding="utf-8")
    monkeypatch.setattr("ctx_engine.ci_status.shutil.which", lambda name: f"/bin/{name}")
    runs_payload = [
        {
            "databaseId": 999,
            "workflowName": "ci",
            "displayTitle": "platform issue",
            "headBranch": "main",
            "status": "completed",
            "conclusion": "failure",
            "createdAt": "2026-05-22T12:00:00Z",
            "url": "https://github.example/run/999",
        }
    ]
    jobs_payload = {
        "jobs": [
            {
                "databaseId": 1000,
                "name": "docker-runtime-smoke",
                "status": "completed",
                "conclusion": "failure",
                "startedAt": "2026-05-22T12:00:01Z",
                "completedAt": "2026-05-22T12:00:02Z",
                "url": "https://github.example/job/1000",
                "steps": [],
            }
        ]
    }

    def fake_run(command, cwd, timeout):
        if command[:3] == ["gh", "run", "view"]:
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(jobs_payload), stderr="")
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(runs_payload), stderr="")

    monkeypatch.setattr("ctx_engine.ci_status._run_command", fake_run)

    result = ci_status(tmp_path, run=True, strict=False)

    assert result["status"] == "warn"
    assert result["diagnosis"]["category"] == "runner-platform-failure"
    assert "before any workflow steps" in result["diagnosis"]["summary"]
    assert result["diagnosis"]["recommended_actions"]
