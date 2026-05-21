from __future__ import annotations

from copy import deepcopy


SUPPORTED_HOOK_CLIENTS = ("codex", "claude", "gemini")

_COMMON_CHECKS = [
    {
        "event": "session-start",
        "command": "ctx doctor --strict",
        "purpose": "Verify local runtime, Docker daemon visibility, path mapping, and gateway prerequisites.",
    },
    {
        "event": "pre-tool-use",
        "command": "ctx mcp-lint --strict",
        "purpose": "Fail fast if the exposed MCP tool surface drifts from the allowlisted registry.",
    },
    {
        "event": "pre-handoff",
        "command": "scripts/quality_gate.ps1",
        "purpose": "Run the local pytest, rules, MCP, docs, egress, compression, and Docker quality gate.",
    },
]

_CLIENT_NOTES = {
    "codex": [
        "Keep AGENTS.md and .codex/config.toml generated from .ctx-engine/rules.yaml.",
        "Codex should use ctx-engine as the single project MCP gateway.",
    ],
    "claude": [
        "Keep CLAUDE.md and .mcp.json generated from .ctx-engine/rules.yaml.",
        "Claude should use ctx-engine as the single project MCP gateway.",
    ],
    "gemini": [
        "Keep GEMINI.md and .gemini/settings.json generated from .ctx-engine/rules.yaml.",
        "Gemini should use ctx-engine as the single project MCP gateway.",
    ],
}

_BLOCKED_ACTIONS = [
    "Auto-installing executable hooks without explicit user approval.",
    "Adding shell or repository write tools to the MCP surface.",
    "Connecting directly to downstream docs, memory, code graph, or shell MCP servers.",
    "Sending private source, private docs, secrets, ignored files, or full prompts to external providers.",
]


def _client_plan(client_id: str) -> dict[str, object]:
    if client_id not in SUPPORTED_HOOK_CLIENTS:
        raise ValueError(f"unsupported hook client: {client_id}")
    return {
        "client_id": client_id,
        "mode": "advisory",
        "auto_install": False,
        "recommended_checks": deepcopy(_COMMON_CHECKS),
        "blocked_actions": list(_BLOCKED_ACTIONS),
        "notes": list(_CLIENT_NOTES[client_id]),
    }


def hook_plan(client: str = "all") -> dict[str, object]:
    selected = SUPPORTED_HOOK_CLIENTS if client == "all" else (client,)
    clients = [_client_plan(client_id) for client_id in selected]
    return {
        "status": "ok",
        "mode": "advisory",
        "auto_install": False,
        "clients": clients,
        "warnings": [
            "This command does not install executable client hooks. It documents the safe commands to wire manually when a client hook format is approved."
        ],
    }


def hook_guidance_markdown(client_id: str) -> str:
    plan = _client_plan(client_id)
    checks = "\n".join(
        f"- `{item['command']}` ({item['event']}): {item['purpose']}" for item in plan["recommended_checks"]
    )
    blocked = "\n".join(f"- {item}" for item in plan["blocked_actions"])
    return f"""Hook guidance:

- Advisory only: ctx-engine does not auto-install executable hooks.
- Inspect the current plan with `ctx hooks plan {client_id}`.
- Keep generated client files in sync with `ctx rules check . --strict`.

Recommended checks:

{checks}

Blocked unless explicitly approved:

{blocked}
"""
