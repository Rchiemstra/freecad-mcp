"""Privacy-preserving AST classification for public ``execute_code`` calls."""

from __future__ import annotations

import ast
import hashlib
from typing import Any, Mapping


_TYPED_PATTERNS = {
    "recompute": "recompute_document",
    "save": "save_document",
    "saveas": "save_document_as",
    "removeobject": "delete_object",
    "setexpression": "set_expression",
    "addconstraint": "sketch_add_constraint",
    "addgeometry": "sketch_add_geometry",
    "delconstraint": "sketch_delete_constraint",
    "delconstraints": "sketch_delete_constraint",
    "delgeometry": "sketch_delete_geometry",
    "delgeometries": "sketch_delete_geometry",
}

_TYPE_PATTERNS = {
    "PartDesign::Body": "body_create",
    "Sketcher::SketchObject": "sketch_create",
    "Spreadsheet::Sheet": "spreadsheet_create",
    "PartDesign::Feature": "create_object",
}


def _call_name(node: ast.Call) -> str:
    target = node.func
    parts: list[str] = []
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts))


def analyze_execute_code(
    code: str, options: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Return bounded features and hashes, never source text."""

    raw = str(code).encode("utf-8", errors="replace")
    result: dict[str, Any] = {
        "code_sha256": hashlib.sha256(raw).hexdigest(),
        "code_bytes": len(raw),
        "read_only": bool((options or {}).get("read_only")),
        "execution_mode": str((options or {}).get("execution_mode") or "auto"),
        "document_scope": sorted(
            {
                str(item)
                for item in (
                    (options or {}).get("document"),
                    *((options or {}).get("affected_documents") or ()),
                )
                if item
            }
        ),
        "imports": [],
        "call_families": [],
        "typed_tool_suggestions": [],
        "ast_pattern_hash": None,
        "parse_error": None,
    }
    try:
        tree = ast.parse(str(code), mode="exec")
    except (SyntaxError, ValueError) as exc:
        result["parse_error"] = type(exc).__name__
        return result

    imports: set[str] = set()
    calls: set[str] = set()
    suggestions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            call = _call_name(node)
            if call:
                calls.add(call)
                suggestion = _TYPED_PATTERNS.get(call.rsplit(".", 1)[-1].lower())
                if suggestion:
                    suggestions.add(suggestion)
            for argument in node.args[:4]:
                if isinstance(argument, ast.Constant) and isinstance(
                    argument.value, str
                ):
                    suggestion = _TYPE_PATTERNS.get(argument.value)
                    if suggestion:
                        suggestions.add(suggestion)
    # Dumping without attributes removes locations and formatting while retaining
    # enough structure to group repeated patterns.
    pattern = ast.dump(tree, annotate_fields=False, include_attributes=False)
    result.update(
        imports=sorted(imports),
        call_families=sorted(calls)[:128],
        typed_tool_suggestions=sorted(suggestions),
        ast_pattern_hash=hashlib.sha256(pattern.encode("utf-8")).hexdigest(),
    )
    return result


def typed_tool_warning(analysis: Mapping[str, Any]) -> dict[str, Any] | None:
    suggestions = list(analysis.get("typed_tool_suggestions") or ())
    if not suggestions:
        return None
    return {
        "code": "TYPED_TOOL_AVAILABLE",
        "message": "A safer typed MCP tool matches this public Python workflow.",
        "preferred_tools": suggestions,
    }


__all__ = ["analyze_execute_code", "typed_tool_warning"]
