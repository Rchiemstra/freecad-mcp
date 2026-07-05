"""
Live FreeCAD integration smoke test for assembly/path workflows.

This test is skipped unless it is run from an environment where the FreeCAD
Python modules are importable.
"""
from __future__ import annotations

import contextlib
import io
import json
import math

import pytest
from mcp.types import TextContent

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from freecad_mcp.operations.p5_measure import validate_geometry_operation
from freecad_mcp.operations.p7_assembly import (
    build_path_wire_operation,
    create_datum_plane_operation,
    create_subshape_binder_operation,
    sweep_pipe_operation,
)


class DirectFreeCADConnection:
    def execute_code(self, code: str):
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                exec(code, {"FreeCAD": FreeCAD, "Part": Part, "Sketcher": Sketcher})
            return {
                "success": True,
                "message": "Python code execution scheduled. \nOutput: " + buffer.getvalue(),
                "recompute_errors": [],
            }
        except Exception as err:
            return {"success": False, "error": str(err)}

    def get_active_screenshot(self, *args, **kwargs):
        return None


def _text(response) -> str:
    return " ".join(item.text for item in response if isinstance(item, TextContent))


def _json(response) -> dict:
    return json.loads(_text(response).splitlines()[0])


def _json_after_output(response) -> dict:
    text = _text(response)
    if "Output:" in text:
        return json.loads(text.split("Output:", 1)[1].strip())
    return json.loads(text.splitlines()[-1])


def test_minimal_assembly_path_and_pipe_workflow():
    doc = FreeCAD.newDocument("MCPAssemblyPathLive")
    conn = DirectFreeCADConnection()
    try:
        source = doc.addObject("Part::Box", "SourceBox")
        source.Length = 10
        source.Width = 8
        source.Height = 6
        source.Placement.Base = FreeCAD.Vector(11.47, 0, 0)

        body = doc.addObject("PartDesign::Body", "CableBody")
        doc.recompute()

        binder = _json(
            create_subshape_binder_operation(
                conn,
                True,
                doc.Name,
                "SourceBoxRef",
                "SourceBox",
                sub_elements=["Face1"],
                target_body="CableBody",
                if_exists="replace",
            )
        )
        assert binder["ok"] is True
        assert binder["bbox_delta_mm"] is None or binder["bbox_delta_mm"] <= 0.01

        datum = _json(
            create_datum_plane_operation(
                conn,
                True,
                doc.Name,
                "CableDatum",
                "CableBody",
                "offset_from_face",
                source_ref="SourceBoxRef:Face1",
                if_exists="replace",
            )
        )
        assert datum["ok"] is True

        sketch = doc.addObject("Sketcher::SketchObject", "RouteSketch")
        points = [
            (0, 0),
            (10, 0),
            (10, 5),
            (4, 5),
            (4, 12),
        ]
        for idx in range(len(points) - 1):
            start = FreeCAD.Vector(points[idx][0], points[idx][1], 0)
            end = FreeCAD.Vector(points[idx + 1][0], points[idx + 1][1], 0)
            sketch.addGeometry(Part.LineSegment(start, end), False)
        doc.recompute()

        wire = _json(
            build_path_wire_operation(
                conn,
                True,
                doc.Name,
                "CablePathWire",
                [{"sketch": "RouteSketch", "geo_index": i} for i in range(4)],
                if_exists="replace",
            )
        )
        assert wire["ok"] is True
        assert wire["edge_count"] == 4

        pipe = _json(
            sweep_pipe_operation(
                conn,
                True,
                doc.Name,
                "CablePathWire",
                1.75,
                "CableLower_1p75mm",
                if_exists="replace",
            )
        )
        assert pipe["ok"] is True
        expected_volume = math.pi * (1.75 / 2.0) ** 2 * wire["length_mm"]
        assert abs(pipe["volume_mm3"] - expected_volume) / expected_volume < 0.25

        validation = _json_after_output(
            validate_geometry_operation(conn, doc.Name, "CableLower_1p75mm")
        )
        assert "check_ok" in validation
        assert validation["face_count"] > 0
    finally:
        FreeCAD.closeDocument(doc.Name)
