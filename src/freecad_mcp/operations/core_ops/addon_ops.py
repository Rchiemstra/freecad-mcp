"""MCP result adapters for the three shared add-on service RPCs."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from mcp.types import CallToolResult

from ...addon_services import _json_copy
from ...freecad_client import FreeCADConnection
from ...responses.tool_results import json_response, tool_fail


def _call(callback: Callable[[], Any], *, mutation: bool = False) -> CallToolResult:
    try:
        result = _json_copy(callback())
        if not isinstance(result, dict) or not isinstance(result.get("success"), bool):
            raise ValueError("The add-on RPC returned an invalid result envelope.")
        if mutation and result["success"] and (result.get("committed") is not True or result.get("outcome") != "committed"):
            raise ValueError("The add-on RPC did not prove a terminal commit.")
    except Exception as exc:
        result = {"success": False, "error_code": "ADDON_RPC_UNCERTAIN", "error": str(exc)[:4096],
                  "committed": None, "outcome": "uncertain", "retry_safe": False}
    if isinstance(result, dict) and result.get("success") is True:
        return json_response(result)
    return tool_fail(json.dumps(result, allow_nan=False), structured=result)


def list_addons_operation(freecad: FreeCADConnection) -> CallToolResult:
    return _call(freecad.list_addons)


def describe_addon_operation(freecad: FreeCADConnection, addon_id: str) -> CallToolResult:
    return _call(lambda: freecad.describe_addon(addon_id))


def invoke_addon_operation_operation(freecad: FreeCADConnection, doc_name: str, addon_id: str, operation: str, arguments: dict[str, Any]) -> CallToolResult:
    return _call(lambda: freecad.invoke_addon_operation(doc_name, addon_id, operation, arguments), mutation=True)
