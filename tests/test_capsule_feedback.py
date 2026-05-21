from __future__ import annotations

import json

from ctx_engine.capsule.builder import CapsuleBuilder
from ctx_engine.cli import main
from ctx_engine.providers.capsule_feedback import CapsuleFeedbackProvider
from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.local_docs import LocalDocsProvider


def test_capsule_feedback_record_and_report():
    provider = CapsuleFeedbackProvider()

    result = provider.record(
        "cap-1",
        "partial",
        workspace_id="ws-1",
        client_id="test",
        useful_files=["app/auth.py", "app/auth.py"],
        missing_files=["tests/test_auth.py"],
        notes="needs test context",
    )
    report = provider.report("cap-1")

    assert result["status"] == "ok"
    assert result["rating"] == "partial"
    assert result["useful_files"] == ["app/auth.py"]
    assert report["summary"]["feedback_count"] == 1
    assert report["summary"]["rating_counts"]["partial"] == 1
    assert report["summary"]["top_missing_files"][0]["path"] == "tests/test_auth.py"


def test_capsule_feedback_cli_record_and_report(capsys):
    assert main(["feedback", "record", "cap-2", "--rating", "useful", "--useful-file", "app.py"]) == 0
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["capsule_id"] == "cap-2"

    assert main(["feedback", "report", "cap-2"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["feedback_count"] == 1
    assert report["feedback"][0]["ledger_id"]


def test_capsule_includes_feedback_summary(fixture_root):
    root = fixture_root / "python_app"
    result = CodeGraphProvider().index_repository(root)
    LocalDocsProvider().index(root, result["workspace_id"])

    first = CapsuleBuilder().build("where is auth handled?", token_budget=1200, workspace_id=result["workspace_id"])
    capsule_id = str(first["provenance"]["capsule_id"])
    CapsuleFeedbackProvider().record(capsule_id, "useful", workspace_id=result["workspace_id"])

    second = CapsuleBuilder().build("where is auth handled?", token_budget=1200, workspace_id=result["workspace_id"])

    assert first["feedback_context"]["feedback_count"] == 0
    assert second["cache"] == "hit"
    assert second["feedback_context"]["feedback_count"] == 1
    assert second["feedback_context"]["latest_rating"] == "useful"
