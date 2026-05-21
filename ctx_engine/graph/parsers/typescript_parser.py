from __future__ import annotations

from .javascript_parser import JavaScriptParser


class TypeScriptParser(JavaScriptParser):
    language = "typescript"
    tree_sitter_language = "typescript"
