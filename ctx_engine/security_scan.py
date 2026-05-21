from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


SUPPORTED_SCANNERS = ("semgrep", "gitleaks")


def _run_command(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def _semgrep_command(path: Path) -> list[str]:
    return ["semgrep", "scan", "--json", "--quiet", str(path)]


def _gitleaks_command(path: Path) -> list[str]:
    return ["gitleaks", "detect", "--no-git", "--redact", "--report-format", "json", "--source", str(path)]


def _normalize_semgrep(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    findings: list[dict[str, Any]] = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        start = item.get("start") if isinstance(item.get("start"), dict) else {}
        findings.append(
            {
                "scanner": "semgrep",
                "rule_id": item.get("check_id") or "",
                "message": extra.get("message") or "",
                "path": item.get("path") or "",
                "line": start.get("line"),
                "severity": extra.get("severity") or "",
            }
        )
    return findings


def _normalize_gitleaks(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    findings: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        findings.append(
            {
                "scanner": "gitleaks",
                "rule_id": item.get("RuleID") or item.get("Rule") or "",
                "message": item.get("Description") or item.get("Match") or "",
                "path": item.get("File") or "",
                "line": item.get("StartLine"),
                "severity": item.get("Severity") or "",
            }
        )
    return findings


def _parse_json_output(scanner: str, stdout: str, stderr: str) -> tuple[list[dict[str, Any]], list[str]]:
    text = stdout.strip() or stderr.strip()
    if not text:
        return [], []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"{scanner} returned non-JSON output: {exc}"]
    if scanner == "semgrep":
        return _normalize_semgrep(payload), []
    if scanner == "gitleaks":
        return _normalize_gitleaks(payload), []
    return [], [f"unsupported scanner: {scanner}"]


def scan_security(path: str | Path = ".", scanner: str | None = None, all_scanners: bool = False, strict: bool = False, timeout: float = 60.0) -> dict[str, Any]:
    root = Path(path).resolve()
    selected = list(SUPPORTED_SCANNERS) if all_scanners else [scanner or "semgrep"]
    scanner_results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    for scanner_name in selected:
        if scanner_name not in SUPPORTED_SCANNERS:
            errors.append(f"unsupported scanner: {scanner_name}")
            scanner_results.append({"scanner": scanner_name, "status": "error", "command_available": False, "findings_count": 0, "warnings": [f"unsupported scanner: {scanner_name}"]})
            continue

        command_available = shutil.which(scanner_name) is not None
        if not command_available:
            message = f"{scanner_name} command is not available"
            warnings.append(message)
            scanner_results.append({"scanner": scanner_name, "status": "unavailable", "command_available": False, "findings_count": 0, "warnings": [message]})
            if strict:
                errors.append(message)
            continue

        command = _semgrep_command(root) if scanner_name == "semgrep" else _gitleaks_command(root)
        try:
            completed = _run_command(command, timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            message = f"{scanner_name} failed to run: {exc}"
            warnings.append(message)
            errors.append(message)
            scanner_results.append({"scanner": scanner_name, "status": "error", "command_available": True, "findings_count": 0, "warnings": [message]})
            continue

        normalized, parse_warnings = _parse_json_output(scanner_name, completed.stdout, completed.stderr)
        findings.extend(normalized)
        warnings.extend(parse_warnings)

        # Semgrep exits 1 for findings or fatal errors depending on context; Gitleaks exits 1 for leaks.
        scanner_status = "pass"
        if normalized:
            scanner_status = "findings"
        elif completed.returncode not in (0, 1):
            scanner_status = "error"
            errors.append(f"{scanner_name} returned exit code {completed.returncode}")

        scanner_results.append(
            {
                "scanner": scanner_name,
                "status": scanner_status,
                "command_available": True,
                "command": command,
                "returncode": completed.returncode,
                "findings_count": len(normalized),
                "warnings": parse_warnings,
            }
        )

    if findings and strict:
        errors.append("security scanner findings detected")

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
        "scanner_results": scanner_results,
        "findings": findings,
        "warnings": sorted(warnings),
        "errors": sorted(errors),
        "command_available": all(result.get("command_available") for result in scanner_results) if scanner_results else False,
    }
