"""Unit tests for parametric Spreadsheet / expression / Body MCP operations."""
from unittest.mock import MagicMock

from mcp.types import TextContent

from freecad_mcp.operations.core import (
    sketch_add_constraint_operation,
    sketch_constrain_distance_operation,
    sketch_constrain_radius_operation,
)
from freecad_mcp.operations.parametric import (
    body_create_operation,
    body_set_tip_operation,
    clear_expression_operation,
    diagnose_parametric_operation,
    list_expressions_operation,
    set_expression_operation,
    sketch_attach_operation,
    sketch_edit_constraint_operation,
    spreadsheet_create_operation,
    spreadsheet_get_cells_operation,
    spreadsheet_list_aliases_operation,
    spreadsheet_set_alias_operation,
    spreadsheet_set_cells_operation,
)


def _text(response):
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


def _ok_conn(output="done"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {
        "success": True,
        "message": "Python code execution scheduled. \nOutput: " + output,
        "recompute_errors": [],
    }
    conn.spreadsheet_create.return_value = {"success": True, "sheet": "Dims"}
    conn.spreadsheet_set_cells.return_value = {
        "success": True,
        "sheet": "Dims",
        "updated": [],
    }
    conn.spreadsheet_set_alias.return_value = {
        "success": True,
        "sheet": "Dims",
        "address": "B1",
        "alias": "Bore",
    }
    conn.set_expression.return_value = {"success": True, "object": "Pad"}
    conn.clear_expression.return_value = {"success": True, "object": "Pad"}
    conn.body_create.return_value = {"success": True, "body": "Body"}
    conn.body_set_tip.return_value = {"success": True, "body": "Body", "tip": "Pad"}
    conn.sketch_edit_constraint.return_value = {"success": True, "sketch": "Sk"}
    conn.sketch_add_constraint.return_value = {"success": True}
    return conn


def _fail_conn(error="oops"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": error}
    for method_name in (
        "spreadsheet_create",
        "spreadsheet_set_cells",
        "spreadsheet_set_alias",
        "set_expression",
        "clear_expression",
        "body_create",
        "body_set_tip",
        "sketch_edit_constraint",
        "sketch_add_constraint",
    ):
        getattr(conn, method_name).return_value = {"success": False, "error": error}
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def test_spreadsheet_create_uses_typed_rpc_once():
    conn = _ok_conn()
    response = spreadsheet_create_operation(conn, True, "Doc", "Dims")
    assert not response.isError
    conn.spreadsheet_create.assert_called_once_with("Doc", "Dims")
    conn.execute_code.assert_not_called()


def test_spreadsheet_set_cells_and_alias():
    conn = _ok_conn()
    cells = [{"address": "A1", "value": 2.5, "alias": "Wall"}]
    spreadsheet_set_cells_operation(
        conn,
        True,
        "Doc",
        "Dims",
        cells,
    )
    conn.spreadsheet_set_cells.assert_called_once_with("Doc", "Dims", cells)
    spreadsheet_set_alias_operation(conn, True, "Doc", "Dims", "B1", "Bore")
    conn.spreadsheet_set_alias.assert_called_once_with(
        "Doc", "Dims", "B1", "Bore"
    )
    conn.execute_code.assert_not_called()

    spreadsheet_list_aliases_operation(conn, True, "Doc", "Dims")
    assert "aliases" in _code(conn)
    spreadsheet_get_cells_operation(conn, True, "Doc", "Dims", ["A1", {"alias": "Wall"}])
    assert "getContents" in _code(conn)


def test_spreadsheet_set_cells_rejects_empty():
    resp = spreadsheet_set_cells_operation(_ok_conn(), True, "Doc", "Dims", [])
    assert resp.isError


def test_set_clear_list_expression():
    conn = _ok_conn()
    set_expression_operation(conn, True, "Doc", "Pad", "Length", "<<Dims>>.PadH")
    conn.set_expression.assert_called_once_with(
        "Doc", "Pad", "Length", "<<Dims>>.PadH"
    )
    clear_expression_operation(conn, True, "Doc", "Pad", "Length")
    conn.clear_expression.assert_called_once_with("Doc", "Pad", "Length")
    conn.execute_code.assert_not_called()

    list_expressions_operation(conn, True, "Doc", "Pad")
    assert "ExpressionEngine" in _code(conn)


def test_set_expression_constraints_path():
    conn = _ok_conn()
    set_expression_operation(conn, True, "Doc", "Sketch", "Constraints[0]", "<<Dims>>.Wall")
    conn.set_expression.assert_called_once_with(
        "Doc", "Sketch", "Constraints[0]", "<<Dims>>.Wall"
    )
    conn.execute_code.assert_not_called()


def test_body_and_attach():
    conn = _ok_conn()
    body_create_operation(conn, True, "Doc", "Body")
    conn.body_create.assert_called_once_with("Doc", "Body")
    body_set_tip_operation(conn, True, "Doc", "Body", "Pad")
    conn.body_set_tip.assert_called_once_with("Doc", "Body", "Pad")
    conn.execute_code.assert_not_called()

    conn.sketch_attach.return_value = {
        "success": True,
        "sketch": "Sketch",
        "attached": {"kind": "origin_plane", "plane": "XY_Plane"},
    }
    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")
    assert not resp.isError
    conn.sketch_attach.assert_called_with("Doc", "Sketch", "XY_Plane")

    conn.sketch_attach.reset_mock()
    conn.sketch_attach.return_value = {
        "success": True,
        "sketch": "Sketch",
        "attached": {"kind": "face_ref", "subname": "Face1"},
    }
    sketch_attach_operation(
        conn, True, "Doc", "Sketch", {"object": "Box", "subname": "Face1"}
    )
    args = conn.sketch_attach.call_args.args
    assert args[2]["subname"] == "Face1"

    offset = {
        "Base": {"x": 0, "y": 0, "z": 10},
        "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 0},
    }
    conn.sketch_attach.reset_mock()
    conn.sketch_attach.return_value = {
        "success": True,
        "sketch": "Sketch",
        "attached": {"kind": "origin_plane"},
        "attachment_offset": offset,
    }
    before = conn.execute_code.call_count
    sketch_attach_operation(
        conn, True, "Doc", "Sketch", "XY_Plane", attachment_offset=offset
    )
    conn.sketch_attach.assert_called_once_with("Doc", "Sketch", "XY_Plane", offset)
    assert conn.execute_code.call_count == before


def test_named_constraints_in_code():
    conn = _ok_conn("done")
    sketch_constrain_radius_operation(conn, True, "Doc", "Sk", 0, 5.0, name="BoreR")
    code = _code(conn)
    assert "renameConstraint" in code
    assert "BoreR" in code
    sketch_constrain_distance_operation(conn, True, "Doc", "Sk", 1, 10.0, name="WallThick")
    assert "WallThick" in _code(conn)
    sketch_add_constraint_operation(
        conn,
        True,
        "Doc",
        "Sk",
        [{"type": "Radius", "geo": 0, "value": 3.0, "name": "R1"}],
    )
    conn.sketch_add_constraint.assert_called_once_with(
        "Doc",
        "Sk",
        [{"type": "Radius", "geo": 0, "value": 3.0, "name": "R1"}],
    )


def test_sketch_edit_constraint_requires_identity():
    resp = sketch_edit_constraint_operation(_ok_conn(), True, "Doc", "Sk", value=2.0)
    assert resp.isError
    conn = _ok_conn()
    sketch_edit_constraint_operation(conn, True, "Doc", "Sk", value=4.0, name="WallThick")
    conn.sketch_edit_constraint.assert_called_once_with(
        "Doc", "Sk", 4.0, "WallThick", None
    )
    conn.execute_code.assert_not_called()


def test_diagnose_parametric_code():
    conn = _ok_conn('{"ok": true}')
    diagnose_parametric_operation(conn, True, "Doc")
    code = _code(conn)
    assert "expression_issues" in code
    assert "invalid_objects" in code
    diagnose_parametric_operation(conn, True, "Doc", "Pad")
    assert "Pad" in _code(conn)


def test_failures_surface():
    assert spreadsheet_create_operation(_fail_conn(), True, "Doc", "Dims").isError
    assert set_expression_operation(_fail_conn(), True, "Doc", "Pad", "Length", "x").isError
    assert body_create_operation(_fail_conn(), True, "Doc", "Body").isError
    fail = _fail_conn()
    fail.sketch_attach.return_value = {"success": False, "error": "nope"}
    assert sketch_attach_operation(fail, True, "Doc", "Sketch", "XY_Plane").isError
