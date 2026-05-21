from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


SUPPORTED_SCANNERS = ("semgrep", "gitleaks", "secretlint", "npm-audit", "pip-audit")
_SCANNER_BINARIES = {
    "semgrep": "semgrep",
    "gitleaks": "gitleaks",
    "secretlint": "secretlint",
    "npm-audit": "npm",
    "pip-audit": "pip-audit",
}


def _run_command(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def _semgrep_command(path: Path) -> list[str]:
    return ["semgrep", "scan", "--json", "--quiet", str(path)]


def _gitleaks_command(path: Path) -> list[str]:
    return ["gitleaks", "detect", "--no-git", "--redact", "--report-format", "json", "--source", str(path)]


def _secretlint_command(path: Path) -> list[str]:
    return ["secretlint", "--format", "json", str(path)]


def _npm_audit_command(path: Path) -> list[str] | None:
    if not (path / "package.json").exists():
        return None
    return ["npm", "audit", "--json", "--prefix", str(path)]


def _pip_audit_command(path: Path) -> list[str] | None:
    candidates = [
        path / "requirements.txt",
        path / "requirements-dev.txt",
        path / "dev-requirements.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return ["pip-audit", "--format", "json", "-r", str(candidate)]
    return None


def _scanner_command(scanner: str, path: Path) -> tuple[list[str] | None, str | None]:
    if scanner == "semgrep":
        return _semgrep_command(path), None
    if scanner == "gitleaks":
        return _gitleaks_command(path), None
    if scanner == "secretlint":
        return _secretlint_command(path), None
    if scanner == "npm-audit":
        command = _npm_audit_command(path)
        return command, None if command else "npm-audit skipped: package.json not found"
    if scanner == "pip-audit":
        command = _pip_audit_command(path)
        return command, None if command else "pip-audit skipped: requirements file not found"
    return None, f"unsupported scanner: {scanner}"


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


def _normalize_secretlint(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        records = payload.get("results") or payload.get("files") or []
    elif isinstance(payload, list):
        records = payload
    else:
        return []

    findings: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        path = record.get("filePath") or record.get("path") or ""
        messages = record.get("messages") or []
        for message in messages:
            if not isinstance(message, dict):
                continue
            findings.append(
                {
                    "scanner": "secretlint",
                    "rule_id": message.get("ruleId") or message.get("rule") or "",
                    "message": message.get("message") or "",
                    "path": path,
                    "line": message.get("line"),
                    "severity": str(message.get("severity") or ""),
                }
            )
    return findings


def _normalize_npm_audit(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    findings: list[dict[str, Any]] = []
    vulnerabilities = payload.get("vulnerabilities")
    if isinstance(vulnerabilities, dict):
        for package_name, item in vulnerabilities.items():
            if not isinstance(item, dict):
                continue
            via = item.get("via") if isinstance(item.get("via"), list) else []
            advisory = next((entry for entry in via if isinstance(entry, dict)), {})
            title = advisory.get("title") if isinstance(advisory, dict) else None
            rule_id = advisory.get("source") if isinstance(advisory, dict) else None
            findings.append(
                {
                    "scanner": "npm-audit",
                    "rule_id": str(rule_id or package_name),
                    "message": str(title or item.get("name") or package_name),
                    "path": "package.json",
                    "line": None,
                    "severity": item.get("severity") or "",
                }
            )
    advisories = payload.get("advisories")
    if isinstance(advisories, dict):
        for advisory_id, item in advisories.items():
            if not isinstance(item, dict):
                continue
            findings.append(
                {
                    "scanner": "npm-audit",
                    "rule_id": str(advisory_id),
                    "message": item.get("title") or item.get("module_name") or "",
                    "path": "package.json",
                    "line": None,
                    "severity": item.get("severity") or "",
                }
            )
    return findings


def _normalize_pip_audit(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        dependencies = payload.get("dependencies") or []
    elif isinstance(payload, list):
        dependencies = payload
    else:
        return []

    findings: list[dict[str, Any]] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        name = dependency.get("name") or ""
        for vuln in dependency.get("vulns") or []:
            if not isinstance(vuln, dict):
                continue
            aliases = vuln.get("aliases") if isinstance(vuln.get("aliases"), list) else []
            findings.append(
                {
                    "scanner": "pip-audit",
                    "rule_id": vuln.get("id") or (aliases[0] if aliases else ""),
                    "message": vuln.get("description") or name,
                    "path": "requirements.txt",
                    "line": None,
                    "severity": vuln.get("severity") or "",
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
    if scanner == "secretlint":
        return _normalize_secretlint(payload), []
    if scanner == "npm-audit":
        return _normalize_npm_audit(payload), []
    if scanner == "pip-audit":
        return _normalize_pip_audit(payload), []
    return [], [f"unsupported scanner: {scanner}"]


def scan_security(
    path: str | Path = ".",
    scanner: str | None = None,
    all_scanners: bool = False,
    strict: bool = False,
    timeout: float = 60.0,
) -> dict[str, Any]:
    root = Path(path).resolve()
    selected = list(SUPPORTED_SCANNERS) if all_scanners else [scanner or "semgrep"]
    scanner_results: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    for scanner_name in selected:
        if scanner_name not in SUPPORTED_SCANNERS:
            errors.append(f"unsupported scanner: {scanner_name}")
            scanner_results.append(
                {
                    "scanner": scanner_name,
                    "status": "error",
                    "command_available": False,
                    "findings_count": 0,
                    "warnings": [f"unsupported scanner: {scanner_name}"],
                }
            )
            continue

        binary = _SCANNER_BINARIES[scanner_name]
        command_available = shutil.which(binary) is not None
        if not command_available:
            message = f"{scanner_name} command is not available"
            warnings.append(message)
            scanner_results.append(
                {
                    "scanner": scanner_name,
                    "status": "unavailable",
                    "command_available": False,
                    "findings_count": 0,
                    "warnings": [message],
                }
            )
            if strict:
                errors.append(message)
            continue

        command, skip_reason = _scanner_command(scanner_name, root)
        if command is None:
            if skip_reason:
                warnings.append(skip_reason)
            scanner_results.append(
                {
                    "scanner": scanner_name,
                    "status": "skipped",
                    "command_available": True,
                    "findings_count": 0,
                    "warnings": [skip_reason] if skip_reason else [],
                }
            )
            continue

        try:
            completed = _run_command(command, timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            message = f"{scanner_name} failed to run: {exc}"
            warnings.append(message)
            errors.append(message)
            scanner_results.append(
                {
                    "scanner": scanner_name,
                    "status": "error",
                    "command_available": True,
                    "findings_count": 0,
                    "warnings": [message],
                }
            )
            continue

        normalized, parse_warnings = _parse_json_output(scanner_name, completed.stdout, completed.stderr)
        findings.extend(normalized)
        warnings.extend(parse_warnings)

        # These tools may exit 1 when findings are present.
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
