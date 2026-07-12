"""I9 e2e: solve_assembly re-solves a real Assembly via the internal solver
against a live FreeCAD (P9).

Build an assembly with a grounded component, then call solve_assembly_operation
and assert it succeeds (ok=True) using one of the known solve entry points.
"""
from __future__ import annotations

import json

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")
Sketcher = pytest.importorskip("Sketcher")

from freecad_mcp.operations.p7_assembly import (  # noqa: E402
    create_assembly_grounded_joint_operation,
    create_assembly_operation,
    solve_assembly_operation,
)

from tests.e2e._helpers import tool_response_text  # noqa: E402

pytestmark = pytest.mark.e2e


def _payload(response) -> dict:
    text = tool_response_text(response)
    if "Output:" in text:
        text = text.split("Output:", 1)[1].strip()
    return json.loads(text.splitlines()[0])


def test_solve_assembly_runs_the_solver(freecad_session):
    doc = freecad_session.doc

    asm = create_assembly_operation(
        freecad_session, True, doc.Name, "Asm", if_exists="replace",
    )
    assert _payload(asm)["ok"] is True

    comp = doc.addObject("Part::Box", "Comp1")
    comp.Length, comp.Width, comp.Height = 5.0, 5.0, 5.0
    FreeCAD.ActiveDocument.recompute()

    grounded = create_assembly_grounded_joint_operation(
        freecad_session, True, doc.Name, "Asm", "Comp1", recompute=True,
    )
    assert _payload(grounded)["ok"] is True

    solved = solve_assembly_operation(freecad_session, True, doc.Name, "Asm")
    payload = _payload(solved)
    assert payload["ok"] is True
    assert payload["assembly"] == "Asm"
    assert payload["method"] in {
        "assembly.solve()", "JointObject.solveIfAllowed", "recompute",
    }
