"""Typed-tool availability warnings for execute_code analysis."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def typed_tool_warning(analysis: Mapping[str, Any]) -> dict[str, Any] | None:
    suggestions = list(analysis.get("typed_tool_suggestions") or ())
    if not suggestions:
        return None
    return {
        "code": "TYPED_TOOL_AVAILABLE",
        "message": "A safer typed MCP tool matches this public Python workflow.",
        "preferred_tools": suggestions,
    }
