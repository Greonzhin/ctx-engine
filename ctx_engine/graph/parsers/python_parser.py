from __future__ import annotations

import ast

from .base import SourceParser, node_text, node_value, parse_tree, point_row, tree_sitter_available
from ..symbols import ParsedFile, SymbolRecord


def _signature_from_line(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip().rstrip(":")
    return ""


def _decorator_text(text: str, node: ast.AST) -> str:
    values = []
    for deco in getattr(node, "decorator_list", []):
        try:
            values.append(ast.get_source_segment(text, deco) or "")
        except Exception:
            values.append("")
    return "\n".join(values)


class PythonParser(SourceParser):
    language = "python"

    def parse(self, text: str, path: str) -> ParsedFile:
        use_tree = tree_sitter_available("python", text)
        backend = "tree-sitter+ast" if use_tree else "ast"
        imports: list[str] = []
        exports: list[str] = []
        symbols: list[SymbolRecord] = []
        seen: set[tuple[str, int]] = set()

        if use_tree:
            tree = parse_tree("python", text)
            root = tree.root_node() if tree is not None else None
            if root is not None:
                stack = [root]
                while stack:
                    node = stack.pop()
                    child_count = int(node_value(node, "named_child_count") or 0)
                    for i in range(child_count):
                        stack.append(node.named_child(i))
                    kind = str(node_value(node, "kind") or "")
                    snippet = node_text(text, node).strip()
                    start_pos = node_value(node, "start_position") or (0, 0)
                    end_pos = node_value(node, "end_position") or start_pos
                    start_line = point_row(start_pos) + 1
                    end_line = point_row(end_pos) + 1
                    if kind in {"import_statement", "import_from_statement"}:
                        imports.append(snippet)
                        continue
                    if kind == "assignment" and "__all__" in snippet:
                        exports.append(snippet)
                        continue
                    if kind in {"function_definition", "class_definition"}:
                        name_node = node.child_by_field_name("name")
                        name = node_text(text, name_node).strip() if name_node else ""
                        if not name:
                            continue
                        rec_kind = "class" if kind == "class_definition" else "function"
                        key = (name, start_line)
                        if key in seen:
                            continue
                        seen.add(key)
                        route_like = "@app." in snippet or "@router." in snippet
                        symbols.append(
                            SymbolRecord(
                                name=name,
                                kind=rec_kind,
                                signature=snippet.splitlines()[0].rstrip(":") if snippet else name,
                                start_line=start_line,
                                end_line=end_line,
                                container=None,
                                imports=imports,
                                exports=exports,
                                route_like=route_like,
                                test_name=name.startswith("test_"),
                            )
                        )
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return ParsedFile(self.language, imports, exports, symbols, "unparsed")

        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(_signature_from_line(text, node.lineno))
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        exports.append(_signature_from_line(text, node.lineno))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                parent = parents.get(node)
                container = parent.name if isinstance(parent, ast.ClassDef) else None
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                if isinstance(node, ast.AsyncFunctionDef):
                    kind = "async_function"
                decorators = _decorator_text(text, node)
                route_like = any(token in decorators for token in (".route", ".get", ".post", ".put", ".delete"))
                signature = _signature_from_line(text, node.lineno)
                key = (node.name, node.lineno)
                if key in seen:
                    continue
                seen.add(key)
                symbols.append(
                    SymbolRecord(
                        name=node.name,
                        kind=kind,
                        signature=signature,
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                        container=container,
                        imports=imports,
                        exports=exports,
                        route_like=route_like,
                        test_name=node.name.startswith("test_"),
                    )
                )
        return ParsedFile(self.language, imports, exports, symbols, backend)
