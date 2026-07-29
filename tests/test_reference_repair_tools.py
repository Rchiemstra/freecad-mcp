"""MCP-side contracts for recovery-safe reference inspection and repair."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.core import (
    inspect_references_operation,
    repair_references_operation,
)
from addon.FreeCADMCP.rpc_server import reference_repair


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
    assert response.structuredContent["status"] == "failed"
    assert response.structuredContent["data"] == result
    assert response.structuredContent["repair_committed"] is False
    assert "repair_committed" in _text(response)


def test_preflight_counts_exact_properties(monkeypatch):
    document = SimpleNamespace(Name="Model")
    target = SimpleNamespace(Name="Target", Document=document)

    class _Owner:
        TypeId = "PartDesign::Feature"

        def __init__(self, name, properties):
            self.Name = name
            self.PropertiesList = list(properties)
            for property_name, subelements in properties.items():
                setattr(self, property_name, (target, list(subelements)))

        def getTypeIdOfProperty(self, _property_name):
            return "App::PropertyLinkSub"

    owners = [
        _Owner("Pinion_Tooth_Pad", {"ReferenceAxis": ["AxisBad"]}),
        _Owner("Joint_A", {"AttachedTo": ["EdgeBad"]}),
        _Owner("Joint_B", {"Support": ["FaceBad"]}),
        _Owner("Healthy", {"Support": ["Face1"]}),
    ]
    document.Objects = owners
    document.getObject = lambda name: next(
        (owner for owner in owners if owner.Name == name), None
    )

    def validate(_target, subelement):
        if subelement.endswith("Bad"):
            raise ValueError(f"{subelement} does not exist")

    monkeypatch.setattr(
        reference_repair.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
    )
    monkeypatch.setattr(reference_repair, "validate_subelement_reference", validate)

    result = reference_repair.inspect_references_gui(
        "Model", only_invalid=True, validate=True
    )

    assert result["ok"] is True
    assert result["invalid_count"] == 3
    assert {
        (item["object"], item["property"]) for item in result["references"]
    } == {
        ("Pinion_Tooth_Pad", "ReferenceAxis"),
        ("Joint_A", "AttachedTo"),
        ("Joint_B", "Support"),
    }
