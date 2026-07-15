"""Live regression tests for repairing stale subelement links before recompute."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.e2e


def test_invalid_linksublist_can_be_inspected_and_repaired_without_recompute(freecad):
    from addon.FreeCADMCP.rpc_server.reference_repair import (
        inspect_references_gui,
        repair_references_gui,
    )

    doc = freecad.newDocument("ReferenceRepairDeferred")
    try:
        target = doc.addObject("Part::Box", "Target")
        target.Length = 10
        target.Width = 10
        target.Height = 10
        doc.recompute()

        owner = doc.addObject("App::FeaturePython", "BrokenBinderLikeOwner")
        owner.addProperty("App::PropertyLinkSubList", "Support")
        owner.Support = [(target, ("Edge999",))]

        inspected = inspect_references_gui(
            doc.Name, [owner.Name], only_invalid=True, validate=True
        )
        assert inspected["ok"] is True
        assert inspected["invalid_count"] == 1
        assert inspected["references"][0]["property"] == "Support"
        assert inspected["references"][0]["references"][0]["subelements"] == [
            "Edge999"
        ]

        repaired = repair_references_gui(
            doc.Name,
            [{
                "object": owner.Name,
                "property": "Support",
                "references": [{
                    "object": target.Name,
                    "subelements": ["Edge1"],
                }],
            }],
        )

        assert repaired["ok"] is True
        assert repaired["repair_committed"] is True
        assert repaired["recompute"] == {
            "requested": False,
            "ok": None,
            "deferred": True,
        }
        assert repaired["remaining_invalid_repaired_properties"] == []
        normalized = inspect_references_gui(doc.Name, [owner.Name], validate=True)
        support = next(
            item for item in normalized["references"] if item["property"] == "Support"
        )
        assert support["valid"] is True
        assert support["references"][0]["subelements"] == ["Edge1"]
    finally:
        freecad.closeDocument(doc.Name)


def test_invalid_replacement_is_rejected_before_existing_link_changes(freecad):
    from addon.FreeCADMCP.rpc_server.reference_repair import repair_references_gui

    doc = freecad.newDocument("ReferenceRepairPreflight")
    try:
        target = doc.addObject("Part::Box", "Target")
        doc.recompute()
        owner = doc.addObject("App::FeaturePython", "Owner")
        owner.addProperty("App::PropertyLinkSubList", "Support")
        owner.Support = [(target, ("Edge1",))]

        result = repair_references_gui(
            doc.Name,
            [{
                "object": owner.Name,
                "property": "Support",
                "references": [{
                    "object": target.Name,
                    "subelements": ["Edge999"],
                }],
            }],
            validate=True,
        )

        assert result["ok"] is False
        assert result["repair_committed"] is False
        current = owner.Support
        assert "Edge1" in str(current)
        assert "Edge999" not in str(current)
    finally:
        freecad.closeDocument(doc.Name)


def test_recovery_mode_rewrites_reference_without_reading_target_shape(freecad):
    from addon.FreeCADMCP.rpc_server.reference_repair import (
        inspect_references_gui,
        repair_references_gui,
    )

    doc = freecad.newDocument("ReferenceRepairNoShapeRead")
    try:
        target = doc.addObject("App::FeaturePython", "UnevaluatableTarget")
        owner = doc.addObject("App::FeaturePython", "Owner")
        owner.addProperty("App::PropertyLinkSubList", "Support")
        owner.Support = [(target, ("Edge999",))]

        repaired = repair_references_gui(
            doc.Name,
            [{
                "object": owner.Name,
                "property": "Support",
                "references": [{
                    "object": target.Name,
                    "subelements": ["Edge42"],
                }],
            }],
        )

        assert repaired["ok"] is True
        assert repaired["validation_performed"] is False
        raw = inspect_references_gui(doc.Name, [owner.Name])
        support = next(
            item for item in raw["references"] if item["property"] == "Support"
        )
        assert support["valid"] is None
        assert support["references"][0]["subelements"] == ["Edge42"]

        strict = repair_references_gui(
            doc.Name,
            [{
                "object": owner.Name,
                "property": "Support",
                "references": [{
                    "object": target.Name,
                    "subelements": ["Edge43"],
                }],
            }],
            validate=True,
        )
        assert strict["ok"] is False
        assert strict["repair_committed"] is False
        assert "Edge42" in str(owner.Support)
    finally:
        freecad.closeDocument(doc.Name)
