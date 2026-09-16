"""sketch_attach typed-RPC routing tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp._shared.protocol.sketch_attach_contract import (
    make_sketch_attach_failure,
    make_sketch_attach_success,
)
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
    offset = _offset_90_z()
    conn.sketch_attach.return_value = make_sketch_attach_success("Sketch", "origin_plane", "XY_Plane", "")
    resp = sketch_attach_operation(
        conn, True, "Doc", "Sketch", "XY_Plane", attachment_offset=offset
    )
    assert not resp.isError
    conn.sketch_attach.assert_called_once_with("Doc", "Sketch", "XY_Plane", offset)
    conn.execute_code.assert_not_called()


def test_sketch_attach_omits_fourth_arg_when_no_offset():
    conn = MagicMock()
    conn.sketch_attach.return_value = make_sketch_attach_success("Sketch", "origin_plane", "XY_Plane", "")
    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")
    assert not resp.isError
    conn.sketch_attach.assert_called_once_with("Doc", "Sketch", "XY_Plane")
    assert len(conn.sketch_attach.call_args.args) == 3
    conn.execute_code.assert_not_called()


def test_typed_failure_is_not_retried_via_generated_code():
    conn = MagicMock()
    conn.sketch_attach.return_value = make_sketch_attach_failure(
        "SKETCH_MISSING", "Sketch 'Missing' not found."
    )
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


def test_missing_typed_method_surfaces_transport_uncertain():
    conn = MagicMock()
    conn.sketch_attach.side_effect = AttributeError(
        'method "sketch_attach" is not supported'
    )
    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")
    assert resp.isError
    conn.execute_code.assert_not_called()
    assert "unavailable" in _text(resp).lower()


def test_unknown_method_response_fails_without_retry():
    conn = MagicMock()
    conn.sketch_attach.return_value = make_sketch_attach_failure(
        "UNKNOWN_METHOD", "The requested RPC method is not registered"
    )
    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")
    assert resp.isError
    conn.execute_code.assert_not_called()
    assert "not registered" in _text(resp)


def test_structured_internal_protocol_failure_is_not_retried():
    conn = MagicMock()
    conn.sketch_attach.return_value = make_sketch_attach_failure(
        "INTERNAL_PROTOCOL_ERROR",
        "The authenticated RPC request could not be processed",
    )
    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")
    assert resp.isError
    conn.execute_code.assert_not_called()


def test_unadvertised_offset_still_calls_typed_rpc():
    conn = MagicMock()
    offset = _offset_90_z()
    conn.sketch_attach.return_value = make_sketch_attach_success("Sketch", "origin_plane", "XY_Plane", "")
    resp = sketch_attach_operation(
        conn,
        True,
        "Doc",
        "Sketch",
        "XY_Plane",
        attachment_offset=offset,
    )
    assert not resp.isError
    conn.sketch_attach.assert_called_once_with("Doc", "Sketch", "XY_Plane", offset)
    conn.execute_code.assert_not_called()


def test_offset_passed_through_to_typed_rpc():
    conn = MagicMock()
    offset = _offset_90_z(7.5)
    conn.sketch_attach.return_value = make_sketch_attach_success("Sketch", "origin_plane", "XY_Plane", "")
    resp = sketch_attach_operation(
        conn, True, "Doc", "Sketch", "XY_Plane", attachment_offset=offset
    )
    assert not resp.isError
    conn.sketch_attach.assert_called_once_with("Doc", "Sketch", "XY_Plane", offset)
    conn.execute_code.assert_not_called()
