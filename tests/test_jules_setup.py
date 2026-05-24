from __future__ import annotations

from pathlib import Path


def test_jules_bolt_setup_files_exist_and_match_repo():
    root = Path(__file__).resolve().parents[1]
    setup = (root / ".jules" / "setup.sh").read_text(encoding="utf-8")
    journal = (root / ".jules" / "bolt.md").read_text(encoding="utf-8")
    runbook = (root / "docs" / "runbooks" / "jules-bolt.md").read_text(encoding="utf-8")

    assert 'python -m pip install -e ".[dev]"' in setup
    assert "python -m pytest -q" in setup
    assert "pnpm" not in setup
    assert "No critical performance learnings" in journal
    assert "Jules runs tasks in a short-lived Ubuntu VM" in runbook
    assert "Do not use `pnpm lint` or `pnpm test` for the main repo" in runbook
    assert "Proceed without asking for a user-selected bottleneck" in runbook
