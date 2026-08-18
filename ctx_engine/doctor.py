from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from .config import DEFAULT_ENDPOINT, data_dir
from .db import sqlite_status
from .pathmap import check_paths
from .providers.egress import EgressProvider
from .security.net import urlopen_checked


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0


def _http_health(endpoint: str) -> dict[str, object]:
    base = endpoint.rsplit("/mcp", 1)[0]
    try:
        with urlopen_checked(f"{base}/health", timeout=3.0) as response:
            return {"reachable": True, "status": response.status}

    except urllib.error.URLError as exc:
        return {"reachable": False, "warning": type(exc.reason).__name__ if hasattr(exc, "reason") else str(exc)}
    except Exception as exc:
        return {"reachable": False, "warning": type(exc).__name__}


def _docker_daemon_status() -> dict[str, object]:
    if not shutil.which("docker"):
        return {"reachable": False, "server_version": None, "context": None, "warning": "Docker CLI not found on PATH."}

    context: str | None = None
    try:
        context_result = subprocess.run(
            ["docker", "context", "show"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if context_result.returncode == 0:
            context = context_result.stdout.strip() or None
    except Exception:
        context = None

    try:
        version_result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except Exception as exc:
        return {"reachable": False, "server_version": None, "context": context, "warning": type(exc).__name__}

    if version_result.returncode != 0:
        warning = (version_result.stderr or version_result.stdout or "Docker daemon is not reachable.").strip()
        return {"reachable": False, "server_version": None, "context": context, "warning": warning}

    server_version = version_result.stdout.strip() or None
    return {"reachable": bool(server_version), "server_version": server_version, "context": context, "warning": None}


def doctor_status(workspace_path: str | Path = ".", endpoint: str = DEFAULT_ENDPOINT) -> dict[str, object]:
    workspace = Path(workspace_path).resolve()
    dd = data_dir()
    dd.mkdir(parents=True, exist_ok=True)
    generated = {
        "AGENTS.md": (workspace / "AGENTS.md").exists(),
        "CLAUDE.md": (workspace / "CLAUDE.md").exists(),
        "GEMINI.md": (workspace / "GEMINI.md").exists(),
        ".codex/config.toml": (workspace / ".codex" / "config.toml").exists(),
        ".mcp.json": (workspace / ".mcp.json").exists(),
        ".gemini/settings.json": (workspace / ".gemini" / "settings.json").exists(),
    }
    docker_cli = bool(shutil.which("docker"))
    docker_daemon = _docker_daemon_status()
    checks = {
        "python": sys.version.split()[0],
        "sqlite": sqlite_status(),
        "data_dir_writable": dd.exists() and dd.is_dir(),
        "docker": docker_cli,
        "docker_daemon": docker_daemon,
        "mcp_health": _http_health(endpoint),
        "port_7331_free": _port_free("127.0.0.1", 7331),
        "path_mapping": check_paths(str(workspace)),
        "generated_files": generated,
        "egress_last_24h": EgressProvider().summary_last_24h(provider="context7"),
    }
    warnings = []
    if not checks["docker"]:
        warnings.append("Docker CLI not found on PATH; Dockerfile is still generated.")
    elif not docker_daemon["reachable"]:
        warnings.append(f"Docker daemon is not reachable: {docker_daemon.get('warning')}")
    if not checks["mcp_health"]["reachable"]:
        warnings.append("MCP server is not currently running.")
    ok = bool(checks["sqlite"]["fts5"]) and bool(checks["data_dir_writable"])
    return {"status": "healthy" if ok else "unhealthy", "checks": checks, "warnings": warnings}
