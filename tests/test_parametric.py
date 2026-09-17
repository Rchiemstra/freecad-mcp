"""Unit tests for parametric Spreadsheet / expression / Body MCP operations."""

from unittest.mock import MagicMock

import pytest
from mcp.types import TextContent

from freecad_mcp._shared.protocol.body_create_contract import (
    make_body_create_failure,
    make_body_create_success,
)
from freecad_mcp._shared.protocol.body_set_tip_contract import (
    make_body_set_tip_failure,
    make_body_set_tip_success,
)
from freecad_mcp._shared.protocol.clear_expression_contract import (
    make_clear_expression_failure,
    make_clear_expression_success,
)
from freecad_mcp._shared.protocol.set_expression_contract import (
    make_set_expression_failure,
    make_set_expression_success,
)
from freecad_mcp._shared.protocol.sketch_attach_contract import (
    make_sketch_attach_failure,
    make_sketch_attach_success,
)
from freecad_mcp._shared.protocol.spreadsheet_create_contract import (
    make_spreadsheet_create_failure,
    make_spreadsheet_create_success,
)
from freecad_mcp._shared.protocol.spreadsheet_get_cells_contract import (
    make_spreadsheet_get_cells_success,
)
from freecad_mcp._shared.protocol.spreadsheet_list_aliases_contract import (
    make_spreadsheet_list_aliases_success,
)
from freecad_mcp._shared.protocol.spreadsheet_set_alias_contract import (
    make_spreadsheet_set_alias_success,
)
from freecad_mcp._shared.protocol.spreadsheet_set_cells_contract import (
    make_spreadsheet_set_cells_success,
)
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


def _ok_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.spreadsheet_create.return_value = make_spreadsheet_create_success("Dims", "Dims")
    conn.spreadsheet_set_cells.return_value = make_spreadsheet_set_cells_success(
        "Dims",
        [{"address": "A1", "alias": "Wall", "value": "2.5"}],
    )
    conn.spreadsheet_set_alias.return_value = make_spreadsheet_set_alias_success("Dims", "B1", "Bore")
    conn.spreadsheet_list_aliases.return_value = make_spreadsheet_list_aliases_success("Dims", {"Wall": "A1"})
    conn.spreadsheet_get_cells.return_value = make_spreadsheet_get_cells_success("Dims", [{"address": "A1", "value": 2.5}])
    conn.set_expression.return_value = make_set_expression_success("Pad", "Length", "<<Dims>>.PadH")
    conn.clear_expression.return_value = make_clear_expression_success("Pad", "Length")
    conn.list_expressions.return_value = {
        "success": True,
        "ok": True,
        "object": "Pad",
        "expressions": [],
        "count": 0,
    }
    conn.body_create.return_value = make_body_create_success("Body", "Body")
    conn.body_set_tip.return_value = make_body_set_tip_success("Body", "Pad", "Pad")
    conn.sketch_edit_constraint.return_value = {"success": True, "sketch": "Sk"}
    conn.sketch_add_constraint.return_value = {"success": True}
    return conn


def _fail_conn(error="oops"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.spreadsheet_create.return_value = make_spreadsheet_create_failure("FAILED", error)
    conn.set_expression.return_value = make_set_expression_failure("FAILED", error)
    conn.clear_expression.return_value = make_clear_expression_failure("FAILED", error)
    conn.list_expressions.return_value = {"success": False, "error_code": "FAILED", "error": error}
    conn.body_create.return_value = make_body_create_failure("BODY_CREATE_FAILED", error)
    conn.body_set_tip.return_value = make_body_set_tip_failure("BODY_SET_TIP_FAILED", error)
    conn.execute_code.return_value = {"success": False, "error": error}
    for method_name in (
        "spreadsheet_set_cells",
        "spreadsheet_set_alias",
        "sketch_edit_constraint",
        "sketch_add_constraint",
    ):
        getattr(conn, method_name).return_value = {"success": False, "error": error}
    return conn


def test_spreadsheet_create_code():
    conn = _ok_conn()
    resp = spreadsheet_create_operation(conn, True, "Doc", "Dims")
    assert not resp.isError
    conn.spreadsheet_create.assert_called_once_with("Doc", "Dims")
    conn.execute_code.assert_not_called()


def test_spreadsheet_set_cells_and_alias():
    conn = _ok_conn()
    cells = [{"address": "A1", "value": 2.5, "alias": "Wall"}]
    spreadsheet_set_cells_operation(conn, True, "Doc", "Dims", cells)
    spreadsheet_set_alias_operation(conn, True, "Doc", "Dims", "B1", "Bore")
    conn.execute_code.assert_not_called()
    spreadsheet_list_aliases_operation(conn, True, "Doc", "Dims")
    spreadsheet_get_cells_operation(conn, True, "Doc", "Dims", ["A1", {"alias": "Wall"}])
    conn.spreadsheet_set_cells.assert_called_once_with("Doc", "Dims", cells)
    conn.spreadsheet_set_alias.assert_called_once_with("Doc", "Dims", "B1", "Bore")
    conn.spreadsheet_list_aliases.assert_called_once_with("Doc", "Dims")
    conn.spreadsheet_get_cells.assert_called_once_with("Doc", "Dims", ["A1", {"alias": "Wall"}])


def test_spreadsheet_set_cells_rejects_empty():
    resp = spreadsheet_set_cells_operation(_ok_conn(), True, "Doc", "Dims", [])
    assert resp.isError


def test_set_clear_list_expression():
    conn = _ok_conn()
    set_expression_operation(conn, True, "Doc", "Pad", "Length", "<<Dims>>.PadH")
    clear_expression_operation(conn, True, "Doc", "Pad", "Length")
    conn.execute_code.assert_not_called()
    list_expressions_operation(conn, True, "Doc", "Pad")
    conn.set_expression.assert_called_once_with("Doc", "Pad", "Length", "<<Dims>>.PadH")
    conn.clear_expression.assert_called_once_with("Doc", "Pad", "Length")
    conn.list_expressions.assert_called_once_with("Doc", "Pad")


def test_set_expression_constraints_path():
    conn = _ok_conn()
    set_expression_operation(conn, True, "Doc", "Sketch", "Constraints[0]", "<<Dims>>.Wall")
    conn.set_expression.assert_called_once_with("Doc", "Sketch", "Constraints[0]", "<<Dims>>.Wall")
    conn.execute_code.assert_not_called()


def test_body_and_attach():
    conn = _ok_conn()
    body_create_operation(conn, True, "Doc", "Body")
    conn.body_create.assert_called_once_with("Doc", "Body")
    body_set_tip_operation(conn, True, "Doc", "Body", "Pad")
    conn.body_set_tip.assert_called_once_with("Doc", "Body", "Pad")
    conn.execute_code.assert_not_called()

    conn.sketch_attach.return_value = make_sketch_attach_success("Sketch", "origin_plane", "XY_Plane", "")
    resp = sketch_attach_operation(conn, True, "Doc", "Sketch", "XY_Plane")
    assert not resp.isError
    conn.sketch_attach.assert_called_with("Doc", "Sketch", "XY_Plane")

    conn.sketch_attach.reset_mock()
    conn.sketch_attach.return_value = make_sketch_attach_success("Sketch", "face_ref", "Box", "Face1")
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
    conn.sketch_attach.return_value = make_sketch_attach_success("Sketch", "origin_plane", "XY_Plane", "")
    sketch_attach_operation(
        conn, True, "Doc", "Sketch", "XY_Plane", attachment_offset=offset
    )
    conn.sketch_attach.assert_called_once_with("Doc", "Sketch", "XY_Plane", offset)


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"error": "rejected"},
        {"error_code": "REJECTED"},
        {"success": True},
        {"success": True, "ok": True, "body": ""},
        {"success": True, "ok": True, "body": "Body"},
        {
            "success": True,
            "ok": True,
            "body": "Body",
            "label": "Body",
            "error": "contradictory",
        },
    ],
)
def test_body_create_rejects_malformed_or_contradictory_rpc_results(result):
    conn = _ok_conn()
    conn.body_create.return_value = result

    response = body_create_operation(conn, True, "Doc", "Body")

    assert response.isError


def test_body_create_accepts_actual_assigned_name_response():
    conn = _ok_conn()
    conn.body_create.return_value = make_body_create_success("Body001", "Main body")

    response = body_create_operation(conn, True, "Doc", "RequestedBody")

    assert response.isError is False
    conn.body_create.assert_called_once_with("Doc", "RequestedBody")


def test_named_constraints_in_code():
    conn = _ok_conn()
    typed = {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "sketch": "Sk",
        "constraint_index": 0,
    }
    conn.sketch_constrain_radius.return_value = typed
    conn.sketch_constrain_distance.return_value = typed
    sketch_constrain_radius_operation(conn, True, "Doc", "Sk", 0, 5.0, name="BoreR")
    conn.sketch_constrain_radius.assert_called_once_with("Doc", "Sk", 0, 5.0, "BoreR")
    sketch_constrain_distance_operation(conn, True, "Doc", "Sk", 1, 10.0, name="WallThick")
    conn.sketch_constrain_distance.assert_called_once_with("Doc", "Sk", 1, 10.0, None, "WallThick")
    conn.sketch_add_constraint.return_value = {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "sketch": "Sk",
        "added_count": 1,
    }
    resp = sketch_add_constraint_operation(
        conn,
        True,
        "Doc",
        "Sk",
        [{"type": "Radius", "geo": 0, "value": 3.0, "name": "R1"}],
    )
    assert resp.isError is False
    conn.sketch_add_constraint.assert_called_once()
    assert conn.sketch_add_constraint.call_args.args[2][0]["name"] == "R1"
    conn.execute_code.assert_not_called()


def test_sketch_edit_constraint_requires_identity():
    resp = sketch_edit_constraint_operation(_ok_conn(), True, "Doc", "Sk", value=2.0)
    assert resp.isError
    conn = _ok_conn()
    conn.sketch_edit_constraint.return_value = {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "committed",
        "committed": True,
        "retry_safe": False,
        "sketch": "Sk",
        "index": 0,
        "name": "WallThick",
    }
    resp = sketch_edit_constraint_operation(conn, True, "Doc", "Sk", value=4.0, name="WallThick")
    assert resp.isError is False
    conn.sketch_edit_constraint.assert_called_once_with("Doc", "Sk", 4.0, "WallThick", None)
    conn.execute_code.assert_not_called()


def test_diagnose_parametric_routes_typed_rpc():
    conn = _ok_conn()
    conn.diagnose_parametric.return_value = {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "observed",
        "retry_safe": False,
        "expression_issues": [],
        "invalid_objects": [],
    }
    diagnose_parametric_operation(conn, True, "Doc")
    conn.diagnose_parametric.assert_called_with("Doc", None)
    diagnose_parametric_operation(conn, True, "Doc", "Pad")
    conn.diagnose_parametric.assert_called_with("Doc", "Pad")


def test_failures_surface():
    assert spreadsheet_create_operation(_fail_conn(), True, "Doc", "Dims").isError
    assert set_expression_operation(_fail_conn(), True, "Doc", "Pad", "Length", "x").isError
    assert body_create_operation(_fail_conn(), True, "Doc", "Body").isError
    assert body_set_tip_operation(_fail_conn(), True, "Doc", "Body", "Pad").isError
    fail = _fail_conn()
    fail.sketch_attach.return_value = make_sketch_attach_failure("SKETCH_NOT_FOUND", "nope")
    assert sketch_attach_operation(fail, True, "Doc", "Sketch", "XY_Plane").isError
