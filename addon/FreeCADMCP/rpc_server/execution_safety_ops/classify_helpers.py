"""AST helpers for execute_code safety classification."""

from __future__ import annotations

import ast

_EXPENSIVE_METHODS = frozenset({
    "cut", "common", "fuse", "multiCut", "multiFuse", "section",
    "distToShape", "isInside", "isValid", "check", "checkGeometry",
    "removeSplitter",
})
_LIGHTWEIGHT_CALLS = frozenset({
    "print", "len", "getattr", "hasattr", "sorted", "list", "tuple", "dict",
    "set", "str", "float", "int", "bool", "round", "min", "max", "sum",
    "abs", "enumerate", "range", "zip", "any", "all",
})
_LIGHTWEIGHT_METHODS = frozenset({
    "getDocument", "listDocuments", "getObject", "getTypeIdOfProperty",
    "isNull", "isClosed", "dumps", "keys", "values", "items", "get",
})
_LIGHTWEIGHT_IMPORTS = frozenset({"FreeCAD", "json", "math"})


def parse_execute_code_ast(code: str) -> ast.AST | None:
    try:
        return ast.parse(code, mode="exec")
    except SyntaxError:
        return None


def tree_has_expensive_method_call(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Attribute) and node.attr in _EXPENSIVE_METHODS
        for node in ast.walk(tree)
    )


def is_unsafe_mutation_node(node: ast.AST) -> bool:
    if isinstance(node, (ast.Delete, ast.AugAssign, ast.AnnAssign, ast.NamedExpr)):
        return True
    return isinstance(node, ast.Assign) and any(
        isinstance(target, (ast.Attribute, ast.Subscript)) for target in node.targets
    )


def is_unsafe_import(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(
            item.name.split(".")[0] not in _LIGHTWEIGHT_IMPORTS for item in node.names
        )
    if isinstance(node, ast.ImportFrom):
        return not node.module or node.module.split(".")[0] not in _LIGHTWEIGHT_IMPORTS
    return False


def is_unsafe_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name):
        return node.func.id not in _LIGHTWEIGHT_CALLS
    if isinstance(node.func, ast.Attribute):
        return node.func.attr not in _LIGHTWEIGHT_METHODS
    return True
