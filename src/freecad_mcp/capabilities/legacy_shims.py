"""Legacy tool shims referenced by bootstrapped manifests."""

from __future__ import annotations

from mcp.types import CallToolResult

from ..responses.tool_results import tool_fail

_LEGACY_REMOVED = {
    "success": False,
    "ok": False,
    "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
    "error": "Document authority is owned by native FreeCAD collaboration.",
}


def legacy_removed_tool(*_args: object, **_kwargs: object) -> CallToolResult:
    return tool_fail(
        "[LEGACY_LEASE_AUTHORITY_REMOVED] " + str(_LEGACY_REMOVED["error"]),
        structured=_LEGACY_REMOVED,
    )


__all__ = ["legacy_removed_tool"]
