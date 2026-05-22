from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import connect, init_db, now_iso, stable_json


ALLOWED_CAPABILITIES = (
    "read_context",
    "read_docs",
    "read_memory",
    "write_memory",
    "inspect_runtime",
    "export_context",
)

DEFAULT_CAPABILITIES = ("read_context", "read_docs", "read_memory", "inspect_runtime")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _token_id(token_hash: str) -> str:
    return token_hash[:20]


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _normalize_capabilities(values: list[str] | None) -> list[str]:
    selected = values or list(DEFAULT_CAPABILITIES)
    normalized: list[str] = []
    for value in selected:
        item = value.strip().lower()
        if item not in ALLOWED_CAPABILITIES:
            raise ValueError(f"unsupported capability: {value}")
        if item not in normalized:
            normalized.append(item)
    return normalized


def issue_capability_token(
    agent_id: str,
    client_id: str = "generic",
    capabilities: list[str] | None = None,
    ttl_minutes: int = 60,
    workspace_id: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    if not agent_id.strip():
        raise ValueError("agent_id is required")
    ttl = max(1, int(ttl_minutes))
    issued = datetime.now(timezone.utc)
    expires = issued + timedelta(minutes=ttl)
    token = f"ctxcap_{secrets.token_urlsafe(32)}"
    token_hash = _hash_token(token)
    token_id = _token_id(token_hash)
    selected = _normalize_capabilities(capabilities)

    conn = init_db(connect())
    try:
        conn.execute(
            """
            INSERT INTO capability_tokens(
              id, token_hash, agent_id, client_id, workspace_id, capabilities_json,
              issued_at, expires_at, revoked_at, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token_id,
                token_hash,
                agent_id.strip(),
                client_id.strip() or "generic",
                workspace_id,
                stable_json(selected),
                issued.isoformat(),
                expires.isoformat(),
                None,
                note,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "ok",
        "token": token,
        "token_record": {
            "id": token_id,
            "agent_id": agent_id.strip(),
            "client_id": client_id.strip() or "generic",
            "workspace_id": workspace_id,
            "capabilities": selected,
            "issued_at": issued.isoformat(),
            "expires_at": expires.isoformat(),
            "revoked_at": None,
            "note": note,
        },
        "warnings": [
            "Capability tokens are local advisory credentials and are not enforced by the MCP gateway yet.",
            "The token secret is shown once; store it outside repository files.",
        ],
    }


def _row(row) -> dict[str, Any]:
    data = dict(row)
    data["capabilities"] = json.loads(data.pop("capabilities_json") or "[]")
    data.pop("token_hash", None)
    return data


def list_capability_tokens(include_revoked: bool = False, limit: int = 50) -> dict[str, Any]:
    conn = init_db(connect())
    try:
        if include_revoked:
            rows = conn.execute(
                "SELECT * FROM capability_tokens ORDER BY issued_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM capability_tokens WHERE revoked_at IS NULL ORDER BY issued_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    tokens = [_row(row) for row in rows]
    return {"status": "ok", "count": len(tokens), "tokens": tokens}


def verify_capability_token(token: str, capability: str | None = None) -> dict[str, Any]:
    token_hash = _hash_token(token)
    conn = init_db(connect())
    try:
        row = conn.execute("SELECT * FROM capability_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
    finally:
        conn.close()
    if not row:
        return {"status": "fail", "valid": False, "errors": ["capability token not found"]}

    record = _row(row)
    errors: list[str] = []
    now = datetime.now(timezone.utc)
    if record.get("revoked_at"):
        errors.append("capability token is revoked")
    try:
        if _parse_time(str(record["expires_at"])) <= now:
            errors.append("capability token is expired")
    except Exception:
        errors.append("capability token has invalid expiry")
    if capability:
        requested = capability.strip().lower()
        if requested not in ALLOWED_CAPABILITIES:
            errors.append(f"unsupported capability: {capability}")
        elif requested not in record.get("capabilities", []):
            errors.append(f"capability not granted: {requested}")

    return {
        "status": "fail" if errors else "ok",
        "valid": not errors,
        "token_record": record,
        "required_capability": capability,
        "errors": errors,
    }


def revoke_capability_token(token_id: str) -> dict[str, Any]:
    conn = init_db(connect())
    try:
        row = conn.execute("SELECT * FROM capability_tokens WHERE id = ?", (token_id,)).fetchone()
        if not row:
            return {"status": "fail", "errors": [f"capability token not found: {token_id}"]}
        revoked_at = now_iso()
        conn.execute("UPDATE capability_tokens SET revoked_at = ? WHERE id = ?", (revoked_at, token_id))
        conn.commit()
        updated = conn.execute("SELECT * FROM capability_tokens WHERE id = ?", (token_id,)).fetchone()
    finally:
        conn.close()
    return {"status": "ok", "token_record": _row(updated)}
