from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server.execute_code_analysis import analyze_execute_code
from addon.FreeCADMCP.rpc_server.mutation_guard import make_method_spec
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.core import (
    sketch_delete_constraint_operation,
    sketch_delete_geometry_operation,
)


class _Constraint:
    def __init__(self, constraint_type: str, name: str = ""):
        self.Type = constraint_type
        self.Name = name


class _Geometry:
    def __init__(self, type_id: str):
        self.TypeId = type_id


class _Sketch:
    Name = "Sketch"

    def __init__(self):
        self.Constraints = [
            _Constraint("Horizontal"),
            _Constraint("Block"),
            _Constraint("Radius", "MainRadius"),
            _Constraint("Block", "Pinned"),
        ]
        self.Geometry = [
            _Geometry("Part::GeomLineSegment"),
            _Geometry("Part::GeomCircle"),
            _Geometry("Part::GeomLineSegment"),
        ]
        self.deleted_constraint_batches = []
        self.deleted_geometry_batches = []

    def delConstraints(self, indices, update_geometry):
        self.deleted_constraint_batches.append((list(indices), update_geometry))
        for index in sorted(indices, reverse=True):
            del self.Constraints[index]

    def delGeometries(self, indices):
        self.deleted_geometry_batches.append(list(indices))
        for index in sorted(indices, reverse=True):
            del self.Geometry[index]
        # Model FreeCAD removing one constraint that references deleted geometry.
        if self.Constraints:
            self.Constraints.pop(0)

    def getConstruction(self, index):
        return index == 2


class _Document:
    Name = "Doc"

    def __init__(self, sketch):
        self.sketch = sketch
        self.recompute_calls = 0

    def getObject(self, name):
        return self.sketch if name == self.sketch.Name else None

    def recompute(self):
        self.recompute_calls += 1


def _install_freecad(monkeypatch):
    sketch = _Sketch()
    document = _Document(sketch)
    freecad = SimpleNamespace(
        getDocument=lambda name: document if name == document.Name else None
    )
    monkeypatch.setattr(rpc_server, "FreeCAD", freecad)
    return sketch, document


def test_constraint_deletion_resolves_names_and_indices_before_one_batch(monkeypatch):
    sketch, document = _install_freecad(monkeypatch)

    result = rpc_server.FreeCADRPC()._sketch_delete_constraint_gui(
        "Doc",
        "Sketch",
        [1, 1],
        ["Pinned"],
    )

    assert result["success"] is True
    assert result["deleted_count"] == 2
    assert [item["index"] for item in result["deleted_constraints"]] == [1, 3]
    assert [item["type"] for item in result["deleted_constraints"]] == [
        "Block",
        "Block",
    ]
    assert sketch.deleted_constraint_batches == [([1, 3], True)]
    assert result["remaining_constraint_count"] == 2
    assert document.recompute_calls == 1


def test_constraint_deletion_rejects_invalid_selector_before_mutation(monkeypatch):
    sketch, document = _install_freecad(monkeypatch)

    result = rpc_server.FreeCADRPC()._sketch_delete_constraint_gui(
        "Doc",
        "Sketch",
        [99],
        None,
    )

    assert result["success"] is False
    assert result["error_code"] == "CONSTRAINT_INDEX_OUT_OF_RANGE"
    assert sketch.deleted_constraint_batches == []
    assert document.recompute_calls == 0


def test_geometry_deletion_is_batched_and_reports_dependent_constraints(monkeypatch):
    sketch, document = _install_freecad(monkeypatch)

    result = rpc_server.FreeCADRPC()._sketch_delete_geometry_gui(
        "Doc",
        "Sketch",
        [2, 0, 2],
    )

    assert result["success"] is True
    assert result["deleted_count"] == 2
    assert [item["index"] for item in result["deleted_geometry"]] == [0, 2]
    assert result["deleted_geometry"][1]["construction"] is True
    assert result["dependent_constraints_removed"] == 1
    assert sketch.deleted_geometry_batches == [[0, 2]]
    assert result["remaining_geometry_count"] == 1
    assert document.recompute_calls == 1


def test_operation_wrappers_use_typed_rpc_methods():
    connection = MagicMock()
    connection.get_active_screenshot.return_value = None
    connection.sketch_delete_constraint.return_value = {
        "success": True,
        "deleted_count": 2,
    }
    connection.sketch_delete_geometry.return_value = {
        "success": True,
        "deleted_count": 1,
    }

    constraint_result = sketch_delete_constraint_operation(
        connection,
        True,
        "Doc",
        "Sketch",
        constraint_indices=[1],
        constraint_names=["Pinned"],
    )
    geometry_result = sketch_delete_geometry_operation(
        connection,
        True,
        "Doc",
        "Sketch",
        [0],
    )

    assert constraint_result.isError is False
    assert geometry_result.isError is False
    connection.sketch_delete_constraint.assert_called_once_with(
        "Doc",
        "Sketch",
        [1],
        ["Pinned"],
    )
    connection.sketch_delete_geometry.assert_called_once_with(
        "Doc",
        "Sketch",
        [0],
    )
    connection.execute_code.assert_not_called()


def test_connection_routes_deletion_through_authenticated_mutation_v2():
    connection = object.__new__(FreeCADConnection)
    connection._invoke_mutation_v2 = MagicMock(
        side_effect=[
            {"success": True, "deleted_count": 1},
            {"success": True, "deleted_count": 2},
        ]
    )
    connection.server = MagicMock()

    constraint_result = connection.sketch_delete_constraint(
        "Doc",
        "Sketch",
        [3],
        [],
    )
    geometry_result = connection.sketch_delete_geometry(
        "Doc",
        "Sketch",
        [0, 2],
    )

    assert constraint_result["success"] is True
    assert geometry_result["success"] is True
    assert connection._invoke_mutation_v2.call_args_list[0].args[0] == (
        "sketch_delete_constraint"
    )
    assert connection._invoke_mutation_v2.call_args_list[1].args[0] == (
        "sketch_delete_geometry"
    )
    connection.server.sketch_delete_constraint.assert_not_called()
    connection.server.sketch_delete_geometry.assert_not_called()


def test_deletion_methods_get_transaction_recompute_and_validation_guards():
    for method in ("sketch_delete_constraint", "sketch_delete_geometry"):
        spec = make_method_spec(method, "MUTATING")
        assert spec.transaction is True
        assert spec.recompute is True
        assert spec.validator is not None


def test_execute_code_analysis_points_deletions_to_typed_tools():
    analysis = analyze_execute_code(
        "sketch.delConstraints([1, 2], True)\nsketch.delGeometries([0])"
    )

    assert analysis["typed_tool_suggestions"] == [
        "sketch_delete_constraint",
        "sketch_delete_geometry",
    ]
