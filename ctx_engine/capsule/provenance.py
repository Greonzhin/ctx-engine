from __future__ import annotations

from pathlib import Path

from ..db import now_iso
from ..integrations.rtk import estimate_tokens


def provenance(
    provider: str,
    path_or_url: str,
    line: str | int | None = None,
    hash_value: str | None = None,
    trust_tier: str = "local_code",
    text: str = "",
    version: str | None = None,
    confidence_label: str = "extracted",
) -> dict[str, object]:
    return {
        "provider": provider,
        "path": path_or_url,
        "line": line,
        "hash": hash_value,
        "version": version,
        "retrieved_at": now_iso(),
        "trust_tier": trust_tier,
        "confidence_label": confidence_label,
        "token_estimate": estimate_tokens(text),
    }


def file_label(path: str) -> str:
    return Path(path).as_posix()
