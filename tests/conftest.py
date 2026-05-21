from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("CTX_ENGINE_DATA_DIR", str(data))
    monkeypatch.delenv("CTX_ENGINE_DB", raising=False)
    monkeypatch.delenv("CTX_ENGINE_CONTEXT7_LIVE", raising=False)
    return data


@pytest.fixture
def fixture_root() -> Path:
    return Path(__file__).resolve().parent / "fixtures"
