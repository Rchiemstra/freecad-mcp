"""Unit tests for parametric Spreadsheet / expression / Body MCP operations."""
from unittest.mock import MagicMock

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
from freecad_mcp.operations.core import (
    sketch_add_constraint_operation,
    sketch_constrain_distance_operation,
    sketch_constrain_radius_operation,
)
from mcp.types import TextContent


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
    return conn


def _fail_conn(error="oops"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": error}
    return conn


def _code(conn) -> str:
    return conn.execute_code.call_args[0][0]


def test_spreadsheet_create_code():
    conn = _ok_conn('{"ok": true}')
    spreadsheet_create_operation(conn, True, "Doc", "Dims")
    code = _code(conn)
    assert "Spreadsheet::Sheet" in code
    assert "Dims" in code


def test_spreadsheet_set_cells_and_alias():
    conn = _ok_conn('{"ok": true}')
    spreadsheet_set_cells_operation(
        conn,
        True,
        "Doc",
        "Dims",
        [{"address": "A1", "value": 2.5, "alias": "Wall"}],
    )
    code = _code(conn)
    assert "set(" in code
    assert "Wall" in code
    spreadsheet_set_alias_operation(conn, True, "Doc", "Dims", "B1", "Bore")
    assert "setAlias" in _code(conn)
    spreadsheet_list_aliases_operation(conn, True, "Doc", "Dims")
    assert "aliases" in _code(conn)
    spreadsheet_get_cells_operation(conn, True, "Doc", "Dims", ["A1", {"alias": "Wall"}])
    assert "getContents" in _code(conn)


def test_spreadsheet_set_cells_rejects_empty():
    resp = spreadsheet_set_cells_operation(_ok_conn(), True, "Doc", "Dims", [])
    assert resp.isError


def test_set_clear_list_expression():
    conn = _ok_conn('{"ok": true}')
    set_expression_operation(conn, True, "Doc", "Pad", "Length", "<<Dims>>.PadH")
    code = _code(conn)
    assert "setExpression" in code
    assert "Constraints" not in code or "Length" in code
    assert "<<Dims>>.PadH" in code
    clear_expression_operation(conn, True, "Doc", "Pad", "Length")
    assert "clearExpression" in _code(conn) or "setExpression" in _code(conn)
    list_expressions_operation(conn, True, "Doc", "Pad")
    assert "ExpressionEngine" in _code(conn)


def test_set_expression_constraints_path():
    conn = _ok_conn('{"ok": true}')
    set_expression_operation(conn, True, "Doc", "Sketch", "Constraints[0]", "<<Dims>>.Wall")
    assert "Constraints[0]" in _code(conn)


def test_body_and_attach():
    conn = _ok_conn('{"ok": true}')
    body_create_operation(conn, True, "Doc", "Body")
    assert "PartDesign::Body" in _code(conn)
    body_set_tip_operation(conn, True, "Doc", "Body", "Pad")
    assert "Tip" in _code(conn)
    sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")
    assert "XY_Plane" in _code(conn)
    sketch_attach_operation(conn, True, "Doc", "Sketch", {"object": "Box", "subname": "Face1"})
    assert "Face1" in _code(conn)


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
    assert "renameConstraint" in _code(conn)


def test_sketch_edit_constraint_requires_identity():
    resp = sketch_edit_constraint_operation(_ok_conn(), True, "Doc", "Sk", value=2.0)
    assert resp.isError
    conn = _ok_conn('{"ok": true}')
    sketch_edit_constraint_operation(conn, True, "Doc", "Sk", value=4.0, name="WallThick")
    assert "WallThick" in _code(conn)
    assert "setDatum" in _code(conn)


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
