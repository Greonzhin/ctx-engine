from __future__ import annotations

from .symbols import SymbolRecord


def build_skeleton(text: str, symbols: list[SymbolRecord], imports: list[str], limit: int = 120) -> str:
    lines: list[str] = []
    for item in imports[:40]:
        lines.append(item.strip())
    if imports and symbols:
        lines.append("")
    for symbol in sorted(symbols, key=lambda s: (s.start_line, s.name)):
        prefix = f"{symbol.kind} "
        line = f"{prefix}{symbol.signature or symbol.name}  # L{symbol.start_line}"
        if symbol.route_like:
            line += " route"
        if symbol.test_name:
            line += " test"
        lines.append(line)
        if len(lines) >= limit:
            lines.append("... skeleton truncated")
            break
    if not lines:
        for raw in text.splitlines()[: min(limit, 40)]:
            stripped = raw.strip()
            if stripped:
                lines.append(stripped[:200])
    return "\n".join(lines)


def snippet_around(text: str, start_line: int, end_line: int, radius: int = 4) -> dict[str, object]:
    lines = text.splitlines()
    start = max(1, start_line - radius)
    end = min(len(lines), end_line + radius)
    body = "\n".join(f"{idx}: {lines[idx - 1]}" for idx in range(start, end + 1))
    return {"start_line": start, "end_line": end, "text": body}
