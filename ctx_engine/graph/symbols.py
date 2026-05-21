from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SymbolRecord:
    name: str
    kind: str
    signature: str
    start_line: int
    end_line: int
    container: str | None = None
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    route_like: bool = False
    test_name: bool = False


@dataclass(frozen=True)
class ParsedFile:
    language: str
    imports: list[str]
    exports: list[str]
    symbols: list[SymbolRecord]
    parser_backend: str
