from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.log_compression import compress_log_text


def test_compress_log_keeps_pytest_failure_and_traceback():
    text = """
tests/test_auth.py::test_authenticate_request_accepts_valid_token FAILED
================================ FAILURES =================================
FAILED tests/test_auth.py::test_authenticate_request_accepts_valid_token
Traceback (most recent call last):
  File "tests/test_auth.py", line 3, in test_authenticate_request_accepts_valid_token
AssertionError: expected valid token
"""

    result = compress_log_text(text)

    assert result["status"] == "ok"
    assert any("FAILED tests/test_auth.py" in item for item in result["failures"])
    assert any("Traceback" in item["text"] for item in result["kept_lines"])
    assert result["compressed_tokens"] > 0


def test_compress_log_keeps_docker_error():
    text = """
#12 3.4 RUN pip install .
#12 ERROR: process "/bin/sh -c pip install ." did not complete successfully
docker compose failed with PermissionError: denied
"""

    result = compress_log_text(text)

    assert any("#12 ERROR" in item for item in result["failures"])
    assert any("docker compose failed" in item for item in result["failures"])


def test_compress_log_cli_file_and_stdin(tmp_path, monkeypatch, capsys):
    log = tmp_path / "failure.log"
    log.write_text("FAILED tests/test_auth.py::test_auth\nAssertionError: nope\n", encoding="utf-8")

    assert main(["compress-log", str(log)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"].endswith("failure.log")

    monkeypatch.setattr("sys.stdin.read", lambda: "Traceback (most recent call last):\nException: nope\n")
    assert main(["compress-log"]) == 0
    stdin_payload = json.loads(capsys.readouterr().out)
    assert stdin_payload["source"] == "stdin"
