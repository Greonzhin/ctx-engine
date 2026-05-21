from __future__ import annotations

import json

from ctx_engine.capsule.builder import CapsuleBuilder
from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.local_docs import LocalDocsProvider


def test_sensitive_files_are_excluded_and_redacted(fixture_root):
    root = fixture_root / "secret_leak_repo"
    result = CodeGraphProvider().index_repository(root)
    LocalDocsProvider().index(root, result["workspace_id"])
    capsule = CapsuleBuilder().build("read env", workspace_id=result["workspace_id"])
    text = json.dumps(capsule)
    assert "sk-test-secret" not in text
    assert ".env" not in text
