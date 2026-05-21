from __future__ import annotations

import math


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def rank_text(query: str, text: str, path: str = "") -> float:
    terms = [term.lower() for term in query.replace("_", " ").split() if term.strip()]
    haystack = f"{path}\n{text}".lower()
    if not terms:
        return 0.0
    score = sum(1.0 for term in terms if term in haystack)
    score += sum(haystack.count(term) * 0.2 for term in terms)
    if any(term in path.lower() for term in terms):
        score += 1.5
    return score


def fit_budget(items: list[dict[str, object]], budget: int, text_key: str = "text") -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    selected: list[dict[str, object]] = []
    omitted: list[dict[str, object]] = []
    used = 0
    for item in items:
        text = str(item.get(text_key, ""))
        tokens = int(item.get("token_estimate") or estimate_tokens(text))
        item["token_estimate"] = tokens
        if used + tokens <= budget:
            selected.append(item)
            used += tokens
        else:
            omitted.append(item)
    return selected, omitted
