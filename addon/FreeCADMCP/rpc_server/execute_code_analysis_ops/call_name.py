"""AST call-name extraction for execute_code analysis."""

from __future__ import annotations

import ast


def call_name(node: ast.Call) -> str:
    target = node.func
    parts: list[str] = []
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts))
