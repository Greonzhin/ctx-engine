from __future__ import annotations

import json
import shutil
import types
import re
import sys

from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.semantic import (
    ScipSemanticAdapter,
    _run_lsp_text_document_references_edges,
    _run_jsonrpc_edge_command,
    _run_lsp_workspace_symbol_edges,
)


def test_symbol_references_finds_test_and_import_links(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    payload = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=20,
    )

    assert payload["status"] == "ok"
    assert payload["references"]
    assert any(str(item.get("path", "")).endswith("tests/test_auth.py") for item in payload["references"])
    assert all(item.get("semantic_confidence") in {"extracted", "inferred", "ambiguous"} for item in payload["references"])
    assert all(isinstance(item.get("edge_evidence"), list) for item in payload["references"])


def test_change_impact_reports_impacted_files_and_tests(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "ts_app")
    payload = CodeGraphProvider().get_change_impact(
        "authenticateToken",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=20,
        include_tests=True,
    )

    assert payload["status"] == "ok"
    assert payload["impacted_files"]
    assert any(str(item.get("path", "")).endswith("src/auth.ts") for item in payload["impacted_files"])
    assert any("test" in "/".join(item.get("reasons", [])) or "test" in str(item.get("path", "")) for item in payload["impacted_files"])
    assert any("suggested_test" in list(item.get("reasons", [])) for item in payload["impacted_files"])


def test_semantic_adapter_fallback_is_deterministic(fixture_root, monkeypatch):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_LSP", "0")
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_SCIP", "0")
    provider = CodeGraphProvider()

    first = provider.get_symbol_references("authenticate_request", workspace_id=result["workspace_id"], depth=1, limit=10)
    second = provider.get_symbol_references("authenticate_request", workspace_id=result["workspace_id"], depth=1, limit=10)

    assert first["references"] == second["references"]
    assert first["adapters"] == second["adapters"]


def test_semantic_depth_expands_reference_hops(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    depth1 = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=50,
    )
    depth2 = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=2,
        limit=50,
    )
    assert depth1["status"] == "ok"
    assert depth2["status"] == "ok"
    assert len(depth2["references"]) >= len(depth1["references"])


def test_graph_store_kuzu_fallback_matches_sqlite_shape(fixture_root, monkeypatch):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")

    monkeypatch.setenv("CTX_ENGINE_GRAPH_BACKEND", "sqlite")
    sqlite_payload = CodeGraphProvider().get_symbol_references("authenticate_request", workspace_id=result["workspace_id"], depth=1, limit=10)

    monkeypatch.setenv("CTX_ENGINE_GRAPH_BACKEND", "kuzu")
    kuzu_payload = CodeGraphProvider().get_symbol_references("authenticate_request", workspace_id=result["workspace_id"], depth=1, limit=10)

    assert sqlite_payload["status"] == "ok"
    assert kuzu_payload["status"] == "ok"
    assert isinstance(sqlite_payload["references"], list)
    assert isinstance(kuzu_payload["references"], list)
    assert {item["path"] for item in sqlite_payload["references"]} == {item["path"] for item in kuzu_payload["references"]}


def test_scip_optional_signal_contributes_edges_when_enabled(fixture_root, monkeypatch):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_LSP", "0")
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_SCIP", "1")
    payload = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=20,
    )
    assert payload["status"] == "ok"
    assert any(item.get("adapter") == "scip" and item.get("available") for item in payload.get("adapters", []))
    assert payload["references"]


def test_semantic_scores_present_on_references(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    payload = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=20,
    )
    assert payload["status"] == "ok"
    assert payload["references"]
    assert all(isinstance(item.get("semantic_score"), (int, float)) for item in payload["references"])


def test_semantic_commands_resolve_workspace_from_cwd(tmp_path, fixture_root, monkeypatch):
    root_py = tmp_path / "python_app"
    root_ts = tmp_path / "ts_app"
    shutil.copytree(fixture_root / "python_app", root_py)
    shutil.copytree(fixture_root / "ts_app", root_ts)

    provider = CodeGraphProvider()
    py_index = provider.index_repository(root_py)
    provider.index_repository(root_ts)  # Make ts latest intentionally.

    monkeypatch.chdir(root_py)
    payload = provider.get_symbol_references("authenticate_request", workspace_id=None, depth=1, limit=20)
    assert payload["status"] == "ok"
    assert payload["workspace_id"] == py_index["workspace_id"]
    assert payload["seeds"]


def test_query_normalization_and_seed_expansion_improve_auth_query(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    payload = CodeGraphProvider().get_change_impact(
        "where is auth request handled",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=20,
        include_tests=False,
    )
    seed_names = {str(item.get("name")) for item in payload.get("seeds", [])}
    assert "authenticate_request" in seed_names


def test_scip_file_parse_is_used_when_available(tmp_path, fixture_root, monkeypatch):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    scip_dir = root / ".scip"
    scip_dir.mkdir(parents=True, exist_ok=True)
    scip_edges = [
        {
            "from_symbol": "test_authenticate_request_accepts_valid_token",
            "from_path": "tests/test_auth.py",
            "from_kind": "function",
            "to_symbol": "authenticate_request",
            "to_path": "app/middleware.py",
            "to_kind": "function",
            "edge_type": "reference",
            "evidence": "scip parsed edge",
            "confidence": "extracted",
        }
    ]
    (scip_dir / "edges.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in scip_edges) + "\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_LSP", "0")
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_SCIP", "1")
    payload = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=20,
    )
    assert payload["status"] == "ok"
    assert any(str(item.get("evidence")) == "scip parsed edge" for item in payload.get("references", []))


def test_lsp_client_ingestion_file_is_used_when_available(tmp_path, fixture_root, monkeypatch):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    lsp_dir = root / ".ctx-engine"
    lsp_dir.mkdir(parents=True, exist_ok=True)
    lsp_edges = [
        {
            "from_symbol": "AuthMiddleware",
            "from_path": "app/middleware.py",
            "from_kind": "class",
            "to_symbol": "authenticate_request",
            "to_path": "app/middleware.py",
            "to_kind": "function",
            "edge_type": "callee",
            "evidence": "lsp client edge",
            "confidence": "extracted",
        }
    ]
    (lsp_dir / "lsp_edges.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in lsp_edges) + "\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_LSP", "1")
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_SCIP", "0")
    payload = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=20,
    )
    assert payload["status"] == "ok"
    assert any(str(item.get("evidence")) == "lsp client edge" for item in payload.get("references", []))


def test_scip_command_ingestion_is_used_when_configured(tmp_path, fixture_root, monkeypatch):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    script = tmp_path / "emit_scip_edges.py"
    script.write_text(
        """
import json
import sys

_payload = json.loads(sys.stdin.read() or "{}")
print(json.dumps({
    "from_symbol": "test_authenticate_request_accepts_valid_token",
    "from_path": "tests/test_auth.py",
    "from_kind": "function",
    "to_symbol": "authenticate_request",
    "to_path": "app/middleware.py",
    "to_kind": "function",
    "edge_type": "reference",
    "evidence": "scip command edge",
    "confidence": "extracted",
}, ensure_ascii=False))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_LSP", "0")
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_SCIP", "1")
    monkeypatch.setenv("CTX_ENGINE_SCIP_EDGE_COMMAND", f"\"{sys.executable}\" \"{script}\"")
    payload = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=20,
    )
    assert payload["status"] == "ok"
    assert any(str(item.get("evidence")) == "scip command edge" for item in payload.get("references", []))


def test_lsp_command_ingestion_is_used_when_configured(tmp_path, fixture_root, monkeypatch):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    script = tmp_path / "emit_lsp_edges.py"
    script.write_text(
        """
import json
import sys

_payload = json.loads(sys.stdin.read() or "{}")
print(json.dumps({
    "from_symbol": "AuthMiddleware",
    "from_path": "app/middleware.py",
    "from_kind": "class",
    "to_symbol": "authenticate_request",
    "to_path": "app/middleware.py",
    "to_kind": "function",
    "edge_type": "callee",
    "evidence": "lsp command edge",
    "confidence": "extracted",
}, ensure_ascii=False))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_LSP", "1")
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_SCIP", "0")
    monkeypatch.setenv("CTX_ENGINE_LSP_EDGE_COMMAND", f"\"{sys.executable}\" \"{script}\"")
    payload = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=20,
    )
    assert payload["status"] == "ok"
    assert any(str(item.get("evidence")) == "lsp command edge" for item in payload.get("references", []))


def test_scip_native_index_parse_is_used_when_available(tmp_path, fixture_root, monkeypatch):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    scip_dir = root / ".scip"
    scip_dir.mkdir(parents=True, exist_ok=True)
    (scip_dir / "index.scip").write_text("placeholder", encoding="utf-8")
    script = tmp_path / "emit_scip_print_json.py"
    script.write_text(
        """
import json

payload = {
    "documents": [
        {
            "relative_path": "tests/test_auth.py",
            "occurrences": [
                {"symbol": "scip-python python . tests.test_auth.test_authenticate_request().", "symbol_roles": 1},
                {"symbol": "scip-python python . app.middleware.authenticate_request().", "symbol_roles": 8},
            ],
        }
    ]
}
print(json.dumps(payload, ensure_ascii=False))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_LSP", "0")
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_SCIP", "1")
    monkeypatch.setenv("CTX_ENGINE_SCIP_PRINT_COMMAND", f"{sys.executable} {script.as_posix()}")
    provider = CodeGraphProvider()
    seeds = provider.search_symbols("authenticate_request", workspace_id=result["workspace_id"], limit=8)
    edges = ScipSemanticAdapter()._load_scip_index_edges(root, seeds, limit=20)
    assert edges
    assert any(str(item.get("evidence")) == "scip print occurrence" for item in edges)


def test_scip_print_parse_is_deterministic_for_same_payload(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    seeds = CodeGraphProvider().search_symbols("authenticate_request", workspace_id=result["workspace_id"], limit=8)
    payload = {
        "documents": [
            {
                "relative_path": "tests/test_auth.py",
                "occurrences": [
                    {"symbol": "scip-python python . tests.test_auth.test_authenticate_request().", "symbol_roles": 1},
                    {"symbol": "scip-python python . app.middleware.authenticate_request().", "symbol_roles": 8},
                ],
            }
        ]
    }
    adapter = ScipSemanticAdapter()
    first = adapter._edges_from_scip_payload(payload, seeds, limit=20)
    second = adapter._edges_from_scip_payload(payload, seeds, limit=20)
    assert first == second


def test_lsp_rpc_ingestion_is_used_when_configured(tmp_path, fixture_root, monkeypatch):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    script = tmp_path / "emit_lsp_rpc_response.py"
    script.write_text(
        """
import json
import re
import sys

raw = sys.stdin.buffer.read()
match = re.search(br"Content-Length:\\s*(\\d+)\\r\\n\\r\\n", raw)
req = {}
if match:
    length = int(match.group(1))
    start = match.end()
    req = json.loads(raw[start:start + length].decode("utf-8"))

edges = [{
    "from_symbol": "AuthMiddleware",
    "from_path": "app/middleware.py",
    "from_kind": "class",
    "to_symbol": "authenticate_request",
    "to_path": "app/middleware.py",
    "to_kind": "function",
    "edge_type": "callee",
    "evidence": "lsp rpc edge",
    "confidence": "extracted",
}]
response = {"jsonrpc": "2.0", "id": req.get("id", 1), "result": {"edges": edges}}
body = json.dumps(response, ensure_ascii=False).encode("utf-8")
sys.stdout.buffer.write(f"Content-Length: {len(body)}\\r\\n\\r\\n".encode("ascii") + body)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    records = _run_jsonrpc_edge_command(
        f"{sys.executable} {script.as_posix()}",
        "workspace/semanticEdges",
        {"workspace_id": "w", "root_path": str(root), "seeds": [], "limit": 20},
        timeout_seconds=8,
    )
    assert records
    assert any(str(item.get("evidence")) == "lsp rpc edge" for item in records)


def test_lsp_workspace_symbol_session_ingestion(tmp_path, fixture_root):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    script = tmp_path / "fake_lsp_server.py"
    script.write_text(
        """
import json
import sys
from pathlib import Path


def read_frames(raw: bytes):
    pos = 0
    out = []
    while pos < len(raw):
        header_end = raw.find(b"\\r\\n\\r\\n", pos)
        if header_end < 0:
            break
        headers = raw[pos:header_end].decode("ascii", errors="ignore").split("\\r\\n")
        pos = header_end + 4
        length = 0
        for line in headers:
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length <= 0 or pos + length > len(raw):
            break
        body = raw[pos:pos + length]
        pos += length
        out.append(json.loads(body.decode("utf-8")))
    return out


def frame(payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\\r\\n\\r\\n".encode("ascii") + body


messages = read_frames(sys.stdin.buffer.read())
root_uri = ""
responses = []
for msg in messages:
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        params = msg.get("params") or {}
        root_uri = str(params.get("rootUri") or "")
        responses.append({"jsonrpc": "2.0", "id": mid, "result": {"capabilities": {}}})
    elif method == "workspace/symbol":
        query = str((msg.get("params") or {}).get("query") or "")
        uri = root_uri.rstrip("/") + "/app/middleware.py"
        responses.append(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": [
                    {
                        "name": "AuthMiddleware",
                        "kind": 5,
                        "location": {"uri": uri, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}},
                        "detail": query,
                    }
                ],
            }
        )
    elif method == "shutdown":
        responses.append({"jsonrpc": "2.0", "id": mid, "result": None})

sys.stdout.buffer.write(b"".join(frame(item) for item in responses))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    seeds = CodeGraphProvider().search_symbols("authenticate_request", workspace_id=result["workspace_id"], limit=8)
    records = _run_lsp_workspace_symbol_edges(
        f"{sys.executable} {script.as_posix()}",
        root=root,
        seeds=seeds,
        limit=20,
        timeout_seconds=8,
    )
    assert records
    assert any(str(item.get("evidence")) == "lsp workspace/symbol" for item in records)


def test_lsp_references_session_ingestion(tmp_path, fixture_root):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    script = tmp_path / "fake_lsp_refs_server.py"
    script.write_text(
        """
import json
import sys


def read_frames(raw: bytes):
    pos = 0
    out = []
    while pos < len(raw):
        header_end = raw.find(b"\\r\\n\\r\\n", pos)
        if header_end < 0:
            break
        headers = raw[pos:header_end].decode("ascii", errors="ignore").split("\\r\\n")
        pos = header_end + 4
        length = 0
        for line in headers:
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length <= 0 or pos + length > len(raw):
            break
        body = raw[pos:pos + length]
        pos += length
        out.append(json.loads(body.decode("utf-8")))
    return out


def frame(payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\\r\\n\\r\\n".encode("ascii") + body


messages = read_frames(sys.stdin.buffer.read())
responses = []
for msg in messages:
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        responses.append({"jsonrpc": "2.0", "id": mid, "result": {"capabilities": {}}})
    elif method == "textDocument/references":
        responses.append(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": [
                    {
                        "uri": "file:///repo/tests/test_auth.py",
                        "range": {"start": {"line": 5, "character": 0}, "end": {"line": 5, "character": 1}},
                    }
                ],
            }
        )
    elif method == "shutdown":
        responses.append({"jsonrpc": "2.0", "id": mid, "result": None})

sys.stdout.buffer.write(b"".join(frame(item) for item in responses))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    seeds = CodeGraphProvider().search_symbols("authenticate_request", workspace_id=result["workspace_id"], limit=8)
    records = _run_lsp_text_document_references_edges(
        f"{sys.executable} {script.as_posix()}",
        root=root,
        seeds=seeds,
        limit=20,
        timeout_seconds=8,
    )
    assert records
    assert any(str(item.get("evidence")) == "lsp references" for item in records)


def test_lsp_client_command_merges_symbol_and_references(tmp_path, fixture_root, monkeypatch):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    script = tmp_path / "fake_lsp_combo_server.py"
    script.write_text(
        """
import json
import sys


def read_frames(raw: bytes):
    pos = 0
    out = []
    while pos < len(raw):
        header_end = raw.find(b"\\r\\n\\r\\n", pos)
        if header_end < 0:
            break
        headers = raw[pos:header_end].decode("ascii", errors="ignore").split("\\r\\n")
        pos = header_end + 4
        length = 0
        for line in headers:
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length <= 0 or pos + length > len(raw):
            break
        body = raw[pos:pos + length]
        pos += length
        out.append(json.loads(body.decode("utf-8")))
    return out


def frame(payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\\r\\n\\r\\n".encode("ascii") + body


messages = read_frames(sys.stdin.buffer.read())
root_uri = ""
responses = []
for msg in messages:
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        root_uri = str((msg.get("params") or {}).get("rootUri") or "")
        responses.append({"jsonrpc": "2.0", "id": mid, "result": {"capabilities": {}}})
    elif method == "workspace/symbol":
        responses.append(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": [
                    {
                        "name": "AuthMiddleware",
                        "kind": 5,
                        "location": {"uri": root_uri.rstrip("/") + "/app/middleware.py", "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}},
                    }
                ],
            }
        )
    elif method == "textDocument/references":
        responses.append(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": [
                    {
                        "uri": root_uri.rstrip("/") + "/tests/test_auth.py",
                        "range": {"start": {"line": 6, "character": 0}, "end": {"line": 6, "character": 1}},
                    }
                ],
            }
        )
    elif method == "shutdown":
        responses.append({"jsonrpc": "2.0", "id": mid, "result": None})

sys.stdout.buffer.write(b"".join(frame(item) for item in responses))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_LSP", "1")
    monkeypatch.setenv("CTX_ENGINE_SEMANTIC_SCIP", "0")
    monkeypatch.delenv("CTX_ENGINE_LSP_EDGE_COMMAND", raising=False)
    monkeypatch.delenv("CTX_ENGINE_LSP_RPC_COMMAND", raising=False)
    monkeypatch.setenv("CTX_ENGINE_LSP_CLIENT_COMMAND", f"{sys.executable} {script.as_posix()}")
    payload = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=20,
    )
    assert payload["status"] == "ok"
    evidences = {str(item.get("evidence")) for item in payload.get("references", [])}
    assert "lsp workspace/symbol" in evidences or "lsp references" in evidences


def test_lsp_references_prefers_document_symbol_selection_range(tmp_path, fixture_root):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    script = tmp_path / "fake_lsp_docsymbol_refs_server.py"
    script.write_text(
        """
import json
import sys


def read_frames(raw: bytes):
    pos = 0
    out = []
    while pos < len(raw):
        header_end = raw.find(b"\\r\\n\\r\\n", pos)
        if header_end < 0:
            break
        headers = raw[pos:header_end].decode("ascii", errors="ignore").split("\\r\\n")
        pos = header_end + 4
        length = 0
        for line in headers:
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length <= 0 or pos + length > len(raw):
            break
        body = raw[pos:pos + length]
        pos += length
        out.append(json.loads(body.decode("utf-8")))
    return out


def frame(payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\\r\\n\\r\\n".encode("ascii") + body


messages = read_frames(sys.stdin.buffer.read())
root_uri = ""
responses = []
for msg in messages:
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        root_uri = str((msg.get("params") or {}).get("rootUri") or "")
        responses.append({"jsonrpc": "2.0", "id": mid, "result": {"capabilities": {}}})
    elif method == "textDocument/documentSymbol":
        responses.append(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": [
                    {
                        "name": "authenticate_request",
                        "kind": 12,
                        "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 40}},
                        "selectionRange": {"start": {"line": 2, "character": 7}, "end": {"line": 2, "character": 27}},
                    }
                ],
            }
        )
    elif method == "textDocument/references":
        pos = (msg.get("params") or {}).get("position") or {}
        ch = int(pos.get("character", -1))
        if ch == 7:
            responses.append(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": [
                        {
                            "uri": root_uri.rstrip("/") + "/tests/test_auth.py",
                            "range": {"start": {"line": 7, "character": 0}, "end": {"line": 7, "character": 1}},
                        }
                    ],
                }
            )
        else:
            responses.append({"jsonrpc": "2.0", "id": mid, "result": []})
    elif method == "shutdown":
        responses.append({"jsonrpc": "2.0", "id": mid, "result": None})

sys.stdout.buffer.write(b"".join(frame(item) for item in responses))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    seeds = CodeGraphProvider().search_symbols("authenticate_request", workspace_id=result["workspace_id"], limit=8)
    records = _run_lsp_text_document_references_edges(
        f"{sys.executable} {script.as_posix()}",
        root=root,
        seeds=seeds,
        limit=20,
        timeout_seconds=8,
    )
    assert records
    assert any(str(item.get("evidence")) == "lsp references" for item in records)


def test_lsp_references_falls_back_to_definition_position(tmp_path, fixture_root):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)
    script = tmp_path / "fake_lsp_definition_refs_server.py"
    script.write_text(
        """
import json
import sys


def read_frames(raw: bytes):
    pos = 0
    out = []
    while pos < len(raw):
        header_end = raw.find(b"\\r\\n\\r\\n", pos)
        if header_end < 0:
            break
        headers = raw[pos:header_end].decode("ascii", errors="ignore").split("\\r\\n")
        pos = header_end + 4
        length = 0
        for line in headers:
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length <= 0 or pos + length > len(raw):
            break
        body = raw[pos:pos + length]
        pos += length
        out.append(json.loads(body.decode("utf-8")))
    return out


def frame(payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(body)}\\r\\n\\r\\n".encode("ascii") + body


messages = read_frames(sys.stdin.buffer.read())
root_uri = ""
responses = []
for msg in messages:
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        root_uri = str((msg.get("params") or {}).get("rootUri") or "")
        responses.append({"jsonrpc": "2.0", "id": mid, "result": {"capabilities": {}}})
    elif method == "textDocument/documentSymbol":
        responses.append({"jsonrpc": "2.0", "id": mid, "result": []})
    elif method == "textDocument/definition":
        responses.append(
            {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {
                    "uri": root_uri.rstrip("/") + "/app/middleware.py",
                    "range": {"start": {"line": 2, "character": 11}, "end": {"line": 2, "character": 26}},
                },
            }
        )
    elif method == "textDocument/references":
        pos = (msg.get("params") or {}).get("position") or {}
        ch = int(pos.get("character", -1))
        if ch == 11:
            responses.append(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": [
                        {
                            "uri": root_uri.rstrip("/") + "/tests/test_auth.py",
                            "range": {"start": {"line": 8, "character": 0}, "end": {"line": 8, "character": 1}},
                        }
                    ],
                }
            )
        else:
            responses.append({"jsonrpc": "2.0", "id": mid, "result": []})
    elif method == "shutdown":
        responses.append({"jsonrpc": "2.0", "id": mid, "result": None})

sys.stdout.buffer.write(b"".join(frame(item) for item in responses))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    seeds = CodeGraphProvider().search_symbols("authenticate_request", workspace_id=result["workspace_id"], limit=8)
    records = _run_lsp_text_document_references_edges(
        f"{sys.executable} {script.as_posix()}",
        root=root,
        seeds=seeds,
        limit=20,
        timeout_seconds=8,
    )
    assert records
    assert any(str(item.get("evidence")) == "lsp references" for item in records)


def test_graph_store_kuzu_runtime_path_uses_kuzu_backend(fixture_root, monkeypatch):
    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def rows_as_dict(self):
            return self

        def get_all(self):
            return self._rows

    class _Connection:
        def __init__(self, _db):
            self.nodes = {}
            self.edges = []

        @staticmethod
        def _parse_map(query: str) -> dict[str, object]:
            body = query.split("{", 1)[1].rsplit("}", 1)[0]
            out: dict[str, object] = {}
            for part in body.split(","):
                if ":" not in part:
                    continue
                key, value = part.split(":", 1)
                key = key.strip()
                value = value.strip().rstrip(")")
                if value.startswith("'") and value.endswith("'"):
                    out[key] = value[1:-1]
                elif value.lower() in {"true", "false"}:
                    out[key] = value.lower() == "true"
                else:
                    try:
                        out[key] = float(value)
                    except Exception:
                        out[key] = value
            return out

        def execute(self, query: str):
            if query.startswith("CREATE NODE TABLE") or query.startswith("CREATE REL TABLE"):
                return _Result([])
            if query.startswith("CREATE (:Symbol"):
                props = self._parse_map(query)
                self.nodes[str(props.get("id"))] = props
                return _Result([])
            if query.startswith("MATCH (a:Symbol {id:") and "CREATE (a)-[:Edge" in query:
                ids = re.findall(r"id:\s*'([^']+)'", query)
                from_id = ids[0] if len(ids) >= 1 else ""
                to_id = ids[1] if len(ids) >= 2 else ""
                edge_props = self._parse_map(query.split("[:Edge", 1)[1])
                self.edges.append(
                    {
                        "from_id": from_id,
                        "to_id": to_id,
                        "edge_type": edge_props.get("edge_type"),
                        "evidence": edge_props.get("evidence"),
                        "confidence": edge_props.get("confidence"),
                        "score": float(edge_props.get("score") or 0.0),
                    }
                )
                return _Result([])
            if query.startswith("MATCH (a:Symbol)-[e:Edge]->(b:Symbol)"):
                all_lists = re.findall(r"\[(.*?)\]", query)
                seed_ids = set()
                for block in all_lists[:1]:
                    for token in block.split(","):
                        token = token.strip()
                        if token.startswith("'") and token.endswith("'"):
                            seed_ids.add(token[1:-1])
                rows = []
                for e in self.edges:
                    if e["from_id"] not in seed_ids and e["to_id"] not in seed_ids:
                        continue
                    a = self.nodes.get(e["from_id"], {})
                    b = self.nodes.get(e["to_id"], {})
                    rows.append(
                        {
                            "from_id": e["from_id"],
                            "from_name": a.get("name"),
                            "from_path": a.get("path"),
                            "from_kind": a.get("kind"),
                            "from_test": bool(a.get("is_test")),
                            "to_id": e["to_id"],
                            "to_name": b.get("name"),
                            "to_path": b.get("path"),
                            "to_kind": b.get("kind"),
                            "to_test": bool(b.get("is_test")),
                            "edge_type": e.get("edge_type"),
                            "evidence": e.get("evidence"),
                            "confidence": e.get("confidence"),
                            "score": float(e.get("score") or 0.0),
                        }
                    )
                rows.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
                return _Result(rows)
            return _Result([])

    class _Database:
        def __init__(self, _path):
            self.path = _path

    fake_kuzu = types.SimpleNamespace(Database=_Database, Connection=_Connection)
    monkeypatch.setitem(sys.modules, "kuzu", fake_kuzu)
    monkeypatch.setenv("CTX_ENGINE_GRAPH_BACKEND", "kuzu")
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    payload = CodeGraphProvider().get_symbol_references(
        "authenticate_request",
        workspace_id=result["workspace_id"],
        depth=1,
        limit=10,
    )
    assert payload["status"] == "ok"
    assert payload["backend"] == "kuzu"
    assert payload["references"]
