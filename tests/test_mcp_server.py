from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from ctx_engine.server import MCPGateway, PROTOCOL_VERSION, make_server
from ctx_engine.mcp_contract import check_gateway_contract, check_http_gateway_contract


def test_mcp_lists_required_tools():
    gateway = MCPGateway()
    status, response = gateway.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert status == 200
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert "get_context_capsule" in names
    assert "get_doctor_status" in names
    assert "get_blast_radius" in names
    assert "get_symbol_references" in names
    assert "get_change_impact" in names
    assert "shell" not in " ".join(names)


def test_http_server_starts():
    server = make_server("127.0.0.1", 0, "safe")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/health"
        with urllib.request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8"))
        assert data["status"] == "ok"
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_endpoints_are_local_read_only():
    server = make_server("127.0.0.1", 0, "safe")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(f"{base}/dashboard", timeout=2) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "ctx-engine" in html
        assert "/dashboard/status" in html

        with urllib.request.urlopen(f"{base}/dashboard/status", timeout=2) as response:
            data = json.loads(response.read().decode("utf-8"))
        assert data["local_only"] is True
        assert data["mode"] == "safe"
        assert data["doctor"]["checks"]["mcp_health"]["reachable"] is True
        assert data["mcp"]["registered_tool_count"] >= 1

        request = urllib.request.Request(f"{base}/dashboard/status", headers={"Host": "ctx-engine.example"})
        try:
            urllib.request.urlopen(request, timeout=2)
            raise AssertionError("dashboard should reject non-local Host headers")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        server.server_close()


def test_mcp_contract_check_passes():
    result = check_gateway_contract()
    assert result["status"] == "pass"
    assert result["protocol_version"] == "2025-11-25"
    assert result["checks"]["no_shell_or_write_tools"] is True


def test_http_mcp_contract_check_passes():
    server = make_server("127.0.0.1", 0, "safe")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/mcp"
        result = check_http_gateway_contract(endpoint)
        assert result["status"] == "pass"
        assert result["transport"] == "http"
    finally:
        server.shutdown()
        server.server_close()


def _post_json(url: str, payload: dict[str, object], headers: dict[str, str] | None = None) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_http_mcp_rejects_bad_origin_and_protocol_version():
    server = make_server("127.0.0.1", 0, "safe")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/mcp"
        payload = {"jsonrpc": "2.0", "id": 1, "method": "ping"}

        try:
            _post_json(endpoint, payload, {"Origin": "http://127.0.0.1.evil.example"})
            raise AssertionError("bad origin should be forbidden")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403

        try:
            _post_json(endpoint, payload, {"MCP-Protocol-Version": "1900-01-01"})
            raise AssertionError("bad protocol version should fail")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400

        status, data = _post_json(endpoint, payload, {"Origin": f"http://127.0.0.1:{server.server_port}"})
        assert status == 200
        assert data["result"] == {}
    finally:
        server.shutdown()
        server.server_close()


def test_http_mcp_get_returns_405_without_sse_stream():
    server = make_server("127.0.0.1", 0, "safe")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/mcp",
            headers={"Accept": "text/event-stream"},
        )
        try:
            urllib.request.urlopen(request, timeout=2)
            raise AssertionError("GET /mcp should report unsupported SSE stream")
        except urllib.error.HTTPError as exc:
            assert exc.code == 405
    finally:
        server.shutdown()
        server.server_close()


def test_tools_call_validation_errors_return_tool_error():
    gateway = MCPGateway()

    status, response = gateway.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "tools/call",
            "params": {"name": "search_symbols", "arguments": {}},
        }
    )
    assert status == 200
    assert response["result"]["isError"] is True
    assert "missing required fields" in response["result"]["content"][0]["text"]

    status, response = gateway.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 43,
            "method": "tools/call",
            "params": {"name": "get_context_capsule", "arguments": {"query": "auth", "token_budget": "4000"}},
        }
    )
    assert status == 200
    assert response["result"]["isError"] is True
    assert "must be integer" in response["result"]["content"][0]["text"]

    status, response = gateway.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 44,
            "method": "tools/call",
            "params": {"name": "workspace_list", "arguments": {"unexpected": True}},
        }
    )
    assert status == 200
    assert response["result"]["isError"] is True
    assert "unknown fields" in response["result"]["content"][0]["text"]
