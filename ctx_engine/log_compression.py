from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .integrations.rtk import estimate_tokens


FAILURE_PATTERNS = (
    re.compile(r"FAILED\s+[\w./\\:-]+", re.IGNORECASE),
    re.compile(r"\b(ERROR|FAIL|FAILED|AssertionError|Traceback|Exception|PermissionError)\b", re.IGNORECASE),
    re.compile(r"\bnpm ERR!\b", re.IGNORECASE),
    re.compile(r"\b(vitest|jest|pytest)\b.*\b(fail|failed|error)\b", re.IGNORECASE),
    re.compile(r"\b(docker|compose|container)\b.*\b(error|failed|denied)\b", re.IGNORECASE),
    re.compile(r"^#\d+\s+ERROR", re.IGNORECASE),
)
WARNING_PATTERNS = (
    re.compile(r"\bwarning\b", re.IGNORECASE),
    re.compile(r"\bdeprecated\b", re.IGNORECASE),
)


def compress_log_text(text: str, max_lines: int = 80) -> dict[str, Any]:
    lines = text.splitlines()
    kept: list[dict[str, Any]] = []
    warnings: list[str] = []
    failures: list[str] = []
    seen: set[int] = set()

    for index, line in enumerate(lines, start=1):
        if any(pattern.search(line) for pattern in FAILURE_PATTERNS):
            failures.append(line.strip())
            _keep_context(lines, index, seen)
        elif any(pattern.search(line) for pattern in WARNING_PATTERNS):
            warnings.append(line.strip())
            seen.add(index)

    for index in sorted(seen):
        if len(kept) >= max_lines:
            break
        kept.append({"line": index, "text": lines[index - 1]})

    if not kept and lines:
        for index, line in enumerate(lines[: min(len(lines), 12)], start=1):
            kept.append({"line": index, "text": line})

    kept_text = "\n".join(str(item["text"]) for item in kept)
    summary = _summary(failures, warnings, len(lines), len(kept))
    return {
        "status": "ok",
        "raw_bytes": len(text.encode("utf-8")),
        "raw_lines": len(lines),
        "compressed_tokens": estimate_tokens(kept_text),
        "summary": summary,
        "failures": _dedupe(failures)[:20],
        "warnings": _dedupe(warnings)[:20],
        "kept_lines": kept,
    }


def compress_log_file(path: str | Path, max_lines: int = 80) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    result = compress_log_text(text, max_lines=max_lines)
    result["source"] = str(Path(path).resolve())
    return result


def _keep_context(lines: list[str], line_number: int, seen: set[int]) -> None:
    for offset in range(-2, 3):
        selected = line_number + offset
        if 1 <= selected <= len(lines):
            seen.add(selected)


def _summary(failures: list[str], warnings: list[str], raw_lines: int, kept_lines: int) -> str:
    if failures:
        return f"Detected {len(_dedupe(failures))} failure/error signals and kept {kept_lines} of {raw_lines} lines."
    if warnings:
        return f"Detected {len(_dedupe(warnings))} warning signals and kept {kept_lines} of {raw_lines} lines."
    return f"No explicit failure signal detected; kept {kept_lines} of {raw_lines} lines."


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
