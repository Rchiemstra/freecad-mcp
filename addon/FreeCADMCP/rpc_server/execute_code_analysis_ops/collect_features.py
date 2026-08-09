"""Walk execute_code AST nodes and collect bounded feature sets."""

from __future__ import annotations

import ast

from .call_name import call_name
from .patterns import typed_pattern_for_call, typed_pattern_for_type_id


def collect_ast_features(tree: ast.AST) -> tuple[set[str], set[str], set[str]]:
    imports: set[str] = set()
    calls: set[str] = set()
    suggestions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            call = call_name(node)
            if call:
                calls.add(call)
                suggestion = typed_pattern_for_call(call)
                if suggestion:
                    suggestions.add(suggestion)
            for argument in node.args[:4]:
                if isinstance(argument, ast.Constant) and isinstance(
                    argument.value, str
                ):
                    suggestion = typed_pattern_for_type_id(argument.value)
                    if suggestion:
                        suggestions.add(suggestion)
    return imports, calls, suggestions
