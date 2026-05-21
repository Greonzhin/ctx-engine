from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.hooks import hook_guidance_markdown, hook_plan


def test_hook_plan_all_is_advisory_only():
    result = hook_plan("all")

    assert result["status"] == "ok"
    assert result["mode"] == "advisory"
    assert result["auto_install"] is False
    assert [item["client_id"] for item in result["clients"]] == ["codex", "claude", "gemini"]
    assert all(item["auto_install"] is False for item in result["clients"])


def test_hook_plan_contains_quality_commands():
    result = hook_plan("codex")
    commands = {item["command"] for item in result["clients"][0]["recommended_checks"]}

    assert "ctx doctor --strict" in commands
    assert "ctx mcp-lint --strict" in commands
    assert "scripts/quality_gate.ps1" in commands


def test_hook_guidance_markdown_mentions_rules_and_plan():
    guidance = hook_guidance_markdown("claude")

    assert "ctx hooks plan claude" in guidance
    assert "ctx rules check . --strict" in guidance
    assert "shell or repository write tools" in guidance


def test_cli_hooks_plan_outputs_json(capsys):
    assert main(["hooks", "plan", "gemini"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "ok"
    assert payload["clients"][0]["client_id"] == "gemini"
    assert payload["clients"][0]["mode"] == "advisory"
