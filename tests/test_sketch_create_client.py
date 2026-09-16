"""Client-side sketch_create argument compatibility."""

from __future__ import annotations

from unittest.mock import MagicMock

from freecad_mcp.freecad_client import FreeCADConnection


def test_client_omits_attachment_offset_for_legacy_addon_when_none():
    server = MagicMock()
    server.sketch_create.return_value = {"success": True, "sketch": "Sketch"}
    conn = FreeCADConnection.__new__(FreeCADConnection)
    conn.server = server
    conn._invoke_mutation_v2 = MagicMock(return_value=None)

    conn.sketch_create("Doc", "Sketch", "Body", "XZ_Plane")

    server.sketch_create.assert_called_once_with("Doc", "Sketch", "Body", "XZ_Plane")


def test_client_routes_atomic_attachment_offset_over_v2():
    conn = FreeCADConnection.__new__(FreeCADConnection)
    captured = {}

    def _capture(method, params, **kwargs):
        captured["method"] = method
        captured["params"] = dict(params)
        return {"success": True, "sketch": "Sketch"}

    conn._invoke_mutation_v2 = _capture  # type: ignore[method-assign]
    conn.server = MagicMock()
    offset = {"Base": {"x": 0, "y": 0, "z": 10}}

    conn.sketch_create("Doc", "Sketch", "Body", "XZ_Plane", offset)

    assert captured == {
        "method": "sketch_create",
        "params": {
            "doc_name": "Doc",
            "sketch_name": "Sketch",
            "body_name": "Body",
            "attach_to": "XZ_Plane",
            "attachment_offset": offset,
        },
    }
