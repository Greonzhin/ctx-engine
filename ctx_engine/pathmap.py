from __future__ import annotations

import os
import re
from pathlib import Path

WINDOWS_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")
WSL_RE = re.compile(r"^/mnt/([a-zA-Z])/(.*)$")


def map_path(path: str, workspace_root: str | None = None) -> dict[str, object]:
    raw = path.strip().strip('"')
    result: dict[str, object] = {
        "input": raw,
        "exists": Path(raw).exists(),
        "windows": None,
        "wsl": None,
        "docker": None,
        "notes": [],
    }
    win = WINDOWS_DRIVE_RE.match(raw)
    if win:
        drive = win.group(1).lower()
        rest = win.group(2).replace("\\", "/")
        result["windows"] = raw
        result["wsl"] = f"/mnt/{drive}/{rest}"
    else:
        wsl = WSL_RE.match(raw)
        if wsl:
            drive = wsl.group(1).upper()
            rest = wsl.group(2).replace("/", "\\")
            result["wsl"] = raw
            result["windows"] = f"{drive}:\\{rest}"
        elif raw.startswith("/workspace"):
            result["docker"] = raw

    root = workspace_root or os.environ.get("CTX_ENGINE_WORKSPACE_ROOT")
    if root:
        try:
            target = Path(raw).resolve()
            base = Path(root).resolve()
            rel = target.relative_to(base).as_posix()
            result["docker"] = "/workspace" if rel == "." else f"/workspace/{rel}"
        except Exception:
            pass
    if any(ch in raw for ch in ("'", "ı", "İ", "ğ", "Ğ", "ş", "Ş", "ö", "Ö", "ü", "Ü", "ç", "Ç")):
        result["notes"].append("unicode-or-apostrophe-safe")
    if "Drive" in raw or "Google Drive" in raw:
        result["notes"].append("synced-folder: expect occasional file lock latency")
    return result


def check_paths(path: str | None = None) -> dict[str, object]:
    target = path or os.getcwd()
    mapped = map_path(target, target if Path(target).exists() else None)
    return {
        "ok": True,
        "cwd": os.getcwd(),
        "mapping": mapped,
        "line_endings": "crlf-compatible",
    }
