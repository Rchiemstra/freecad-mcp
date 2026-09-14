"""sketch_attach typed-RPC routing and compatibility-fallback tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.parametric import sketch_attach_operation


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


def _offset_90_z(z: float = 10.0) -> dict:
    return {
        "Base": {"x": 0.0, "y": 0.0, "z": z},
        "Rotation": {"Axis": {"x": 0.0, "y": 0.0, "z": 1.0}, "Angle": 90.0},
    }


def test_sketch_attach_prefers_typed_rpc_without_execute_code():
    conn = MagicMock()
    conn.sketch_attach.return_value = {
        "success": True,
        "sketch": "Sketch",
        "attached": {"kind": "origin_plane", "plane": "XY_Plane"},
        "attachment_offset": _offset_90_z(),
    }
    resp = sketch_attach_operation(
        conn, True, "Doc", "Sketch", "XY_Plane", attachment_offset=_offset_90_z()
    )
    assert not resp.isError
    conn.sketch_attach.assert_called_once_with(
        "Doc", "Sketch", "XY_Plane", _offset_90_z()
    )
    conn.execute_code.assert_not_called()
    offset = conn.sketch_attach.return_value["attachment_offset"]
    assert abs(offset["Rotation"]["Angle"] - 90.0) < 1e-9
    assert abs(offset["Base"]["z"] - 10.0) < 1e-9


def test_sketch_attach_omits_fourth_arg_when_no_offset():
    conn = MagicMock()
    conn.sketch_attach.return_value = {
        "success": True,
        "sketch": "Sketch",
        "attached": {"kind": "origin_plane"},
    }
    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")
    assert not resp.isError
    conn.sketch_attach.assert_called_once_with("Doc", "Sketch", "XY_Plane")
    assert len(conn.sketch_attach.call_args.args) == 3
    conn.execute_code.assert_not_called()


def test_typed_failure_is_not_retried_via_generated_code():
    conn = MagicMock()
    conn.sketch_attach.return_value = {
        "success": False,
        "error": "Sketch 'Missing' not found.",
        "error_code": "SKETCH_MISSING",
    }
    resp = sketch_attach_operation(conn, True, "Doc", "Missing", "XY_Plane")
    assert resp.isError
    conn.execute_code.assert_not_called()
    assert "Missing" in _text(resp)


def test_typed_exception_not_missing_method_is_not_retried():
    conn = MagicMock()
    conn.sketch_attach.side_effect = RuntimeError("Sketch boom")
    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")
    assert resp.isError
    conn.execute_code.assert_not_called()
    assert "boom" in _text(resp)


def test_missing_typed_method_falls_back_to_generated():
    conn = MagicMock()
    conn.sketch_attach.side_effect = AttributeError(
        'method "sketch_attach" is not supported'
    )
    conn.execute_code.return_value = {
        "success": True,
        "message": 'Output: {"ok": true, "sketch": "Sketch"}',
        "recompute_errors": [],
    }
    conn.get_active_screenshot.return_value = None
    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")
    assert not resp.isError
    conn.execute_code.assert_called_once()
    code = conn.execute_code.call_args[0][0]
    assert "XY_Plane" in code
    assert "_mcp_dict_to_placement" in code


def test_structured_v2_unknown_method_falls_back_to_generated():
    conn = MagicMock()
    conn.sketch_attach.return_value = {
        "success": False,
        "error_code": "UNKNOWN_METHOD",
        "error": "The requested RPC method is not registered",
    }
    conn.execute_code.return_value = {
        "success": True,
        "message": 'Output: {"ok": true, "sketch": "Sketch"}',
        "recompute_errors": [],
    }
    conn.get_active_screenshot.return_value = None

    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")

    assert not resp.isError
    conn.execute_code.assert_called_once()


def test_structured_internal_protocol_failure_is_not_retried():
    conn = MagicMock()
    conn.sketch_attach.return_value = {
        "success": False,
        "error_code": "INTERNAL_PROTOCOL_ERROR",
        "error": "The authenticated RPC request could not be processed",
    }

    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")

    assert resp.isError
    conn.execute_code.assert_not_called()


def test_unadvertised_offset_uses_fallback_before_typed_mutation():
    conn = MagicMock()
    conn.supports_rpc_parameter.return_value = False
    conn.execute_code.return_value = {
        "success": True,
        "message": 'Output: {"ok": true, "sketch": "Sketch"}',
        "recompute_errors": [],
    }
    conn.get_active_screenshot.return_value = None

    resp = sketch_attach_operation(
        conn,
        True,
        "Doc",
        "Sketch",
        "XY_Plane",
        attachment_offset=_offset_90_z(),
    )

    assert not resp.isError
    conn.sketch_attach.assert_not_called()
    conn.execute_code.assert_called_once()


def test_fallback_with_offset_embeds_degree_helpers():
    conn = MagicMock()
    conn.sketch_attach.side_effect = Exception(
        'method "sketch_attach" is not supported by server'
    )
    conn.execute_code.return_value = {
        "success": True,
        "message": 'Output: {"ok": true, "sketch": "Sketch"}',
        "recompute_errors": [],
    }
    conn.get_active_screenshot.return_value = None
    offset = _offset_90_z(7.5)
    resp = sketch_attach_operation(
        conn, True, "Doc", "Sketch", "XY_Plane", attachment_offset=offset
    )
    assert not resp.isError
    code = conn.execute_code.call_args[0][0]
    assert "7.5" in code
    assert "90" in code
    assert "180.0 / _mcp_math.pi" in code or "180.0 /" in code
