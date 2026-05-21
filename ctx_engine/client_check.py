from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .client_adapters import ClaudeAdapter, CodexAdapter, GeminiAdapter, GenericAdapter


def client_adapters() -> dict[str, object]:
    return {
        "codex": CodexAdapter(),
        "claude": ClaudeAdapter(),
        "gemini": GeminiAdapter(),
        "generic": GenericAdapter(),
    }


def _clip(text: str, limit: int = 1200) -> str:
    value = text.strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "...<truncated>"


def _run_command(command: list[str], cwd: Path, timeout: float) -> dict[str, object]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": _clip(completed.stdout),
            "stderr": _clip(completed.stderr),
            "error": None,
        }
    except Exception as exc:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _manual_checks(client_id: str, endpoint: str | None) -> list[dict[str, object]]:
    target = endpoint or "http://127.0.0.1:7331/mcp"
    if client_id == "codex":
        return [
            {
                "name": "codex_mcp_ui",
                "instruction": "Open Codex chat and run /mcp to verify ctx-engine appears and is reachable.",
                "expected": f"ctx-engine entry points to {target}",
            }
        ]
    if client_id == "claude":
        return [
            {
                "name": "claude_mcp_get",
                "command": "claude mcp get ctx-engine",
                "expected": f"Connected and endpoint {target}",
            }
        ]
    if client_id == "gemini":
        return [
            {
                "name": "gemini_mcp_list",
                "command": "gemini mcp list",
                "expected": f"ctx-engine listed with endpoint {target}",
            }
        ]
    return []


def _client_probe(client_id: str, root: Path, endpoint: str | None, run: bool, timeout: float) -> dict[str, object]:
    executable = shutil.which(client_id)
    probe: dict[str, object] = {
        "available": executable is not None,
        "executable": executable,
        "version": None,
        "connection": None,
        "warnings": [],
    }
    if not run:
        return probe
    if not executable:
        if client_id != "generic":
            probe["warnings"] = [f"{client_id} CLI not found on PATH"]
        return probe

    command = str(executable)
    version = _run_command([command, "--version"], root, timeout)
    probe["version"] = version
    warnings = list(probe["warnings"])
    if version["error"] or version["returncode"] not in {0, None}:
        warnings.append(f"{client_id} --version did not complete cleanly")

    if client_id == "claude":
        connection = _run_command([command, "mcp", "get", "ctx-engine"], root, timeout)
        output = f"{connection.get('stdout', '')}\n{connection.get('stderr', '')}"
        connected = "Connected" in output and (endpoint is None or endpoint in output)
        connection["connected"] = connected
        probe["connection"] = connection
        if not connected:
            warnings.append("Claude did not report ctx-engine as connected")
    elif client_id == "gemini":
        connection = _run_command([command, "mcp", "list"], root, timeout)
        output = f"{connection.get('stdout', '')}\n{connection.get('stderr', '')}"
        connected = "ctx-engine" in output and (endpoint is None or endpoint in output)
        connection["connected"] = connected
        probe["connection"] = connection
        if not connected:
            warnings.append("Gemini did not report ctx-engine in MCP list")
    else:
        probe["connection"] = {
            "connected": None,
            "note": "No non-interactive ctx-engine MCP status probe is configured for this client.",
        }

    probe["warnings"] = warnings
    return probe


def check_clients(
    workspace_path: str | Path = ".",
    adapter: str | None = None,
    run: bool = False,
    timeout: float = 8.0,
) -> dict[str, Any]:
    root = Path(workspace_path).resolve()
    adapters = client_adapters()
    selected = {adapter: adapters[adapter]} if adapter else adapters
    clients: dict[str, dict[str, object]] = {}
    warnings: list[str] = []

    for client_id, adapter_instance in selected.items():
        adapter_status = adapter_instance.status(root)
        endpoint = adapter_status.get("configured_endpoint") or adapter_status.get("rules_endpoint")
        cli_status = None
        if client_id != "generic":
            cli_status = _client_probe(client_id, root, str(endpoint) if endpoint else None, run, timeout)
            warnings.extend(str(item) for item in cli_status.get("warnings", []))
        if not adapter_status.get("installed"):
            warnings.append(f"{client_id} adapter files are not installed")
        if adapter_status.get("endpoint_matches_rules") is False:
            warnings.append(f"{client_id} endpoint does not match .ctx-engine/rules.yaml")
        clients[client_id] = {
            "adapter": adapter_status,
            "cli": cli_status,
            "manual_checks": _manual_checks(client_id, str(endpoint) if endpoint else None),
        }

    installed_ok = all(bool(item["adapter"].get("installed")) for item in clients.values())
    endpoints_ok = all(item["adapter"].get("endpoint_matches_rules") is not False for item in clients.values())
    status = "ok" if installed_ok and endpoints_ok and not warnings else "needs_attention"
    return {
        "status": status,
        "workspace_path": str(root),
        "ran_client_commands": run,
        "clients": clients,
        "warnings": sorted(set(warnings)),
    }
