from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.config import ensure_project_config
from ctx_engine.policy import evaluate_policy, load_rules_flags
from ctx_engine.client_adapters import ClaudeAdapter, CodexAdapter, GeminiAdapter, GenericAdapter


def _install_rules_and_clients(root):
    ensure_project_config(root)
    for adapter in (CodexAdapter(), ClaudeAdapter(), GeminiAdapter(), GenericAdapter()):
        adapter.install(root)


def test_policy_loads_rules_flags(tmp_path):
    _install_rules_and_clients(tmp_path)

    result = load_rules_flags(tmp_path)

    assert result["status"] == "ok"
    assert result["flags"]["gateway.no_shell_tools"] is True
    assert result["flags"]["privacy.context7_public_docs_only"] is True


def test_policy_check_passes_for_default_project(tmp_path):
    _install_rules_and_clients(tmp_path)

    result = evaluate_policy(tmp_path)

    assert result["status"] == "pass"
    assert result["failed"] == 0
    assert {item["id"] for item in result["checks"]}.issuperset({"no-shell-tools", "mcp-registry-allowlist"})


def test_policy_check_fails_when_rules_disable_shell_guard(tmp_path):
    _install_rules_and_clients(tmp_path)
    rules = tmp_path / ".ctx-engine" / "rules.yaml"
    rules.write_text(rules.read_text(encoding="utf-8").replace("no_shell_tools: true", "no_shell_tools: false"), encoding="utf-8")

    result = evaluate_policy(tmp_path)

    assert result["status"] == "fail"
    assert any(item["id"] == "no-shell-tools" and item["status"] == "fail" for item in result["checks"])


def test_policy_cli_strict(capsys, tmp_path):
    _install_rules_and_clients(tmp_path)

    assert main(["policy", "check", str(tmp_path), "--strict"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"

    rules = tmp_path / ".ctx-engine" / "rules.yaml"
    rules.write_text(rules.read_text(encoding="utf-8").replace("redact_secrets: true", "redact_secrets: false"), encoding="utf-8")
    assert main(["policy", "check", str(tmp_path), "--strict"]) == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["status"] == "fail"
