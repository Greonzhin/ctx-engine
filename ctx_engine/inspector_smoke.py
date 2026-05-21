from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import DEFAULT_ENDPOINT


def _clip(text: str, limit: int = 2000) -> str:
    value = text.strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "...<truncated>"


def inspector_smoke(
    endpoint: str = DEFAULT_ENDPOINT,
    run: bool = False,
    timeout: float = 20.0,
) -> dict[str, Any]:
    executable = shutil.which("npx")
    base_command = [
        "npx",
        "-y",
        "@modelcontextprotocol/inspector",
        "--cli",
        endpoint,
        "--transport",
        "http",
        "--method",
        "tools/list",
    ]
    command = list(base_command)
    if not run:
        return {
            "status": "ready" if executable else "unavailable",
            "endpoint": endpoint,
            "run": False,
            "executable": executable,
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": None if executable else "npx not found on PATH",
            "warnings": [],
        }
    if not executable:
        return {
            "status": "unavailable",
            "endpoint": endpoint,
            "run": True,
            "executable": None,
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": "npx not found on PATH",
            "warnings": [],
        }
    try:
        run_command = list(base_command)
        exe_suffix = Path(executable).suffix.lower()
        if exe_suffix in {".cmd", ".bat"}:
            run_command = ["cmd", "/c", executable, *base_command[1:]]
        else:
            run_command[0] = executable
        completed = subprocess.run(
            run_command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {
            "status": "error",
            "endpoint": endpoint,
            "run": True,
            "executable": executable,
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "error": f"{type(exc).__name__}: {exc}",
            "warnings": [],
        }
    stdout = _clip(completed.stdout)
    stderr = _clip(completed.stderr)
    warnings: list[str] = []
    has_tools_output = False
    try:
        parsed = json.loads(completed.stdout)
        has_tools_output = isinstance(parsed, dict) and isinstance(parsed.get("tools"), list)
    except Exception:
        has_tools_output = False
    ok = completed.returncode == 0
    if not ok and has_tools_output:
        ok = True
        warnings.append("Inspector returned tools output but exited with a non-zero code.")
    if "UV_HANDLE_CLOSING" in completed.stderr or "Assertion failed" in completed.stderr:
        warnings.append("Observed Node/libuv closing assertion in inspector process output.")
    return {
        "status": "pass" if ok else "fail",
        "endpoint": endpoint,
        "run": True,
        "executable": executable,
        "command": command,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "error": None,
        "warnings": warnings,
    }
