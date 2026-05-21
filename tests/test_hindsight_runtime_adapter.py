from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.memory import BuiltInMemoryProvider


def _start_server(handler_cls: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    return server, thread, endpoint


def _send_json(handler: BaseHTTPRequestHandler, body: object, status: int = 200) -> None:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.wfile.write(data)
    handler.wfile.flush()
    handler.close_connection = True


class _OkHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8") or "{}")
        if self.path == "/retain":
            body = {"id": "h-1", "workspace_id": payload.get("workspace_id"), "provider_used": "hindsight"}
        elif self.path == "/recall":
            body = {"memories": [{"id": "h-2", "claim": "remote memory", "provider_used": "hindsight"}]}
        elif self.path == "/apply_lifecycle_policy":
            body = {"status": "ok", "provider_used": "hindsight"}
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            return
        _send_json(self, body)

    def log_message(self, format, *args):  # noqa: A003
        return


class _FailHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        self.send_response(500)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def log_message(self, format, *args):  # noqa: A003
        return


class _LegacyRecallArrayHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        if self.path == "/retain":
            body = {"id": "h-1", "provider_used": "hindsight"}
        elif self.path == "/recall":
            body = [{"id": "legacy", "claim": "legacy array shape"}]
        elif self.path == "/apply_lifecycle_policy":
            body = {"status": "ok", "provider_used": "hindsight"}
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            return
        _send_json(self, body)

    def log_message(self, format, *args):  # noqa: A003
        return


def test_hindsight_runtime_adapter_uses_endpoint_when_available(fixture_root, monkeypatch):
    server, thread, endpoint = _start_server(_OkHandler)
    try:
        result = CodeGraphProvider().index_repository(fixture_root / "python_app")
        monkeypatch.setenv("CTX_ENGINE_MEMORY_PROVIDER", "hindsight")
        monkeypatch.setenv("CTX_ENGINE_HINDSIGHT_ENDPOINT", endpoint)
        provider = BuiltInMemoryProvider()

        written = provider.retain("Auth logic in middleware", workspace_id=result["workspace_id"])
        assert written["provider_used"] == "hindsight"

        rows = provider.recall("auth", workspace_id=result["workspace_id"])
        assert rows
        assert rows[0]["provider_used"] == "hindsight"

        policy = provider.apply_lifecycle_policy(workspace_id=result["workspace_id"])
        assert policy["provider_used"] == "hindsight"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_hindsight_runtime_adapter_falls_back_on_remote_error(fixture_root, monkeypatch):
    server, thread, endpoint = _start_server(_FailHandler)
    try:
        result = CodeGraphProvider().index_repository(fixture_root / "python_app")
        monkeypatch.setenv("CTX_ENGINE_MEMORY_PROVIDER", "hindsight")
        monkeypatch.setenv("CTX_ENGINE_HINDSIGHT_ENDPOINT", endpoint)
        provider = BuiltInMemoryProvider()

        written = provider.retain("Auth logic fallback", workspace_id=result["workspace_id"])
        assert written["provider_used"] == "sqlite_fallback"
        assert "provider_warning" in written

        rows = provider.recall("auth", workspace_id=result["workspace_id"])
        assert rows
        assert rows[0]["provider_used"] == "sqlite_fallback"
        assert "provider_warning" in rows[0]
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_hindsight_runtime_adapter_rejects_legacy_recall_array(fixture_root, monkeypatch):
    server, thread, endpoint = _start_server(_LegacyRecallArrayHandler)
    try:
        result = CodeGraphProvider().index_repository(fixture_root / "python_app")
        BuiltInMemoryProvider().retain("Auth logic fallback for legacy recall", workspace_id=result["workspace_id"])
        monkeypatch.setenv("CTX_ENGINE_MEMORY_PROVIDER", "hindsight")
        monkeypatch.setenv("CTX_ENGINE_HINDSIGHT_ENDPOINT", endpoint)
        provider = BuiltInMemoryProvider()

        rows = provider.recall("auth", workspace_id=result["workspace_id"])
        assert rows
        assert rows[0]["provider_used"] == "sqlite_fallback"
        assert "recall response must be an object with memories" in rows[0]["provider_warning"]
    finally:
        server.shutdown()
        thread.join(timeout=2)
