from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from urllib.parse import unquote, urlparse
from pathlib import Path

from ..db import connect, init_db
from ..workspace import get_workspace


def _symbol_token(value: str) -> str:
    return value.strip().lower()


def _term_in_text(term: str, text: str) -> bool:
    if not term or not text:
        return False

    # Fast path: substring check avoids expensive regex calls for the common
    # negative case, while preserving regex word-boundary semantics for positives.
    lowered_term = term.lower()
    lowered_text = text.lower()
    if lowered_term not in lowered_text:
        return False

    pattern = rf"\b{re.escape(term)}\b"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _read_records_from_file(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".jsonl":
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        records = [json.loads(line) for line in lines if line.strip()]
    else:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        records = _records_from_payload(payload)
    return [item for item in records if isinstance(item, dict)]


def _read_records_from_stdout(text: str) -> list[dict[str, object]]:
    body = text.strip()
    if not body:
        return []
    if body.startswith("{") or body.startswith("["):
        payload = json.loads(body)
        records = _records_from_payload(payload)
        return [item for item in records if isinstance(item, dict)]
    records: list[dict[str, object]] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            records.append(row)
    return records


def _normalize_edge_record(record: dict[str, object], adapter_name: str, default_evidence: str, default_confidence: str) -> dict[str, object]:
    return {
        "from_symbol_id": record.get("from_symbol_id"),
        "from_symbol": record.get("from_symbol"),
        "from_path": record.get("from_path"),
        "from_kind": record.get("from_kind"),
        "from_test_name": bool(record.get("from_test_name", False)),
        "to_symbol_id": record.get("to_symbol_id"),
        "to_symbol": record.get("to_symbol"),
        "to_path": record.get("to_path"),
        "to_kind": record.get("to_kind"),
        "to_test_name": bool(record.get("to_test_name", False)),
        "edge_type": str(record.get("edge_type") or "reference"),
        "evidence": str(record.get("evidence") or default_evidence),
        "confidence": str(record.get("confidence") or default_confidence),
        "source_adapter": adapter_name,
    }


def _records_from_payload(payload: object) -> list[object]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "edges" in payload and isinstance(payload.get("edges"), list):
            return list(payload.get("edges") or [])
        if any(key in payload for key in ("from_symbol", "to_symbol", "edge_type", "from_symbol_id", "to_symbol_id")):
            return [payload]
    return []


def _run_edge_command(command_text: str, payload: dict[str, object], timeout_seconds: float = 8.0) -> list[dict[str, object]]:
    raw = _split_command(command_text)
    command = []
    for item in raw:
        value = item.strip()
        if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
            value = value[1:-1]
        command.append(value)
    if not command:
        return []
    proc = subprocess.run(
        command,
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=max(1.0, float(timeout_seconds)),
        check=False,
    )
    if proc.returncode != 0:
        return []
    return _read_records_from_stdout(proc.stdout)


def _split_command(command_text: str) -> list[str]:
    text = (command_text or "").strip()
    if not text:
        return []
    preferred_posix = os.name != "nt"
    attempts = [preferred_posix, not preferred_posix]
    parts: list[str] | None = None
    for posix_mode in attempts:
        try:
            parts = shlex.split(text, posix=posix_mode)
            break
        except Exception:
            continue
    if parts is None:
        return []
    cleaned: list[str] = []
    for item in parts:
        value = item.strip()
        if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
            value = value[1:-1]
        if value:
            cleaned.append(value)
    return cleaned


def _encode_lsp_frame(payload: dict[str, object]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def _decode_lsp_frames(raw: bytes) -> list[dict[str, object]]:
    if not raw:
        return []
    data = raw
    pos = 0
    messages: list[dict[str, object]] = []
    while pos < len(data):
        header_end = data.find(b"\r\n\r\n", pos)
        if header_end < 0:
            break
        header_blob = data[pos:header_end].decode("ascii", errors="ignore")
        pos = header_end + 4
        length = 0
        for line in header_blob.split("\r\n"):
            if line.lower().startswith("content-length:"):
                try:
                    length = int(line.split(":", 1)[1].strip())
                except Exception:
                    length = 0
                break
        if length <= 0 or pos + length > len(data):
            break
        body = data[pos : pos + length]
        pos += length
        try:
            parsed = json.loads(body.decode("utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(parsed, dict):
            messages.append(parsed)
    return messages


def _run_jsonrpc_edge_command(
    command_text: str,
    method: str,
    params: dict[str, object],
    timeout_seconds: float = 8.0,
) -> list[dict[str, object]]:
    command = _split_command(command_text)
    if not command:
        return []
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    proc = subprocess.run(
        command,
        input=_encode_lsp_frame(request),
        capture_output=True,
        timeout=max(1.0, float(timeout_seconds)),
        check=False,
    )
    if proc.returncode != 0 and not proc.stdout:
        return []
    frames = _decode_lsp_frames(proc.stdout or b"")
    if not frames:
        try:
            text = (proc.stdout or b"").decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return _read_records_from_stdout(text)
    for message in frames:
        if str(message.get("jsonrpc") or "") != "2.0":
            continue
        if message.get("id") != 1:
            continue
        result = message.get("result")
        records = _records_from_payload(result)
        return [item for item in records if isinstance(item, dict)]
    return []


def _scip_symbol_name(symbol: str) -> str:
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", symbol or "")
    return tokens[-1] if tokens else ""


def _looks_like_test_path(path: str) -> bool:
    lowered = path.replace("\\", "/").lower()
    return (
        "/test" in lowered
        or lowered.endswith("_test.py")
        or lowered.endswith(".test.ts")
        or lowered.endswith(".test.js")
        or lowered.endswith(".spec.ts")
        or lowered.endswith(".spec.js")
    )


def _path_from_uri(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return ""
    path = unquote(parsed.path or "")
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    return path


def _lsp_kind_label(value: object) -> str:
    try:
        kind = int(value)
    except Exception:
        return "symbol"
    mapping = {
        5: "class",
        6: "method",
        12: "function",
        13: "variable",
        23: "struct",
    }
    return mapping.get(kind, "symbol")


def _rel_or_normalized_path(path_text: str, root: Path) -> str:
    raw = str(path_text or "").strip()
    if not raw:
        return ""
    try:
        absolute = Path(raw).resolve()
        rel = absolute.relative_to(root.resolve())
        return rel.as_posix()
    except Exception:
        return raw.replace("\\", "/")


def _flatten_document_symbols(items: list[object]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    stack: list[object] = list(items)
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        out.append(node)
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(children)
    return out


def _symbol_selection_start(symbol: dict[str, object]) -> tuple[int, int] | None:
    selection = symbol.get("selectionRange")
    if not isinstance(selection, dict):
        selection = symbol.get("range")
    if not isinstance(selection, dict):
        return None
    start = selection.get("start")
    if not isinstance(start, dict):
        return None
    try:
        line = int(start.get("line"))
        char = int(start.get("character"))
    except Exception:
        return None
    if line < 0 or char < 0:
        return None
    return (line, char)


def _extract_lsp_location_start(item: object, root: Path) -> tuple[str, int, int] | None:
    if not isinstance(item, dict):
        return None
    uri = str(item.get("uri") or item.get("targetUri") or "")
    abs_path = _path_from_uri(uri)
    rel_path = _rel_or_normalized_path(abs_path, root)
    if not rel_path:
        return None
    range_obj = item.get("range")
    if not isinstance(range_obj, dict):
        range_obj = item.get("targetSelectionRange")
    if not isinstance(range_obj, dict):
        range_obj = item.get("targetRange")
    if not isinstance(range_obj, dict):
        return None
    start = range_obj.get("start")
    if not isinstance(start, dict):
        return None
    try:
        line = int(start.get("line"))
        char = int(start.get("character"))
    except Exception:
        return None
    if line < 0 or char < 0:
        return None
    return (rel_path, line, char)


def _resolve_lsp_seed_positions(
    command_text: str,
    root: Path,
    seeds: list[dict[str, object]],
    timeout_seconds: float = 10.0,
) -> dict[str, tuple[int, int]]:
    command = _split_command(command_text)
    if not command or not seeds:
        return {}
    root_uri = root.resolve().as_uri()
    unique_files: list[str] = []
    for seed in seeds:
        rel_path = str(seed.get("rel_path") or "")
        if rel_path and rel_path not in unique_files:
            unique_files.append(rel_path)
    if not unique_files:
        return {}

    outbound: list[bytes] = []
    outbound.append(
        _encode_lsp_frame(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "processId": None,
                    "rootUri": root_uri,
                    "workspaceFolders": [{"uri": root_uri, "name": root.name or "workspace"}],
                    "capabilities": {},
                },
            }
        )
    )
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
    req_map: dict[int, str] = {}
    req_id = 1200
    for rel_path in unique_files:
        uri = (root / rel_path).resolve().as_uri()
        req_map[req_id] = rel_path
        outbound.append(
            _encode_lsp_frame(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": "textDocument/documentSymbol",
                    "params": {"textDocument": {"uri": uri}},
                }
            )
        )
        req_id += 1
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "id": req_id, "method": "shutdown", "params": None}))
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "method": "exit", "params": {}}))

    try:
        proc = subprocess.run(
            command,
            input=b"".join(outbound),
            capture_output=True,
            timeout=max(1.0, float(timeout_seconds)),
            check=False,
        )
    except Exception:
        return {}
    frames = _decode_lsp_frames(proc.stdout or b"")
    if not frames:
        return {}

    rel_symbols: dict[str, list[dict[str, object]]] = {}
    for frame in frames:
        mid = frame.get("id")
        if not isinstance(mid, int) or mid not in req_map:
            continue
        result = frame.get("result")
        if not isinstance(result, list):
            continue
        flattened = _flatten_document_symbols(result)
        rel_symbols[req_map[mid]] = flattened

    positions: dict[str, tuple[int, int]] = {}
    for seed in seeds:
        seed_name = str(seed.get("name") or "").strip().lower()
        rel_path = str(seed.get("rel_path") or "")
        if not seed_name or not rel_path:
            continue
        symbols = rel_symbols.get(rel_path, [])
        exact = next((item for item in symbols if str(item.get("name") or "").strip().lower() == seed_name), None)
        candidate = exact
        if candidate is None:
            candidate = next((item for item in symbols if seed_name in str(item.get("name") or "").strip().lower()), None)
        if not isinstance(candidate, dict):
            continue
        start = _symbol_selection_start(candidate)
        if not start:
            continue
        key = str(seed.get("id") or "") or f"{seed_name}@{rel_path}"
        positions[key] = start
    unresolved: list[tuple[str, dict[str, object], str]] = []
    for seed in seeds:
        seed_name = str(seed.get("name") or "").strip().lower()
        rel_path = str(seed.get("rel_path") or "")
        if not seed_name or not rel_path:
            continue
        key = str(seed.get("id") or "") or f"{seed_name}@{rel_path}"
        if key not in positions:
            unresolved.append((key, seed, rel_path))
    if not unresolved:
        return positions

    outbound = []
    outbound.append(
        _encode_lsp_frame(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "processId": None,
                    "rootUri": root_uri,
                    "workspaceFolders": [{"uri": root_uri, "name": root.name or "workspace"}],
                    "capabilities": {},
                },
            }
        )
    )
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
    def_req_map: dict[int, tuple[str, str]] = {}
    def_req_id = 1600
    for key, seed, rel_path in unresolved:
        try:
            line = max(0, int(seed.get("start_line") or 1) - 1)
        except Exception:
            line = 0
        uri = (root / rel_path).resolve().as_uri()
        def_req_map[def_req_id] = (key, rel_path)
        outbound.append(
            _encode_lsp_frame(
                {
                    "jsonrpc": "2.0",
                    "id": def_req_id,
                    "method": "textDocument/definition",
                    "params": {
                        "textDocument": {"uri": uri},
                        "position": {"line": line, "character": 0},
                    },
                }
            )
        )
        def_req_id += 1
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "id": def_req_id, "method": "shutdown", "params": None}))
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "method": "exit", "params": {}}))
    try:
        def_proc = subprocess.run(
            command,
            input=b"".join(outbound),
            capture_output=True,
            timeout=max(1.0, float(timeout_seconds)),
            check=False,
        )
    except Exception:
        return positions
    def_frames = _decode_lsp_frames(def_proc.stdout or b"")
    if not def_frames:
        return positions
    for frame in def_frames:
        mid = frame.get("id")
        if not isinstance(mid, int) or mid not in def_req_map:
            continue
        key, seed_rel_path = def_req_map[mid]
        result = frame.get("result")
        candidates: list[object] = []
        if isinstance(result, list):
            candidates = result
        elif isinstance(result, dict):
            candidates = [result]
        if not candidates:
            continue
        parsed = [_extract_lsp_location_start(item, root) for item in candidates]
        parsed = [item for item in parsed if item is not None]
        if not parsed:
            continue
        same_file = next((item for item in parsed if item[0] == seed_rel_path), None)
        chosen = same_file or parsed[0]
        if not chosen:
            continue
        _, line, char = chosen
        positions[key] = (line, char)
    return positions


def _run_lsp_workspace_symbol_edges(
    command_text: str,
    root: Path,
    seeds: list[dict[str, object]],
    limit: int,
    timeout_seconds: float = 10.0,
) -> list[dict[str, object]]:
    command = _split_command(command_text)
    if not command or not seeds:
        return []
    root_uri = root.resolve().as_uri()
    request_ids: list[tuple[int, dict[str, object]]] = []
    next_id = 10

    outbound: list[bytes] = []
    outbound.append(
        _encode_lsp_frame(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "processId": None,
                    "rootUri": root_uri,
                    "workspaceFolders": [{"uri": root_uri, "name": root.name or "workspace"}],
                    "capabilities": {},
                },
            }
        )
    )
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
    for seed in seeds:
        seed_name = str(seed.get("name") or "").strip()
        if not seed_name:
            continue
        request_ids.append((next_id, seed))
        outbound.append(
            _encode_lsp_frame(
                {
                    "jsonrpc": "2.0",
                    "id": next_id,
                    "method": "workspace/symbol",
                    "params": {"query": seed_name},
                }
            )
        )
        next_id += 1
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "id": next_id, "method": "shutdown", "params": None}))
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "method": "exit", "params": {}}))
    payload = b"".join(outbound)

    try:
        proc = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            timeout=max(1.0, float(timeout_seconds)),
            check=False,
        )
    except Exception:
        return []
    frames = _decode_lsp_frames(proc.stdout or b"")
    if not frames:
        return []

    by_id: dict[int, object] = {}
    for message in frames:
        mid = message.get("id")
        if isinstance(mid, int) and "result" in message:
            by_id[mid] = message.get("result")

    edges: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for req_id, seed in request_ids:
        result = by_id.get(req_id)
        if not isinstance(result, list):
            continue
        for item in result:
            if not isinstance(item, dict):
                continue
            location = item.get("location")
            if not isinstance(location, dict):
                continue
            uri = str(location.get("uri") or "")
            abs_path = _path_from_uri(uri)
            rel_path = _rel_or_normalized_path(abs_path, root)
            if not rel_path:
                continue
            from_symbol = str(item.get("name") or Path(rel_path).stem)
            to_symbol = str(seed.get("name") or "")
            edge_type = "test_link" if _looks_like_test_path(rel_path) else "reference"
            key = (from_symbol, rel_path, to_symbol, edge_type)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "from_symbol_id": None,
                    "from_symbol": from_symbol,
                    "from_path": rel_path,
                    "from_kind": _lsp_kind_label(item.get("kind")),
                    "from_test_name": _looks_like_test_path(rel_path),
                    "to_symbol_id": seed.get("id"),
                    "to_symbol": to_symbol,
                    "to_path": seed.get("rel_path"),
                    "to_kind": seed.get("kind"),
                    "to_test_name": bool(seed.get("test_name")),
                    "edge_type": edge_type,
                    "evidence": "lsp workspace/symbol",
                    "confidence": "extracted",
                    "source_adapter": "lsp",
                }
            )
            if len(edges) >= limit:
                return edges
    return edges


def _run_lsp_text_document_references_edges(
    command_text: str,
    root: Path,
    seeds: list[dict[str, object]],
    limit: int,
    timeout_seconds: float = 10.0,
) -> list[dict[str, object]]:
    command = _split_command(command_text)
    if not command or not seeds:
        return []
    root_uri = root.resolve().as_uri()
    outbound: list[bytes] = []
    outbound.append(
        _encode_lsp_frame(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "processId": None,
                    "rootUri": root_uri,
                    "workspaceFolders": [{"uri": root_uri, "name": root.name or "workspace"}],
                    "capabilities": {},
                },
            }
        )
    )
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
    seed_positions = _resolve_lsp_seed_positions(
        command_text,
        root=root,
        seeds=seeds,
        timeout_seconds=timeout_seconds,
    )
    request_ids: list[tuple[int, dict[str, object]]] = []
    next_id = 200
    for seed in seeds:
        rel_path = str(seed.get("rel_path") or "")
        start_line = seed.get("start_line")
        if not rel_path or start_line is None:
            continue
        key = str(seed.get("id") or "") or f"{str(seed.get('name') or '').strip().lower()}@{rel_path}"
        start_pos = seed_positions.get(key)
        if start_pos:
            line = max(0, int(start_pos[0]))
            char = max(0, int(start_pos[1]))
        else:
            try:
                line = max(0, int(start_line) - 1)
            except Exception:
                continue
            char = 0
        seed_abs = (root / rel_path).resolve()
        request_ids.append((next_id, seed))
        outbound.append(
            _encode_lsp_frame(
                {
                    "jsonrpc": "2.0",
                    "id": next_id,
                    "method": "textDocument/references",
                    "params": {
                        "textDocument": {"uri": seed_abs.as_uri()},
                        "position": {"line": line, "character": char},
                        "context": {"includeDeclaration": True},
                    },
                }
            )
        )
        next_id += 1
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "id": next_id, "method": "shutdown", "params": None}))
    outbound.append(_encode_lsp_frame({"jsonrpc": "2.0", "method": "exit", "params": {}}))
    payload = b"".join(outbound)

    try:
        proc = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            timeout=max(1.0, float(timeout_seconds)),
            check=False,
        )
    except Exception:
        return []
    frames = _decode_lsp_frames(proc.stdout or b"")
    if not frames:
        return []
    by_id: dict[int, object] = {}
    for message in frames:
        mid = message.get("id")
        if isinstance(mid, int) and "result" in message:
            by_id[mid] = message.get("result")

    edges: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for req_id, seed in request_ids:
        result = by_id.get(req_id)
        if not isinstance(result, list):
            continue
        seed_rel = str(seed.get("rel_path") or "")
        try:
            seed_line = max(0, int(seed.get("start_line") or 1) - 1)
        except Exception:
            seed_line = -1
        seed_name = str(seed.get("name") or "")
        for item in result:
            if not isinstance(item, dict):
                continue
            uri = str(item.get("uri") or item.get("targetUri") or "")
            abs_path = _path_from_uri(uri)
            rel_path = _rel_or_normalized_path(abs_path, root)
            if not rel_path:
                continue
            range_obj = item.get("range") if isinstance(item.get("range"), dict) else item.get("targetSelectionRange")
            line = -1
            if isinstance(range_obj, dict):
                start = range_obj.get("start")
                if isinstance(start, dict):
                    try:
                        line = int(start.get("line"))
                    except Exception:
                        line = -1
            if rel_path == seed_rel and line == seed_line:
                continue
            from_symbol = Path(rel_path).stem
            edge_type = "test_link" if _looks_like_test_path(rel_path) else "reference"
            key = (from_symbol, rel_path, seed_name, edge_type)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "from_symbol_id": None,
                    "from_symbol": from_symbol,
                    "from_path": rel_path,
                    "from_kind": "symbol",
                    "from_test_name": _looks_like_test_path(rel_path),
                    "to_symbol_id": seed.get("id"),
                    "to_symbol": seed_name,
                    "to_path": seed_rel,
                    "to_kind": seed.get("kind"),
                    "to_test_name": bool(seed.get("test_name")),
                    "edge_type": edge_type,
                    "evidence": "lsp references",
                    "confidence": "extracted",
                    "source_adapter": "lsp",
                }
            )
            if len(edges) >= limit:
                return edges
    return edges


class SemanticSourceAdapter:
    name = "base"

    def collect_edges(
        self,
        workspace_id: str,
        seeds: list[dict[str, object]],
        depth: int = 1,
        limit: int = 200,
    ) -> dict[str, object]:
        raise NotImplementedError


class LspSemanticAdapter(SemanticSourceAdapter):
    name = "lsp"

    def _enabled(self) -> bool:
        value = (os.environ.get("CTX_ENGINE_SEMANTIC_LSP", "1") or "1").strip().lower()
        return value not in {"0", "false", "off", "no"}

    def collect_edges(
        self,
        workspace_id: str,
        seeds: list[dict[str, object]],
        depth: int = 1,
        limit: int = 200,
    ) -> dict[str, object]:
        if not self._enabled():
            return {
                "adapter": self.name,
                "available": False,
                "warning": "LSP semantic adapter disabled by CTX_ENGINE_SEMANTIC_LSP.",
                "edges": [],
            }
        if not seeds:
            return {"adapter": self.name, "available": True, "warning": None, "edges": []}
        external = self._load_client_edges(workspace_id, seeds, limit=max(1, min(int(limit), 1000)))
        if external:
            return {"adapter": self.name, "available": True, "warning": None, "edges": external}

        conn = init_db(connect())
        try:
            rows = conn.execute(
                """
                SELECT s.id, s.name, s.kind, s.signature, s.start_line, s.end_line,
                       s.route_like, s.test_name, s.imports_json,
                       f.rel_path, f.language
                FROM symbols s
                JOIN files f ON f.id = s.file_id
                WHERE s.workspace_id = ?
                """,
                (workspace_id,),
            ).fetchall()
            symbols = [dict(row) for row in rows]
        finally:
            conn.close()

        for row in symbols:
            row["imports"] = json.loads(str(row.get("imports_json") or "[]"))
            row["route_like"] = bool(row.get("route_like"))
            row["test_name"] = bool(row.get("test_name"))

        depth = max(1, min(int(depth), 3))
        edge_limit = max(1, min(int(limit), 1000))

        edges: list[dict[str, object]] = []
        seen: set[tuple[str, str, str, str]] = set()

        def add_edge(
            source: dict[str, object],
            target: dict[str, object],
            edge_type: str,
            evidence: str,
            confidence: str = "inferred",
        ) -> None:
            key = (str(source.get("id")), str(target.get("id")), edge_type, evidence)
            if key in seen:
                return
            seen.add(key)
            edges.append(
                {
                    "from_symbol_id": source.get("id"),
                    "from_symbol": source.get("name"),
                    "from_path": source.get("rel_path"),
                    "from_kind": source.get("kind"),
                    "from_test_name": bool(source.get("test_name")),
                    "to_symbol_id": target.get("id"),
                    "to_symbol": target.get("name"),
                    "to_path": target.get("rel_path"),
                    "to_kind": target.get("kind"),
                    "to_test_name": bool(target.get("test_name")),
                    "edge_type": edge_type,
                    "evidence": evidence,
                    "confidence": confidence,
                    "source_adapter": self.name,
                }
            )

        for seed in seeds:
            add_edge(seed, seed, "definition", "seed symbol definition", confidence="extracted")

        discovered: dict[str, dict[str, object]] = {}
        frontier: list[dict[str, object]] = []
        for seed in seeds:
            sid = str(seed.get("id") or "")
            if sid:
                discovered[sid] = seed
            if str(seed.get("name") or "").strip():
                frontier.append(seed)

        hop = 0
        while frontier and hop < depth and len(edges) < edge_limit:
            next_frontier: list[dict[str, object]] = []
            for target in frontier:
                token = _symbol_token(str(target.get("name") or ""))
                if not token:
                    continue
                for symbol in symbols:
                    if str(symbol.get("id")) == str(target.get("id")):
                        continue
                    imports_text = "\n".join(str(item) for item in symbol.get("imports") or [])
                    signature = str(symbol.get("signature") or "")
                    signature_and_imports = f"{signature}\n{imports_text}"
                    if not _term_in_text(token, signature_and_imports):
                        continue
                    if _term_in_text(token, imports_text):
                        edge_type = "import"
                        evidence = f"import contains {target.get('name')}"
                    elif bool(symbol.get("test_name")):
                        edge_type = "test_link"
                        evidence = f"test references {target.get('name')}"
                    elif bool(symbol.get("route_like")):
                        edge_type = "reference"
                        evidence = f"route-like symbol references {target.get('name')}"
                    else:
                        edge_type = "caller"
                        evidence = f"signature references {target.get('name')}"
                    add_edge(symbol, target, edge_type, evidence)
                    if edge_type == "caller":
                        add_edge(target, symbol, "callee", f"{target.get('name')} is used by {symbol.get('name')}")
                    sid = str(symbol.get("id") or "")
                    if hop + 1 < depth and sid and sid not in discovered:
                        discovered[sid] = symbol
                        next_frontier.append(symbol)
                    if len(edges) >= edge_limit:
                        break
                if len(edges) >= edge_limit:
                    break
            frontier = next_frontier
            hop += 1

        return {"adapter": self.name, "available": True, "warning": None, "edges": edges[:edge_limit]}

    def _load_client_edges(self, workspace_id: str, seeds: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
        workspace = get_workspace(workspace_id)
        if not workspace:
            return []
        root = Path(str(workspace.get("root_path") or "."))
        command_text = (os.environ.get("CTX_ENGINE_LSP_EDGE_COMMAND") or "").strip()
        rpc_command = (os.environ.get("CTX_ENGINE_LSP_RPC_COMMAND") or "").strip()
        session_command = (os.environ.get("CTX_ENGINE_LSP_CLIENT_COMMAND") or "").strip()
        override = (os.environ.get("CTX_ENGINE_LSP_EDGE_FILE") or "").strip()
        records: list[dict[str, object]] = []
        if command_text:
            records = _run_edge_command(
                command_text,
                {
                    "adapter": "lsp",
                    "workspace_id": workspace_id,
                    "root_path": str(root),
                    "seeds": seeds,
                    "limit": limit,
                },
                timeout_seconds=float(os.environ.get("CTX_ENGINE_LSP_EDGE_COMMAND_TIMEOUT", "8")),
            )
        if not records and rpc_command:
            rpc_method = (os.environ.get("CTX_ENGINE_LSP_RPC_METHOD") or "workspace/semanticEdges").strip() or "workspace/semanticEdges"
            records = _run_jsonrpc_edge_command(
                rpc_command,
                rpc_method,
                {
                    "workspace_id": workspace_id,
                    "root_path": str(root),
                    "seeds": seeds,
                    "limit": limit,
                },
                timeout_seconds=float(os.environ.get("CTX_ENGINE_LSP_RPC_TIMEOUT", "8")),
            )
        if not records and session_command:
            records = _run_lsp_workspace_symbol_edges(
                session_command,
                root=root,
                seeds=seeds,
                limit=limit,
                timeout_seconds=float(os.environ.get("CTX_ENGINE_LSP_CLIENT_TIMEOUT", "12")),
            )
            if len(records) < limit:
                ref_records = _run_lsp_text_document_references_edges(
                    session_command,
                    root=root,
                    seeds=seeds,
                    limit=max(1, limit - len(records)),
                    timeout_seconds=float(os.environ.get("CTX_ENGINE_LSP_CLIENT_TIMEOUT", "12")),
                )
                seen = {
                    (
                        str(item.get("from_symbol") or ""),
                        str(item.get("from_path") or ""),
                        str(item.get("to_symbol") or ""),
                        str(item.get("edge_type") or ""),
                    )
                    for item in records
                }
                for item in ref_records:
                    key = (
                        str(item.get("from_symbol") or ""),
                        str(item.get("from_path") or ""),
                        str(item.get("to_symbol") or ""),
                        str(item.get("edge_type") or ""),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    records.append(item)
                    if len(records) >= limit:
                        break
        candidates = []
        if override:
            candidates.append(Path(override))
        candidates.extend(
            [
                root / ".ctx-engine" / "lsp_edges.jsonl",
                root / ".ctx-engine" / "lsp_edges.json",
            ]
        )
        if not records:
            path = next((item for item in candidates if item.exists() and item.is_file()), None)
            if not path:
                return []
            try:
                records = _read_records_from_file(path)
            except Exception:
                return []
        seed_ids = {str(seed.get("id")) for seed in seeds if seed.get("id")}
        seed_names = {str(seed.get("name") or "") for seed in seeds}
        edges: list[dict[str, object]] = []

        for record in records:
            from_id = str(record.get("from_symbol_id") or "")
            to_id = str(record.get("to_symbol_id") or "")
            from_name = str(record.get("from_symbol") or "")
            to_name = str(record.get("to_symbol") or "")
            touches_seed = from_id in seed_ids or to_id in seed_ids or from_name in seed_names or to_name in seed_names
            if not touches_seed:
                continue
            edges.append(_normalize_edge_record(record, self.name, "lsp client edge", "extracted"))
            if len(edges) >= limit:
                break
        return edges


class ScipSemanticAdapter(SemanticSourceAdapter):
    name = "scip"

    def _enabled(self) -> bool:
        value = (os.environ.get("CTX_ENGINE_SEMANTIC_SCIP", "0") or "0").strip().lower()
        return value in {"1", "true", "on", "yes"}

    def collect_edges(
        self,
        workspace_id: str,
        seeds: list[dict[str, object]],
        depth: int = 1,
        limit: int = 200,
    ) -> dict[str, object]:
        if not self._enabled():
            return {
                "adapter": self.name,
                "available": False,
                "warning": "SCIP semantic adapter disabled by default.",
                "edges": [],
            }
        if not seeds:
            return {"adapter": self.name, "available": True, "warning": None, "edges": []}
        real_edges = self._load_scip_edges(workspace_id, seeds, limit=max(1, min(int(limit), 1000)))
        if real_edges:
            return {"adapter": self.name, "available": True, "warning": None, "edges": real_edges}
        conn = init_db(connect())
        try:
            rows = conn.execute(
                """
                SELECT s.id, s.name, s.kind, s.signature, s.start_line, s.end_line,
                       s.imports_json,
                       s.route_like, s.test_name, f.rel_path, f.language
                FROM symbols s
                JOIN files f ON f.id = s.file_id
                WHERE s.workspace_id = ?
                """,
                (workspace_id,),
            ).fetchall()
            symbols = [dict(row) for row in rows]
        finally:
            conn.close()

        edge_limit = max(1, min(int(limit), 1000))
        edges: list[dict[str, object]] = []
        seen: set[tuple[str, str, str]] = set()
        for seed in seeds:
            seed_id = str(seed.get("id") or "")
            seed_name = str(seed.get("name") or "")
            token = _symbol_token(seed_name)
            if not seed_id or not token:
                continue
            for symbol in symbols:
                symbol_id = str(symbol.get("id") or "")
                if not symbol_id or symbol_id == seed_id:
                    continue
                signature = str(symbol.get("signature") or "")
                imports_text = "\n".join(json.loads(str(symbol.get("imports_json") or "[]")))
                signature_and_imports = f"{signature}\n{imports_text}"
                if not _term_in_text(token, signature_and_imports):
                    continue
                key = (symbol_id, seed_id, "reference")
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    {
                        "from_symbol_id": symbol_id,
                        "from_symbol": symbol.get("name"),
                        "from_path": symbol.get("rel_path"),
                        "from_kind": symbol.get("kind"),
                        "from_test_name": bool(symbol.get("test_name")),
                        "to_symbol_id": seed_id,
                        "to_symbol": seed_name,
                        "to_path": seed.get("rel_path"),
                        "to_kind": seed.get("kind"),
                        "to_test_name": bool(seed.get("test_name")),
                        "edge_type": "reference",
                        "evidence": f"scip lexical reference to {seed_name}",
                        "confidence": "ambiguous",
                        "source_adapter": self.name,
                    }
                )
                if len(edges) >= edge_limit:
                    break
            if len(edges) >= edge_limit:
                break

        return {
            "adapter": self.name,
            "available": True,
            "warning": None,
            "edges": edges,
        }

    def _load_scip_edges(self, workspace_id: str, seeds: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
        workspace = get_workspace(workspace_id)
        if not workspace:
            return []
        root = Path(str(workspace.get("root_path") or "."))
        command_text = (os.environ.get("CTX_ENGINE_SCIP_EDGE_COMMAND") or "").strip()
        override = (os.environ.get("CTX_ENGINE_SCIP_EDGE_FILE") or "").strip()
        records: list[dict[str, object]] = []
        if command_text:
            records = _run_edge_command(
                command_text,
                {
                    "adapter": "scip",
                    "workspace_id": workspace_id,
                    "root_path": str(root),
                    "seeds": seeds,
                    "limit": limit,
                },
                timeout_seconds=float(os.environ.get("CTX_ENGINE_SCIP_EDGE_COMMAND_TIMEOUT", "8")),
            )
        candidates = []
        if override:
            candidates.append(Path(override))
        candidates.extend(
            [
                root / ".scip" / "edges.jsonl",
                root / ".scip" / "edges.json",
                root / "scip_edges.jsonl",
            ]
        )
        if not records:
            path = next((item for item in candidates if item.exists() and item.is_file()), None)
            if path:
                try:
                    records = _read_records_from_file(path)
                except Exception:
                    records = []
        if not records:
            native = self._load_scip_index_edges(root, seeds, limit)
            if native:
                return native
            return []
        seed_ids = {str(seed.get("id")) for seed in seeds if seed.get("id")}
        seed_names = {str(seed.get("name") or "") for seed in seeds}

        edges: list[dict[str, object]] = []
        for record in records:
            from_id = str(record.get("from_symbol_id") or "")
            to_id = str(record.get("to_symbol_id") or "")
            from_name = str(record.get("from_symbol") or "")
            to_name = str(record.get("to_symbol") or "")
            touches_seed = from_id in seed_ids or to_id in seed_ids or from_name in seed_names or to_name in seed_names
            if not touches_seed:
                continue
            edges.append(_normalize_edge_record(record, self.name, "scip edge", "inferred"))
            if len(edges) >= limit:
                break
        return edges

    def _load_scip_index_edges(self, root: Path, seeds: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
        override = (os.environ.get("CTX_ENGINE_SCIP_INDEX_FILE") or "").strip()
        index_candidates: list[Path] = []
        if override:
            index_candidates.append(Path(override))
        index_candidates.extend([root / ".scip" / "index.scip", root / "index.scip"])
        index_path = next((item for item in index_candidates if item.exists() and item.is_file()), None)
        if not index_path:
            return []
        command_text = (os.environ.get("CTX_ENGINE_SCIP_PRINT_COMMAND") or "scip").strip() or "scip"
        command = _split_command(command_text)
        if not command:
            return []
        if "{index_path}" in command_text:
            rendered = command_text.replace("{index_path}", str(index_path))
            command = _split_command(rendered)
        else:
            command.extend(["print", "--json", str(index_path)])
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=max(1.0, float(os.environ.get("CTX_ENGINE_SCIP_PRINT_TIMEOUT", "12"))),
                check=False,
            )
        except Exception:
            return []
        if proc.returncode != 0 or not str(proc.stdout or "").strip():
            return []
        try:
            payload = json.loads(proc.stdout)
        except Exception:
            return []
        return self._edges_from_scip_payload(payload, seeds, limit)

    def _edges_from_scip_payload(self, payload: object, seeds: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
        if not isinstance(payload, dict):
            return []
        documents = payload.get("documents")
        if not isinstance(documents, list):
            return []
        seed_by_name: dict[str, dict[str, object]] = {}
        for seed in seeds:
            seed_name = str(seed.get("name") or "").strip().lower()
            if seed_name and seed_name not in seed_by_name:
                seed_by_name[seed_name] = seed
        if not seed_by_name:
            return []
        edges: list[dict[str, object]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for document in documents:
            if not isinstance(document, dict):
                continue
            rel_path = str(document.get("relative_path") or "")
            occurrences = document.get("occurrences")
            if not rel_path or not isinstance(occurrences, list):
                continue
            definition_names: list[str] = []
            for occ in occurrences:
                if not isinstance(occ, dict):
                    continue
                symbol = str(occ.get("symbol") or "")
                if not symbol:
                    continue
                symbol_name = _scip_symbol_name(symbol).lower()
                if not symbol_name:
                    continue
                roles_raw = occ.get("symbol_roles", 0)
                try:
                    roles = int(roles_raw)
                except Exception:
                    roles = 0
                if roles & 1:
                    definition_names.append(symbol_name)
            doc_caller = next((name for name in definition_names if name), "")
            for occ in occurrences:
                if not isinstance(occ, dict):
                    continue
                symbol = str(occ.get("symbol") or "")
                symbol_name = _scip_symbol_name(symbol).lower()
                if symbol_name not in seed_by_name:
                    continue
                seed = seed_by_name[symbol_name]
                caller = doc_caller if doc_caller and doc_caller != symbol_name else f"{Path(rel_path).stem}"
                edge_type = "test_link" if _looks_like_test_path(rel_path) else "reference"
                key = (caller, rel_path, str(seed.get("name") or symbol_name), edge_type)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    {
                        "from_symbol_id": None,
                        "from_symbol": caller,
                        "from_path": rel_path,
                        "from_kind": "function" if doc_caller else "file",
                        "from_test_name": _looks_like_test_path(rel_path),
                        "to_symbol_id": seed.get("id"),
                        "to_symbol": seed.get("name") or symbol_name,
                        "to_path": seed.get("rel_path"),
                        "to_kind": seed.get("kind"),
                        "to_test_name": bool(seed.get("test_name")),
                        "edge_type": edge_type,
                        "evidence": "scip print occurrence",
                        "confidence": "extracted",
                        "source_adapter": self.name,
                    }
                )
                if len(edges) >= limit:
                    return edges
        return edges


class SemanticSourceRouter:
    def __init__(self) -> None:
        self.adapters: list[SemanticSourceAdapter] = [LspSemanticAdapter(), ScipSemanticAdapter()]

    @staticmethod
    def _adapter_weight(adapter_name: str) -> float:
        value = os.environ.get(f"CTX_ENGINE_SEMANTIC_WEIGHT_{adapter_name.upper()}")
        if value is None:
            defaults = {"lsp": 1.0, "scip": 0.8}
            return defaults.get(adapter_name.lower(), 1.0)
        try:
            return max(0.0, float(value))
        except Exception:
            return 1.0

    @staticmethod
    def _confidence_weight(confidence: str) -> float:
        lowered = (confidence or "").strip().lower()
        if lowered == "extracted":
            return 1.0
        if lowered == "inferred":
            return 0.7
        return 0.4

    def collect_edges(
        self,
        workspace_id: str,
        seeds: list[dict[str, object]],
        depth: int = 1,
        limit: int = 200,
    ) -> dict[str, object]:
        adapter_reports: list[dict[str, object]] = []
        merged: list[dict[str, object]] = []
        seed_ids = {str(item.get("id")) for item in seeds if item.get("id")}
        seed_names = {str(item.get("name") or "") for item in seeds if str(item.get("name") or "")}
        for adapter in self.adapters:
            report = adapter.collect_edges(workspace_id, seeds, depth=depth, limit=limit)
            adapter_reports.append(
                {
                    "adapter": report.get("adapter", adapter.name),
                    "available": bool(report.get("available")),
                    "warning": report.get("warning"),
                    "edge_count": len(report.get("edges", [])),
                }
            )
            adapter_name = str(report.get("adapter", adapter.name))
            weight = self._adapter_weight(adapter_name)
            for edge in list(report.get("edges", [])):
                edge_copy = dict(edge)
                confidence = str(edge_copy.get("confidence") or "inferred")
                from_id = str(edge_copy.get("from_symbol_id") or "")
                to_id = str(edge_copy.get("to_symbol_id") or "")
                from_name = str(edge_copy.get("from_symbol") or "")
                to_name = str(edge_copy.get("to_symbol") or "")
                touches_seed = (
                    from_id in seed_ids
                    or to_id in seed_ids
                    or from_name in seed_names
                    or to_name in seed_names
                )
                score = weight * self._confidence_weight(confidence)
                # Keep non-seed edges available for diagnostics, but rank them lower.
                if not touches_seed:
                    score -= 0.25
                edge_copy["touches_seed"] = touches_seed
                edge_copy["semantic_score"] = round(score, 4)
                merged.append(edge_copy)
            if len(merged) >= limit:
                break
        merged.sort(key=lambda item: (float(item.get("semantic_score", 0.0)), str(item.get("edge_type") or "")), reverse=True)
        return {
            "status": "ok",
            "adapters": adapter_reports,
            "edges": merged[: max(1, min(int(limit), 1000))],
        }
