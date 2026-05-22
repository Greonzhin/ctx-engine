from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .config import rules_path
from .mcp_lint import lint_gateway_tools
from .providers.egress import EgressProvider
from .rules_check import check_rules_drift


POLICY_IDS = (
    "rules-source-present",
    "single-mcp-endpoint",
    "no-downstream-mcp",
    "no-shell-tools",
    "no-write-tools",
    "private-code-local",
    "private-docs-local",
    "context7-public-docs-only",
    "redact-secrets",
    "mcp-registry-allowlist",
    "generated-rules-in-sync",
    "context7-egress-observable",
)

_SECTION_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*$")
_KEY_VALUE_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.+?)\s*$")


def load_rules_flags(root: str | Path = ".") -> dict[str, Any]:
    path = rules_path(Path(root).resolve())
    if not path.exists():
        return {"status": "missing", "path": str(path), "flags": {}}
    flags: dict[str, Any] = {}
    section: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("- "):
            continue
        section_match = _SECTION_RE.match(line)
        if section_match:
            section = section_match.group(1)
            continue
        match = _KEY_VALUE_RE.match(line)
        if not match:
            continue
        key, raw_value = match.group(1), match.group(2)
        value: object = raw_value
        lowered = raw_value.lower()
        if lowered == "true":
            value = True
        elif lowered == "false":
            value = False
        dotted = f"{section}.{key}" if section else key
        flags[dotted] = value
    return {"status": "ok", "path": str(path), "flags": flags}


def evaluate_policy(root: str | Path = ".", mode: str = "safe") -> dict[str, Any]:
    workspace = Path(root).resolve()
    rules = load_rules_flags(workspace)
    flags = dict(rules.get("flags") or {})
    mcp_lint = lint_gateway_tools(mode)
    rules_drift = check_rules_drift(workspace)
    egress = EgressProvider().summary_last_24h(provider="context7")

    checks = [
        _check("rules-source-present", rules["status"] == "ok", f"rules_path={rules['path']}"),
        _flag("single-mcp-endpoint", flags, "gateway.single_mcp_endpoint"),
        _flag("no-downstream-mcp", flags, "gateway.no_downstream_mcp_exposure"),
        _flag("no-shell-tools", flags, "gateway.no_shell_tools"),
        _flag("no-write-tools", flags, "gateway.no_write_tools"),
        _flag("private-code-local", flags, "privacy.private_code_stays_local"),
        _flag("private-docs-local", flags, "privacy.private_docs_stay_local"),
        _flag("context7-public-docs-only", flags, "privacy.context7_public_docs_only"),
        _flag("redact-secrets", flags, "privacy.redact_secrets"),
        _check(
            "mcp-registry-allowlist",
            mcp_lint["status"] == "pass",
            f"mcp_lint_status={mcp_lint['status']}; tool_count={mcp_lint.get('tool_count')}",
            errors=list(mcp_lint.get("errors") or []),
            warnings=list(mcp_lint.get("warnings") or []),
        ),
        _check(
            "generated-rules-in-sync",
            rules_drift["status"] == "ok",
            f"rules_check_status={rules_drift['status']}",
            errors=list(rules_drift.get("errors") or []),
        ),
        _check(
            "context7-egress-observable",
            float(egress.get("context7_error_ratio_24h") or 0.0) <= 0.5,
            f"events_24h={egress.get('total')}; error_ratio={egress.get('context7_error_ratio_24h')}",
        ),
    ]

    failed = [item for item in checks if item["status"] == "fail"]
    warnings = [warning for item in checks for warning in item.get("warnings", [])]
    return {
        "status": "pass" if not failed else "fail",
        "workspace_path": str(workspace),
        "mode": mode,
        "policy_count": len(checks),
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": checks,
        "warnings": sorted(set(warnings)),
    }


def _flag(policy_id: str, flags: dict[str, Any], key: str) -> dict[str, Any]:
    value = flags.get(key)
    return _check(policy_id, value is True, f"{key}={value!r}")


def _check(
    policy_id: str,
    passed: bool,
    evidence: str,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": policy_id,
        "status": "pass" if passed else "fail",
        "evidence": [evidence],
        "errors": errors or ([] if passed else [evidence]),
        "warnings": warnings or [],
    }
