from __future__ import annotations

import subprocess

from ctx_engine.doctor import doctor_status


def test_doctor_reports_healthy(tmp_path):
    status = doctor_status(tmp_path)
    assert status["status"] == "healthy"
    assert status["checks"]["sqlite"]["fts5"] is True
    assert "docker_daemon" in status["checks"]
    assert "reachable" in status["checks"]["docker_daemon"]


def test_doctor_reports_docker_daemon_warning_when_cli_exists_but_daemon_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("ctx_engine.doctor.shutil.which", lambda name: "C:/tools/docker.exe" if name == "docker" else None)

    def fake_run(args, **kwargs):
        if args[:3] == ["docker", "context", "show"]:
            return subprocess.CompletedProcess(args, 0, stdout="desktop-linux\n", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="daemon unavailable")

    monkeypatch.setattr("ctx_engine.doctor.subprocess.run", fake_run)

    status = doctor_status(tmp_path)

    assert status["checks"]["docker"] is True
    assert status["checks"]["docker_daemon"] == {
        "reachable": False,
        "server_version": None,
        "context": "desktop-linux",
        "warning": "daemon unavailable",
    }
    assert "Docker daemon is not reachable: daemon unavailable" in status["warnings"]
