from __future__ import annotations

from abc import ABC, abstractmethod

from ..symbols import ParsedFile


class SourceParser(ABC):
    language: str

    @abstractmethod
    def parse(self, text: str, path: str) -> ParsedFile:
        raise NotImplementedError


def tree_sitter_available(language: str, text: str) -> bool:
    try:
        from tree_sitter_language_pack import get_parser

        parser = get_parser(language)
        parser.parse(text)
        return True
    except Exception:
        return False


def parse_tree(language: str, text: str):
    try:
        from tree_sitter_language_pack import get_parser

        parser = get_parser(language)
        return parser.parse(text)
    except Exception:
        return None


def node_value(node, name: str):
    value = getattr(node, name, None)
    if callable(value):
        return value()
    return value


def node_text(text: str, node) -> str:
    try:
        start = int(node_value(node, "start_byte") or 0)
        end = int(node_value(node, "end_byte") or 0)
        return text[start:end]
    except Exception:
        return ""


def point_row(value) -> int:
    if isinstance(value, (list, tuple)) and value:
        return int(value[0])
    row = getattr(value, "row", None)
    if row is not None:
        return int(row)
    line = getattr(value, "line", None)
    if line is not None:
        return int(line)
    return 0
