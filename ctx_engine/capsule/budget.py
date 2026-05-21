from __future__ import annotations

from ..integrations.rtk import estimate_tokens, fit_budget


def reserve_budget(total: int) -> dict[str, int]:
    total = max(500, int(total))
    return {
        "symbols": max(150, int(total * 0.18)),
        "skeletons": max(250, int(total * 0.24)),
        "snippets": max(300, int(total * 0.28)),
        "docs": max(150, int(total * 0.15)),
        "memory": max(100, int(total * 0.08)),
        "build": max(80, int(total * 0.04)),
    }


__all__ = ["estimate_tokens", "fit_budget", "reserve_budget"]
