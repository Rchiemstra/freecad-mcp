"""Capture an MCP tool registry in frozen snapshot shape."""

from __future__ import annotations

import inspect
from typing import Any

from freecad_mcp.tools_register_order import REGISTER_TOOL_MODULES


def _tool_registry(mcp: Any) -> dict[str, Any]:
    manager = getattr(mcp, "_tool_manager", None)
    registry = getattr(manager, "_tools", None) or getattr(manager, "tools", None)
    if not isinstance(registry, dict):
        raise TypeError("expected FastMCP tool registry mapping")
    return registry


def _quote_annotation(annotation: str) -> str:
    if "'" in annotation:
        return '"' + annotation.replace('"', '\\"') + '"'
    return f"'{annotation}'"


def _format_annotation(annotation: object) -> str:
    if annotation is inspect.Parameter.empty:
        return "Any"
    text = (
        annotation
        if isinstance(annotation, str)
        else str(annotation).replace("typing.", "")
    )
    return text


def format_tool_signature(fn: Any) -> str:
    signature = inspect.signature(fn)
    parts: list[str] = []
    for param in signature.parameters.values():
        ann = _format_annotation(param.annotation)
        quoted = _quote_annotation(ann)
        if param.default is inspect.Parameter.empty:
            parts.append(f"{param.name}: {quoted}")
        else:
            default = repr(param.default)
            parts.append(f"{param.name}: {quoted} = {default}")
    return_ann = _quote_annotation(_format_annotation(signature.return_annotation))
    return f"({', '.join(parts)}) -> {return_ann}"


def capture_registry_snapshot(mcp: Any) -> dict[str, object]:
    registry = _tool_registry(mcp)
    tool_order = list(registry)
    tools: dict[str, dict[str, str]] = {}
    for name in tool_order:
        tool = registry[name]
        fn = getattr(tool, "fn", None) or getattr(tool, "function", None)
        if fn is None:
            raise TypeError(f"tool {name!r} has no callable")
        tools[name] = {
            "docstring": inspect.getdoc(fn) or "",
            "signature": format_tool_signature(fn),
        }
    return {
        "register_order": list(REGISTER_TOOL_MODULES),
        "tool_count": len(tool_order),
        "tool_order": tool_order,
        "tools": tools,
    }


__all__ = ["capture_registry_snapshot", "format_tool_signature"]
