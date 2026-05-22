from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.identity import issue_capability_token, list_capability_tokens, revoke_capability_token, verify_capability_token


def test_capability_token_issue_verify_list_and_revoke():
    issued = issue_capability_token("agent-a", client_id="codex", capabilities=["read_context"], ttl_minutes=5)
    token = issued["token"]
    token_id = issued["token_record"]["id"]

    assert token.startswith("ctxcap_")
    assert issued["token_record"]["capabilities"] == ["read_context"]

    verified = verify_capability_token(token, capability="read_context")
    assert verified["valid"] is True
    assert verified["token_record"]["id"] == token_id

    denied = verify_capability_token(token, capability="write_memory")
    assert denied["valid"] is False
    assert "capability not granted: write_memory" in denied["errors"]

    listed = list_capability_tokens()
    assert any(item["id"] == token_id for item in listed["tokens"])

    revoked = revoke_capability_token(token_id)
    assert revoked["status"] == "ok"
    assert revoked["token_record"]["revoked_at"]
    assert verify_capability_token(token)["valid"] is False


def test_identity_cli_issue_verify_revoke(capsys):
    assert main(["identity", "issue", "agent-cli", "--client-id", "codex", "--capability", "read_context", "--ttl-minutes", "5"]) == 0
    issued = json.loads(capsys.readouterr().out)
    token = issued["token"]
    token_id = issued["token_record"]["id"]

    assert main(["identity", "verify", token, "--capability", "read_context"]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True

    assert main(["identity", "revoke", token_id]) == 0
    revoked = json.loads(capsys.readouterr().out)
    assert revoked["status"] == "ok"

    assert main(["identity", "verify", token]) == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["valid"] is False


def test_identity_cli_list(capsys):
    issue_capability_token("agent-list", capabilities=["read_docs"])

    assert main(["identity", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["status"] == "ok"
    assert "tokens" in listed
