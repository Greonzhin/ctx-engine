from __future__ import annotations

from ctx_engine.integrations.context7 import parse_mcp_response


def test_parse_mcp_sse_response():
    raw = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"ok"}]}}\n\n'
    parsed = parse_mcp_response(raw)
    assert parsed["result"]["content"][0]["text"] == "ok"
