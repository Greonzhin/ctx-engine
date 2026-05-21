from __future__ import annotations

import subprocess

import pytest

from ctx_engine.inspector_smoke import inspector_smoke


def test_inspector_smoke_reports_unavailable_when_npx_missing(monkeypatch):
    monkeypatch.setattr("ctx_engine.inspector_smoke.shutil.which", lambda _: None)
    result = inspector_smoke(run=False)
    assert result["status"] == "unavailable"
    assert result["error"] == "npx not found on PATH"


def test_inspector_smoke_run_success(monkeypatch):
    monkeypatch.setattr("ctx_engine.inspector_smoke.shutil.which", lambda _: "C:/tools/npx.cmd")

    class Dummy:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr("ctx_engine.inspector_smoke.subprocess.run", lambda *_, **__: Dummy())
    result = inspector_smoke(run=True)
    assert result["status"] == "pass"
    assert result["returncode"] == 0


def test_inspector_smoke_run_failure(monkeypatch):
    monkeypatch.setattr("ctx_engine.inspector_smoke.shutil.which", lambda _: "C:/tools/npx.cmd")

    class Dummy:
        returncode = 1
        stdout = ""
        stderr = "failed"

    monkeypatch.setattr("ctx_engine.inspector_smoke.subprocess.run", lambda *_, **__: Dummy())
    result = inspector_smoke(run=True)
    assert result["status"] == "fail"
    assert result["returncode"] == 1


def test_inspector_smoke_run_exception(monkeypatch):
    monkeypatch.setattr("ctx_engine.inspector_smoke.shutil.which", lambda _: "C:/tools/npx.cmd")

    def raise_timeout(*_, **__):
        raise subprocess.TimeoutExpired(cmd="npx", timeout=1)

    monkeypatch.setattr("ctx_engine.inspector_smoke.subprocess.run", raise_timeout)
    result = inspector_smoke(run=True)
    assert result["status"] == "error"
    assert "TimeoutExpired" in result["error"]
