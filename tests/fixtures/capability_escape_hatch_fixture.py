"""Synthetic escape-hatch impl for manifest generator unit tests."""

from __future__ import annotations

from mcp.types import CallToolResult

from freecad_mcp.responses import json_response


def hand_written_escape_hatch(_ctx) -> CallToolResult:
    return json_response({"escape": True})
