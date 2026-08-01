from __future__ import annotations

from typing import Any

from ...freecad_client import FreeCADConnection
from ...responses import ToolResponse
from ...template_resources import render_template_lines
from .helpers import (
    _doc_preamble,
    _run_json_code,
    _validate_if_exists,
)


def create_assembly_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    assembly_name: str = "Assembly",
    create_joint_group: bool = True,
    recompute: bool = False,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p7_assembly/create_assembly.py.txt",
        assembly_name=repr(assembly_name),
        create_joint_group=repr(create_joint_group),
        recompute=repr(recompute),
        if_exists=repr(if_exists),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create assembly",
        screenshot=True,
        document=doc_name,
        read_only=False,
    )

def create_assembly_grounded_joint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    assembly_name: str,
    component_name: str,
    label: str | None = None,
    recompute: bool = True,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p7_assembly/create_grounded_joint.py.txt",
        assembly_name=repr(assembly_name),
        component_name=repr(component_name),
        label=repr(label),
        recompute=repr(recompute),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create grounded assembly joint",
        screenshot=True,
        document=doc_name,
    )

def create_assembly_joint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    assembly_name: str,
    joint_type: str,
    ref1_component: str,
    ref2_component: str,
    ref1_element: str = "",
    ref2_element: str = "",
    ref1_vertex: str | None = None,
    ref2_vertex: str | None = None,
    label: str | None = None,
    solve: bool = True,
    presolve: bool = True,
    recompute: bool = True,
    properties: dict[str, Any] | None = None,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p7_assembly/create_joint.py.txt",
        assembly_name=repr(assembly_name),
        joint_type=repr(joint_type),
        ref1_component=repr(ref1_component),
        ref1_element=repr(ref1_element),
        ref1_vertex=repr(ref1_vertex),
        ref2_component=repr(ref2_component),
        ref2_element=repr(ref2_element),
        ref2_vertex=repr(ref2_vertex),
        label=repr(label),
        solve=repr(solve),
        presolve=repr(presolve),
        recompute=repr(recompute),
        properties=repr(properties or {}),
    ) + render_template_lines(
        "diagnostics/joint_preflight.py.txt",
        ref1_component=repr(ref1_component),
        ref2_component=repr(ref2_component),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create assembly joint",
        screenshot=True,
        document=doc_name,
    )

def solve_assembly_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    assembly_name: str,
) -> ToolResponse:
    """I9 — re-solve an Assembly after editing a joint or a referenced face.

    Tries ``assembly.solve()`` (C++), then ``JointObject.solveIfAllowed``, then a
    plain recompute, and reports which method succeeded. Returns JSON
    ``{ok, assembly, method, status}``. Fixes P9 (no documented solve API).
    """
    lines = _doc_preamble(doc_name) + render_template_lines(
        "p7_assembly/solve_assembly.py.txt",
        assembly_name=repr(assembly_name),
    )
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(lines),
        "Failed to solve assembly", screenshot=True, document=doc_name,
    )
