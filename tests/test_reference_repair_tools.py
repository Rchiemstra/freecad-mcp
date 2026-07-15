"""MCP-side contracts for recovery-safe reference inspection and repair."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.core import (
    inspect_references_operation,
    repair_references_operation,
)


def _text(response) -> str:
    return " ".join(
        item.text for item in response.content if isinstance(item, TextContent)
    )


def test_inspect_references_passes_recovery_options_without_screenshot():
    connection = MagicMock()
    connection.inspect_references.return_value = {
        "ok": True,
        "document": "Model",
        "invalid_count": 1,
        "references": [],
        "recomputed": False,
    }

    response = inspect_references_operation(
        connection,
        "Model",
        ["Binder"],
        only_invalid=True,
        validate=True,
    )

    assert response.isError is False
    assert json.loads(_text(response))["recomputed"] is False
    connection.inspect_references.assert_called_once_with(
        "Model", ["Binder"], only_invalid=True, validate=True
    )
    connection.get_active_screenshot.assert_not_called()


def test_repair_references_defaults_to_deferred_recompute():
    connection = MagicMock()
    connection.repair_references.return_value = {
        "ok": True,
        "repair_committed": True,
        "applied": [{"object": "Binder", "property": "Support"}],
        "recompute": {"requested": False, "ok": None, "deferred": True},
    }
    repairs = [{
        "object": "Binder",
        "property": "Support",
        "references": [{"object": "Box", "subelements": ["Edge1"]}],
    }]

    response = repair_references_operation(connection, "Model", repairs)

    assert response.isError is False
    assert json.loads(_text(response))["recompute"]["deferred"] is True
    connection.repair_references.assert_called_once_with(
        "Model", repairs, recompute=False, validate=False
    )
    connection.get_active_screenshot.assert_not_called()


def test_repair_preflight_failure_is_structured_tool_error():
    connection = MagicMock()
    result = {
        "ok": False,
        "repair_committed": False,
        "error": "Repair preflight failed: Box.Edge999 does not exist",
    }
    connection.repair_references.return_value = result

    response = repair_references_operation(connection, "Model", [{}], validate=True)

    assert response.isError is True
    assert response.structuredContent == result
    assert "repair_committed" in _text(response)
