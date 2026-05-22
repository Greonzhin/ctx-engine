from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


SUPPORTED_STRUCTURAL_SEARCHERS = ("ast-grep",)


def _run_command(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def _ast_grep_command(path: Path, pattern: str, language: str | None = None) -> list[str]:
    command = ["ast-grep", "--json", "--pattern", pattern]
    if language:
        command.extend(["--lang", language])
    command.append(str(path))
    return command


def _line_from_range(item: dict[str, Any]) -> int | None:
    start = item.get("start") if isinstance(item.get("start"), dict) else {}
    if isinstance(start.get("line"), int):
        return start["line"]
    range_value = item.get("range") if isinstance(item.get("range"), dict) else {}
    range_start = range_value.get("start") if isinstance(range_value.get("start"), dict) else {}
    if isinstance(range_start.get("line"), int):
        return range_start["line"]
    if isinstance(item.get("line"), int):
        return item["line"]
    if isinstance(item.get("startLine"), int):
        return item["startLine"]
    return None


def _column_from_range(item: dict[str, Any]) -> int | None:
    start = item.get("start") if isinstance(item.get("start"), dict) else {}
    if isinstance(start.get("column"), int):
        return start["column"]
    range_value = item.get("range") if isinstance(item.get("range"), dict) else {}
    range_start = range_value.get("start") if isinstance(range_value.get("start"), dict) else {}
    if isinstance(range_start.get("column"), int):
        return range_start["column"]
    if isinstance(item.get("column"), int):
        return item["column"]
    if isinstance(item.get("startColumn"), int):
        return item["startColumn"]
    return None


def _match_text(item: dict[str, Any]) -> str:
    if isinstance(item.get("text"), str):
        return item["text"].strip()
    if isinstance(item.get("lines"), str):
        return item["lines"].strip()
    if isinstance(item.get("match"), str):
        return item["match"].strip()
    return ""


def _normalize_ast_grep(payload: object, language: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        records = payload.get("matches") or payload.get("results") or []
    elif isinstance(payload, list):
        records = payload
    else:
        records = []

    findings: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        path = item.get("file") or item.get("path") or item.get("filePath") or ""
        findings.append(
            {
                "engine": "ast-grep",
                "path": path,
                "line": _line_from_range(item),
                "column": _column_from_range(item),
                "match": _match_text(item),
                "language": item.get("language") or language or "",
            }
        )
        if len(findings) >= limit:
            break
    return findings


def _parse_ast_grep_output(stdout: str, stderr: str, language: str | None, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    text = stdout.strip() or stderr.strip()
    if not text:
        return [], []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"ast-grep returned non-JSON output: {exc}"]
    return _normalize_ast_grep(payload, language=language, limit=limit), []


def search_structural(
    path: str | Path = ".",
    pattern: str = "",
    language: str | None = None,
    strict: bool = False,
    timeout: float = 30.0,
    limit: int = 50,
) -> dict[str, Any]:
    root = Path(path).resolve()
    warnings: list[str] = []
    errors: list[str] = []
    findings: list[dict[str, Any]] = []

    if not pattern.strip():
        errors.append("pattern is required")
        return {
            "status": "fail",
            "path": str(root),
            "engine": "ast-grep",
            "pattern": pattern,
            "language": language or "",
            "command_available": shutil.which("ast-grep") is not None,
            "findings": findings,
            "warnings": warnings,
            "errors": errors,
        }

    command_available = shutil.which("ast-grep") is not None
    if not command_available:
        message = "ast-grep command is not available"
        warnings.append(message)
        if strict:
            errors.append(message)
        return {
            "status": "fail" if errors else "warn",
            "path": str(root),
            "engine": "ast-grep",
            "pattern": pattern,
            "language": language or "",
            "command_available": False,
            "findings": findings,
            "warnings": warnings,
            "errors": errors,
        }

    command = _ast_grep_command(root, pattern, language)
    try:
        completed = _run_command(command, timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = f"ast-grep failed to run: {exc}"
        warnings.append(message)
        errors.append(message)
        return {
            "status": "fail",
            "path": str(root),
            "engine": "ast-grep",
            "pattern": pattern,
            "language": language or "",
            "command_available": True,
            "command": command,
            "findings": findings,
            "warnings": warnings,
            "errors": errors,
        }

    findings, parse_warnings = _parse_ast_grep_output(completed.stdout, completed.stderr, language, limit)
    warnings.extend(parse_warnings)
    if completed.returncode not in (0, 1):
        errors.append(f"ast-grep returned exit code {completed.returncode}")

    status = "pass"
    if errors:
        status = "fail"
    elif warnings:
        status = "warn"
    elif findings:
        status = "findings"

    return {
        "status": status,
        "path": str(root),
        "engine": "ast-grep",
        "pattern": pattern,
        "language": language or "",
        "command_available": True,
        "command": command,
        "returncode": completed.returncode,
        "findings": findings,
        "warnings": sorted(warnings),
        "errors": sorted(errors),
    }
