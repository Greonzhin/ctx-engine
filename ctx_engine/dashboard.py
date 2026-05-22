from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from . import __version__
from .doctor import doctor_status
from .mcp_registry import load_tool_registry
from .providers.action_ledger import ActionLedger
from .providers.egress import EgressProvider
from .verified_cache import verify_capsule_cache
from .workspace import workspace_inventory


def _status_rank(status: str) -> int:
    order = {"pass": 0, "ok": 0, "healthy": 0, "ready": 0, "warn": 1, "attention": 1, "stale": 1, "fail": 2, "error": 2, "unhealthy": 2}
    return order.get(status, 1)


def _rollup(statuses: list[str]) -> str:
    worst = max((_status_rank(status) for status in statuses), default=0)
    if worst >= 2:
        return "fail"
    if worst == 1:
        return "attention"
    return "ok"


def _workspace_root(inventory: dict[str, Any]) -> str:
    active = inventory.get("active_workspace")
    if isinstance(active, dict) and active.get("root_path"):
        return str(active["root_path"])
    return "."


def dashboard_status(mode: str = "safe", endpoint: str | None = None) -> dict[str, Any]:
    from .policy import evaluate_policy

    inventory = workspace_inventory()
    root = _workspace_root(inventory)
    doctor = doctor_status(root, endpoint=endpoint) if endpoint else doctor_status(root)
    policy = evaluate_policy(root, mode=mode) if Path(root).exists() else {"status": "unavailable", "checks": []}
    registry = load_tool_registry()
    cache = verify_capsule_cache(limit=10)
    egress = EgressProvider().report(provider="context7", limit=20)
    ledger = ActionLedger().tail(limit=5)

    status = _rollup(
        [
            str(inventory.get("status", "attention")),
            str(doctor.get("status", "unhealthy")),
            str(policy.get("status", "fail")),
            str(cache.get("status", "ok")),
        ]
    )
    return {
        "status": status,
        "version": __version__,
        "mode": mode,
        "local_only": True,
        "workspace": inventory,
        "doctor": doctor,
        "policy": policy,
        "mcp": {
            "status": "ok",
            "tool_count": len(registry.get("tools", {})),
            "registered_tool_count": len(registry.get("tools", {})),
            "registry_version": registry.get("version"),
            "warnings": [],
            "errors": [],
        },
        "cache": cache,
        "egress": egress,
        "ledger": ledger,
    }


def render_dashboard_html() -> str:
    title = "ctx-engine dashboard"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #637083;
      --line: #d8dde6;
      --accent: #176b87;
      --good: #18794e;
      --warn: #9a6700;
      --bad: #c22f2f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      padding: 24px clamp(16px, 4vw, 48px) 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{ margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 0; }}
    .sub {{ margin-top: 4px; color: var(--muted); font-size: 13px; }}
    main {{ padding: 22px clamp(16px, 4vw, 48px) 36px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
      align-items: start;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
    }}
    .wide {{ grid-column: 1 / -1; }}
    h2 {{ margin: 0 0 12px; font-size: 15px; font-weight: 700; letter-spacing: 0; }}
    .metric {{ display: flex; justify-content: space-between; gap: 12px; padding: 7px 0; border-top: 1px solid #edf0f4; }}
    .metric:first-of-type {{ border-top: 0; }}
    .label {{ color: var(--muted); }}
    .value {{ overflow-wrap: anywhere; text-align: right; }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 13px;
      font-weight: 650;
      background: #fff;
    }}
    .ok {{ color: var(--good); border-color: #a9d8be; background: #f1fbf5; }}
    .attention {{ color: var(--warn); border-color: #e6c675; background: #fff8e6; }}
    .fail, .unhealthy {{ color: var(--bad); border-color: #efb4b4; background: #fff1f1; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 8px; border-top: 1px solid #edf0f4; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 650; }}
    td.path {{ overflow-wrap: anywhere; }}
    pre {{
      margin: 0;
      max-height: 260px;
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #111820;
      color: #f4f7fb;
      border-radius: 8px;
      padding: 12px;
      font-size: 12px;
      line-height: 1.45;
    }}
    @media (max-width: 640px) {{
      header {{ align-items: start; flex-direction: column; }}
      .metric {{ flex-direction: column; }}
      .value {{ text-align: left; }}
      th:nth-child(3), td:nth-child(3) {{ display: none; }}
    }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>ctx-engine</h1>
      <div class="sub">local dashboard</div>
    </div>
    <div id="overall" class="pill attention">loading</div>
  </header>
  <main>
    <section class="grid">
      <div class="panel">
        <h2>Runtime</h2>
        <div class="metric"><span class="label">Mode</span><span class="value" id="mode">-</span></div>
        <div class="metric"><span class="label">Version</span><span class="value" id="version">-</span></div>
        <div class="metric"><span class="label">Docker</span><span class="value" id="docker">-</span></div>
        <div class="metric"><span class="label">MCP health</span><span class="value" id="mcpHealth">-</span></div>
      </div>
      <div class="panel">
        <h2>Policy</h2>
        <div class="metric"><span class="label">Status</span><span class="value" id="policyStatus">-</span></div>
        <div class="metric"><span class="label">Passed</span><span class="value" id="policyPassed">-</span></div>
        <div class="metric"><span class="label">Failed</span><span class="value" id="policyFailed">-</span></div>
      </div>
      <div class="panel">
        <h2>MCP</h2>
        <div class="metric"><span class="label">Lint</span><span class="value" id="mcpStatus">-</span></div>
        <div class="metric"><span class="label">Tools</span><span class="value" id="toolCount">-</span></div>
        <div class="metric"><span class="label">Registry</span><span class="value" id="registryCount">-</span></div>
      </div>
      <div class="panel">
        <h2>Cache And Egress</h2>
        <div class="metric"><span class="label">Cache</span><span class="value" id="cacheStatus">-</span></div>
        <div class="metric"><span class="label">Context7 events</span><span class="value" id="egressEvents">-</span></div>
        <div class="metric"><span class="label">Context7 failures</span><span class="value" id="egressFailures">-</span></div>
      </div>
      <div class="panel wide">
        <h2>Workspaces</h2>
        <table>
          <thead><tr><th>Name</th><th>Status</th><th>Indexed</th><th>Path</th></tr></thead>
          <tbody id="workspaces"><tr><td colspan="4">loading</td></tr></tbody>
        </table>
      </div>
      <div class="panel wide">
        <h2>Recent Ledger</h2>
        <pre id="ledger">loading</pre>
      </div>
    </section>
  </main>
  <script>
    const text = (id, value) => {{ document.getElementById(id).textContent = value ?? "-"; }};
    const cls = (status) => status === "ok" || status === "pass" || status === "healthy" ? "ok" : (status === "fail" || status === "unhealthy" || status === "error" ? "fail" : "attention");
    fetch("/dashboard/status")
      .then((response) => response.json())
      .then((data) => {{
        const overall = document.getElementById("overall");
        overall.textContent = data.status;
        overall.className = "pill " + cls(data.status);
        text("mode", data.mode);
        text("version", data.version);
        text("docker", data.doctor?.checks?.docker_daemon?.reachable ? "reachable" : "unavailable");
        text("mcpHealth", data.doctor?.checks?.mcp_health?.reachable ? "reachable" : "not running");
        text("policyStatus", data.policy?.status);
        text("policyPassed", data.policy?.passed);
        text("policyFailed", data.policy?.failed);
        text("mcpStatus", data.mcp?.status);
        text("toolCount", data.mcp?.tool_count);
        text("registryCount", data.mcp?.registered_tool_count);
        text("cacheStatus", data.cache?.status);
        text("egressEvents", data.egress?.summary?.events);
        text("egressFailures", data.egress?.summary?.failed);
        const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({{
          "&": "&amp;", "<": "&lt;", ">": "&gt;", "\\"": "&quot;", "'": "&#39;"
        }}[char]));
        const rows = (data.workspace?.workspaces || []).map((item) => `
          <tr>
            <td>${{escapeHtml(item.display_name || item.id)}}${{item.active ? " *" : ""}}</td>
            <td><span class="pill ${{item.exists ? "ok" : "fail"}}">${{item.exists ? "present" : "missing"}}</span></td>
            <td>${{item.indexed ? "yes" : "no"}}</td>
            <td class="path">${{escapeHtml(item.root_path)}}</td>
          </tr>`).join("");
        document.getElementById("workspaces").innerHTML = rows || "<tr><td colspan='4'>none</td></tr>";
        document.getElementById("ledger").textContent = JSON.stringify(data.ledger || [], null, 2);
      }})
      .catch((error) => {{
        const overall = document.getElementById("overall");
        overall.textContent = "error";
        overall.className = "pill fail";
        document.getElementById("ledger").textContent = String(error);
      }});
  </script>
</body>
</html>
"""
