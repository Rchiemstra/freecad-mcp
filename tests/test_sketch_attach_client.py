"""Client-side sketch_attach argument compatibility."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from freecad_mcp.freecad_client import FreeCADConnection


def test_client_omits_attachment_offset_positional_when_none():
    server = MagicMock()
    server.sketch_attach.return_value = {"success": True, "sketch": "Sketch"}
    conn = FreeCADConnection.__new__(FreeCADConnection)
    conn.server = server
    conn._invoke_mutation_v2 = MagicMock(return_value=None)  # force legacy route

    conn.sketch_attach("Doc", "Sketch", "XY_Plane")
    server.sketch_attach.assert_called_once_with("Doc", "Sketch", "XY_Plane")

    server.sketch_attach.reset_mock()
    offset = {
        "Base": {"x": 0, "y": 0, "z": 1},
        "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 90},
    }
    conn.sketch_attach("Doc", "Sketch", "XY_Plane", offset)
    server.sketch_attach.assert_called_once_with("Doc", "Sketch", "XY_Plane", offset)


def test_client_v2_params_omit_attachment_offset_key_when_none():
    conn = FreeCADConnection.__new__(FreeCADConnection)
    captured = {}

    def _capture(method, params, **kwargs):
        captured["method"] = method
        captured["params"] = dict(params)
        return {"success": True, "sketch": "Sketch"}

    conn._invoke_mutation_v2 = _capture  # type: ignore[method-assign]
    conn.server = MagicMock()

    conn.sketch_attach("Doc", "Sketch", "XY_Plane")
    assert captured["method"] == "sketch_attach"
    assert "attachment_offset" not in captured["params"]

    conn.sketch_attach(
        "Doc",
        "Sketch",
        "XY_Plane",
        {"Base": {"x": 0, "y": 0, "z": 2}, "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 45}},
    )
    assert captured["params"]["attachment_offset"]["Base"]["z"] == 2


def test_client_caches_advertised_rpc_parameter_capabilities():
    conn = FreeCADConnection.__new__(FreeCADConnection)
    conn._identity_lock = threading.RLock()
    conn._rpc_method_capabilities = {}
    conn._rpc_method_capabilities_loaded = False
    conn.server = MagicMock()
    conn.server.get_instance_info.return_value = {
        "rpc_method_capabilities": {
            "sketch_attach": {"parameters": ["attachment_offset"]}
        }
    }

    assert conn.supports_rpc_parameter("sketch_attach", "attachment_offset") is True
    assert conn.supports_rpc_parameter("sketch_attach", "future_parameter") is False
    conn.server.get_instance_info.assert_called_once()


def test_client_treats_missing_capability_map_as_legacy_absence():
    conn = FreeCADConnection.__new__(FreeCADConnection)
    conn._identity_lock = threading.RLock()
    conn._rpc_method_capabilities = {}
    conn._rpc_method_capabilities_loaded = False
    conn.server = MagicMock()
    conn.server.get_instance_info.return_value = {"addon_version": "legacy"}

    assert conn.supports_rpc_parameter("sketch_attach", "attachment_offset") is False
