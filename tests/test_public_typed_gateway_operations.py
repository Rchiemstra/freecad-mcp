"""Public TYPED_GATEWAY mutations never execute rendered Python."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from mcp.types import ImageContent

from freecad_mcp.generated.capabilities.connection_methods.connection_assembly_ops import (
    solve_assembly as solve_assembly_connection,
)
from freecad_mcp.generated.capabilities.connection_methods.connection_read_ops import (
    delete_object as delete_object_connection,
)
from freecad_mcp.generated.capabilities.client_stubs import (
    solve_assembly as solve_assembly_client_stub,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.freecad_client_ops.connection_methods.connection_assembly_ops import (
    solve_assembly as public_solve_assembly_connection,
)
from freecad_mcp.operations.core import (
    delete_object_operation,
    sketch_add_constraint_operation,
    sketch_add_geometry_operation,
    sketch_create_operation,
)
from freecad_mcp.operations.p7_assembly import solve_assembly_operation
from freecad_mcp.operations.parametric import (
    body_create_operation,
    body_set_tip_operation,
    clear_expression_operation,
    set_expression_operation,
    sketch_edit_constraint_operation,
    spreadsheet_create_operation,
    spreadsheet_set_alias_operation,
    spreadsheet_set_cells_operation,
)

pytestmark = pytest.mark.unit


_PUBLIC_TYPED_CASES = (
    (
        "delete_object",
        delete_object_operation,
        ("Doc", "Box"),
        ("Doc", "Box", False, False),
    ),
    (
        "sketch_create",
        sketch_create_operation,
        ("Doc", "Sketch", "Body", "XY_Plane"),
        ("Doc", "Sketch", "Body", "XY_Plane"),
    ),
    (
        "sketch_add_geometry",
        sketch_add_geometry_operation,
        ("Doc", "Sketch", [{"type": "line"}]),
        ("Doc", "Sketch", [{"type": "line"}]),
    ),
    (
        "sketch_add_constraint",
        sketch_add_constraint_operation,
        ("Doc", "Sketch", [{"type": "Horizontal", "geo": 0}]),
        ("Doc", "Sketch", [{"type": "Horizontal", "geo": 0}]),
    ),
    (
        "body_create",
        body_create_operation,
        ("Doc", "Body"),
        ("Doc", "Body"),
    ),
    (
        "body_set_tip",
        body_set_tip_operation,
        ("Doc", "Body", "Pad"),
        ("Doc", "Body", "Pad"),
    ),
    (
        "sketch_edit_constraint",
        sketch_edit_constraint_operation,
        ("Doc", "Sketch", 4.0, "Width", None),
        ("Doc", "Sketch", 4.0, "Width", None),
    ),
    (
        "set_expression",
        set_expression_operation,
        ("Doc", "Pad", "Length", "<<Dims>>.Height"),
        ("Doc", "Pad", "Length", "<<Dims>>.Height"),
    ),
    (
        "clear_expression",
        clear_expression_operation,
        ("Doc", "Pad", "Length"),
        ("Doc", "Pad", "Length"),
    ),
    (
        "spreadsheet_create",
        spreadsheet_create_operation,
        ("Doc", "Dims"),
        ("Doc", "Dims"),
    ),
    (
        "spreadsheet_set_cells",
        spreadsheet_set_cells_operation,
        ("Doc", "Dims", [{"address": "A1", "value": 12}]),
        ("Doc", "Dims", [{"address": "A1", "value": 12}]),
    ),
    (
        "spreadsheet_set_alias",
        spreadsheet_set_alias_operation,
        ("Doc", "Dims", "A1", "Height"),
        ("Doc", "Dims", "A1", "Height"),
    ),
    (
        "solve_assembly",
        solve_assembly_operation,
        ("Doc", "Assembly"),
        ("Doc", "Assembly"),
    ),
)


@pytest.mark.parametrize(
    ("method_name", "operation", "operation_args", "typed_args"),
    _PUBLIC_TYPED_CASES,
)
def test_public_typed_mutation_calls_rpc_once_and_never_execute_code(
    method_name,
    operation,
    operation_args,
    typed_args,
):
    connection = MagicMock()
    getattr(connection, method_name).return_value = {
        "success": True,
        "ok": True,
        "message": "committed",
    }

    response = operation(connection, True, *operation_args)

    assert not response.isError
    getattr(connection, method_name).assert_called_once_with(*typed_args)
    connection.execute_code.assert_not_called()


@pytest.mark.parametrize(
    ("method_name", "operation", "operation_args", "typed_args"),
    _PUBLIC_TYPED_CASES,
)
def test_public_typed_mutation_surfaces_rpc_error_without_execute_code(
    method_name,
    operation,
    operation_args,
    typed_args,
):
    connection = MagicMock()
    getattr(connection, method_name).return_value = {
        "success": False,
        "ok": False,
        "error_code": "MUTATION_REJECTED",
        "error": "typed mutation rejected",
    }

    response = operation(connection, True, *operation_args)

    assert response.isError
    assert "typed mutation rejected" in response.content[0].text
    getattr(connection, method_name).assert_called_once_with(*typed_args)
    connection.execute_code.assert_not_called()


@pytest.mark.parametrize(
    ("method_name", "operation", "operation_args"),
    (
        ("delete_object", delete_object_operation, ("Doc", "Box")),
        ("sketch_create", sketch_create_operation, ("Doc", "Sketch")),
        ("solve_assembly", solve_assembly_operation, ("Doc", "Assembly")),
    ),
)
def test_typed_visual_mutations_preserve_screenshot_feedback(
    method_name,
    operation,
    operation_args,
):
    connection = MagicMock()
    getattr(connection, method_name).return_value = {"success": True, "ok": True}
    connection.get_active_screenshot.return_value = "image-data"

    response = operation(connection, False, *operation_args)

    assert any(isinstance(item, ImageContent) for item in response.content)
    connection.get_active_screenshot.assert_called_once_with()
    connection.execute_code.assert_not_called()


def test_committed_solve_survives_screenshot_failure_without_retry_signal():
    connection = MagicMock()
    connection.solve_assembly.return_value = {"success": True, "ok": True}
    connection.get_active_screenshot.side_effect = RuntimeError("viewer unavailable")

    response = solve_assembly_operation(connection, False, "Doc", "Assembly")

    assert not response.isError
    assert response.structuredContent["data"]["presentation_warning"] == (
        "Screenshot capture failed: viewer unavailable"
    )
    connection.solve_assembly.assert_called_once_with("Doc", "Assembly")
    connection.execute_code.assert_not_called()


def test_delete_connection_forwards_safety_flags_to_v2_once():
    connection = MagicMock()
    connection._invoke_mutation_v2.return_value = {"success": True}

    result = delete_object_connection(
        connection,
        "Doc",
        "Body",
        recursive=True,
        force=False,
    )

    assert result == {"success": True}
    connection._invoke_mutation_v2.assert_called_once_with(
        "delete_object",
        {
            "doc_name": "Doc",
            "obj_name": "Body",
            "recursive": True,
            "force": False,
        },
        document_names=("Doc",),
        operation_name="Delete object",
    )
    connection.server.delete_object.assert_not_called()


def test_delete_connection_forwards_safety_flags_to_legacy_rpc_once():
    connection = MagicMock()
    connection._invoke_mutation_v2.return_value = None
    connection.server.delete_object.return_value = {"success": True}

    delete_object_connection(connection, "Doc", "Body", True, True)

    connection.server.delete_object.assert_called_once_with(
        "Doc", "Body", True, True
    )


def test_solve_assembly_connection_routes_v2_once():
    connection = MagicMock()
    connection._invoke_mutation_v2.return_value = {"success": True}

    result = solve_assembly_connection(connection, "Doc", "Assembly")

    assert result == {"success": True}
    connection._invoke_mutation_v2.assert_called_once_with(
        "solve_assembly",
        {"doc_name": "Doc", "assembly_name": "Assembly"},
        document_names=("Doc",),
        operation_name="Solve assembly",
    )
    connection.server.solve_assembly.assert_not_called()


def test_solve_assembly_connection_is_bound_on_public_facade():
    assert FreeCADConnection.solve_assembly is public_solve_assembly_connection


def test_generated_solve_assembly_client_stub_delegates_to_connection_method():
    connection = MagicMock()
    connection._invoke_mutation_v2.return_value = {"success": True}

    result = solve_assembly_client_stub(connection, "Doc", "Assembly")

    assert result == {"success": True}
    connection._invoke_mutation_v2.assert_called_once()
