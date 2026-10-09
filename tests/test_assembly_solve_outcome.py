"""Assembly solves and joints must not report success when nothing happens.

A live stress run created joints on components outside the assembly, then
``solve_assembly`` returned success with ``status: "0"`` while no part moved.
``assembly.solve()`` returns -6 when no part is grounded and -1 when the
solver fails; both were reported as success. The solver status was also
dropped from the flattened MCP envelope, where ``status`` is reserved.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP._shared.protocol.solve_assembly_contract import (
    make_solve_assembly_success,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import assembly_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.typed_runtime import (
    TypedMutationError,
)
from freecad_mcp.operations.parametric_ops.solve_assembly import solve_assembly_operation

pytestmark = pytest.mark.unit


def _document(solve_status):
    assembly = SimpleNamespace(
        Name="Asm",
        TypeId="Assembly::AssemblyObject",
        isDerivedFrom=lambda t: t == "Assembly::AssemblyObject",
        solve=lambda: solve_status,
    )
    return SimpleNamespace(getObject={"Asm": assembly}.get)


def test_a_clean_solve_reports_its_status():
    result = assembly_actions.solve_assembly(_document(0), "Asm")

    assert result == {"assembly": "Asm", "method": "assembly.solve()", "status": "0"}


@pytest.mark.parametrize(
    "status, fragment",
    [(-6, "no grounded component"), (-1, "solver could not satisfy the joints")],
)
def test_a_failed_solve_is_an_error(status, fragment):
    with pytest.raises(TypedMutationError) as caught:
        assembly_actions.solve_assembly(_document(status), "Asm")

    assert caught.value.code == "ASSEMBLY_SOLVE_FAILED"
    assert fragment in str(caught.value)
    assert f"status {status}" in str(caught.value)


def test_the_solver_status_survives_the_envelope():
    connection = SimpleNamespace(
        solve_assembly=lambda *_args: make_solve_assembly_success(
            "Asm", "assembly.solve()", "0"
        )
    )

    response = solve_assembly_operation(connection, True, "Doc", "Asm")

    assert not response.isError
    assert response.structuredContent["solver_status"] == "0"


class JointCreationError(Exception):
    pass


@pytest.mark.parametrize("action", ["joint", "grounded"])
def test_assembly_api_argument_errors_are_invalid_arguments(monkeypatch, action):
    def refuse(*_args, **_kwargs):
        raise JointCreationError("ref2 'PartB' is not part of assembly 'Asm'")

    api = SimpleNamespace(
        makeJointReference=lambda obj, element, vertex: [obj, [element, vertex]],
        createJoint=refuse,
        createGroundedJoint=refuse,
    )
    monkeypatch.setattr(assembly_actions, "_assembly_api", lambda: api)
    document = _document(0)
    part_b = SimpleNamespace(Name="PartB")
    document.getObject = {"Asm": document.getObject("Asm"), "PartA": part_b, "PartB": part_b}.get

    with pytest.raises(TypedMutationError) as caught:
        if action == "joint":
            assembly_actions.create_joint(
                document,
                assembly_name="Asm",
                joint_type="Revolute",
                ref1_component="PartA",
                ref2_component="PartB",
                ref1_element="Face6",
                ref2_element="Face3",
                ref1_vertex=None,
                ref2_vertex=None,
                label=None,
                solve=True,
                presolve=True,
                properties={},
            )
        else:
            assembly_actions.create_grounded_joint(
                document, assembly_name="Asm", component_name="PartB", label=None
            )

    assert caught.value.code == "INVALID_ARGUMENT"
    assert "not part of assembly" in str(caught.value)
