from __future__ import annotations

import re

from .base import SourceParser, node_text, node_value, parse_tree, point_row, tree_sitter_available
from ..symbols import ParsedFile, SymbolRecord

IMPORT_RE = re.compile(r"^\s*(import\b.+|const\s+\w+\s*=\s*require\(.+\))")
EXPORT_RE = re.compile(r"^\s*export\s+")
CLASS_RE = re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)")
FUNC_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")
CONST_FUNC_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"
)
ROUTE_RE = re.compile(r"\b(?:app|router)\.(get|post|put|patch|delete|route)\s*\(")
TEST_RE = re.compile(r"\b(test|it|describe)\s*\(\s*['\"]([^'\"]+)")


class JavaScriptParser(SourceParser):
    language = "javascript"
    tree_sitter_language = "javascript"

    def parse(self, text: str, path: str) -> ParsedFile:
        use_tree = tree_sitter_available(self.tree_sitter_language, text)
        backend = "tree-sitter+regex" if use_tree else "regex"
        imports: list[str] = []
        exports: list[str] = []
        symbols: list[SymbolRecord] = []
        lines = text.splitlines()
        seen: set[tuple[str, int]] = set()

        if use_tree:
            tree = parse_tree(self.tree_sitter_language, text)
            root = tree.root_node() if tree is not None else None
            if root is not None:
                stack = [root]
                while stack:
                    node = stack.pop()
                    child_count = int(node_value(node, "named_child_count") or 0)
                    for i in range(child_count):
                        stack.append(node.named_child(i))

                    snippet = node_text(text, node).strip()
                    start_pos = node_value(node, "start_position") or (0, 0)
                    end_pos = node_value(node, "end_position") or start_pos
                    start_line = point_row(start_pos) + 1
                    end_line = point_row(end_pos) + 1
                    kind = str(node_value(node, "kind") or "")

                    if kind == "import_statement":
                        imports.append(snippet)
                        continue
                    if "export" in kind:
                        exports.append(snippet)

                    name_node = node.child_by_field_name("name")
                    name = node_text(text, name_node).strip() if name_node else ""
                    if kind == "class_declaration" and name:
                        key = (name, start_line)
                        if key not in seen:
                            seen.add(key)
                            symbols.append(SymbolRecord(name, "class", snippet, start_line, end_line, imports=imports, exports=exports))
                    elif kind in {"function_declaration", "method_definition"} and name:
                        key = (name, start_line)
                        if key not in seen:
                            seen.add(key)
                            symbols.append(SymbolRecord(name, "function", snippet, start_line, end_line, imports=imports, exports=exports))
                    elif kind == "variable_declarator" and name and "=>" in snippet:
                        key = (name, start_line)
                        if key not in seen:
                            seen.add(key)
                            symbols.append(SymbolRecord(name, "function", snippet, start_line, end_line, imports=imports, exports=exports))

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if IMPORT_RE.search(line) and stripped not in imports:
                imports.append(stripped)
            if EXPORT_RE.search(line) and stripped not in exports:
                exports.append(stripped)
            match = CLASS_RE.search(line)
            if match:
                key = (match.group(1), idx)
                if key not in seen:
                    seen.add(key)
                    symbols.append(SymbolRecord(match.group(1), "class", stripped, idx, idx, imports=imports, exports=exports))
                continue
            match = FUNC_RE.search(line)
            if match:
                key = (match.group(1), idx)
                if key not in seen:
                    seen.add(key)
                    symbols.append(SymbolRecord(match.group(1), "function", stripped, idx, idx, imports=imports, exports=exports))
                continue
            match = CONST_FUNC_RE.search(line)
            if match:
                key = (match.group(1), idx)
                if key not in seen:
                    seen.add(key)
                    symbols.append(SymbolRecord(match.group(1), "function", stripped, idx, idx, imports=imports, exports=exports))
                continue
            route = ROUTE_RE.search(line)
            if route:
                route_name = f"{route.group(1).upper()} route L{idx}"
                key = (route_name, idx)
                if key not in seen:
                    seen.add(key)
                    symbols.append(
                        SymbolRecord(
                            route_name,
                            "route",
                            stripped,
                            idx,
                            idx,
                            imports=imports,
                            exports=exports,
                            route_like=True,
                        )
                    )
            test = TEST_RE.search(line)
            if test:
                test_name = test.group(2)
                key = (test_name, idx)
                if key not in seen:
                    seen.add(key)
                    symbols.append(
                        SymbolRecord(
                            test_name,
                            test.group(1),
                            stripped,
                            idx,
                            idx,
                            imports=imports,
                            exports=exports,
                            test_name=True,
                        )
                    )
        return ParsedFile(self.language, imports, exports, symbols, backend)
