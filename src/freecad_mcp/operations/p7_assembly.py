"""
P7 - Assembly-aware references, sketch inspection, path wires, and pipe sweeps.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, add_screenshot_if_available, text_response
from ..template_resources import render_template_lines, render_template_text

logger = logging.getLogger("FreeCADMCPserver")


def _extract_execute_output(message: str) -> str:
    marker = "Output:"
    if marker in message:
        return message.split(marker, 1)[1].strip()
    return message.strip()


_PREFLIGHT_SENTINEL = "__PREFLIGHT_WARN__"


def _extract_preflight(output: str) -> tuple[str, str]:
    """I6 — pull the `__PREFLIGHT_WARN__` sentinel out of the execute output.

    Returns (clean_output, warning_text). The clean_output is the original JSON
    payload with the sentinel line removed (so JSON callers stay happy); the
    warning_text is a human-readable block surfaced to the agent when a
    cross-body attachment risk was detected at creation time (P1).
    """
    idx = output.rfind(_PREFLIGHT_SENTINEL)
    if idx < 0:
        return output, ""
    payload = output[idx + len(_PREFLIGHT_SENTINEL):]
    payload = payload.strip().splitlines()[0] if payload.strip() else ""
    clean = output[:idx].rstrip()
    try:
        warns = json.loads(payload) if payload else []
    except Exception:
        warns = []
    if not warns:
        return clean, ""
    lines = []
    for w in warns:
        lines.append(
            f"PREFLIGHT WARNING ({w.get('datum','?')}): {w.get('message','?')}"
        )
    return clean, "\n".join(lines)


def _run_json_code(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
    fail_prefix: str,
    *,
    screenshot: bool = False,
) -> ToolResponse:
    try:
        res = freecad.execute_code(code)
        image = freecad.get_active_screenshot() if screenshot else None
        if res.get("success"):
            output = _extract_execute_output(res.get("message", ""))
            output, preflight = _extract_preflight(output)
            errors = res.get("recompute_errors", [])
            if errors and output.endswith("}"):
                # Keep the response JSON-first without parsing possibly large payloads.
                output += "\n" + str({"recompute_errors": errors})
            if preflight:
                output = output + "\n" + preflight
            return add_screenshot_if_available(text_response(output), image, only_text_feedback)
        return text_response(f"{fail_prefix}: {res.get('error', res.get('message', 'unknown error'))}")
    except Exception as exc:
        logger.error("%s: %s", fail_prefix, exc)
        return text_response(f"{fail_prefix}: {exc}")


def _validate_if_exists(if_exists: str) -> ToolResponse | None:
    if if_exists not in {"error", "skip", "replace"}:
        return text_response("if_exists must be one of: error, skip, replace")
    return None


def _doc_preamble(doc_name: str) -> list[str]:
    return render_template_lines(
        "p7_assembly/doc_preamble.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
    )


def _shared_helpers() -> list[str]:
    return render_template_lines("p7_assembly/shared_helpers.py.txt")


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
    )


def get_document_tree_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    root_filter: str | None = None,
    max_depth: int = 4,
    include: list[str] | None = None,
    include_properties: list[str] | None = None,
    selected_nodes: list[str] | None = None,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/get_document_tree.py.txt",
        root_filter=repr(root_filter),
        max_depth=repr(max_depth),
        include=repr(include),
        include_properties=repr(include_properties),
        selected_nodes=repr(selected_nodes),
    )
    return _run_json_code(freecad, True, "\n".join(lines), "Failed to get document tree")


def create_part_container_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    part_name: str,
    parent_container: str | None = None,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/create_part_container.py.txt",
        part_name=repr(part_name),
        parent_container=repr(parent_container),
        if_exists=repr(if_exists),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create part container",
        screenshot=True,
    )


def move_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    target_container: str,
    remove_from_old_parent: bool = True,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/move_object.py.txt",
        obj_name=repr(obj_name),
        target_container=repr(target_container),
        remove_from_old_parent=repr(remove_from_old_parent),
    )
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to move object", screenshot=True)


def create_subshape_binder_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    binder_name: str,
    source_object: str,
    sub_elements: list[str] | None = None,
    target_body: str | None = None,
    target_container: str | None = None,
    relative: bool = False,
    sync_placement: bool = True,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    binder_code = render_template_text(
        "p7_assembly/create_subshape_binder.py.txt",
        binder_name=repr(binder_name),
        source_name=repr(source_object),
        subs=repr(sub_elements),
        target_body_name=repr(target_body),
        target_container_name=repr(target_container),
        relative=repr(relative),
        sync_placement=repr(sync_placement),
        if_exists=repr(if_exists),
    )
    lines = _doc_preamble(doc_name) + _shared_helpers() + binder_code.strip().splitlines() + render_template_lines(
        "diagnostics/cross_body_preflight.py.txt", obj_name=repr(binder_name),
    )
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to create subshape binder", screenshot=True)


def create_datum_plane_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    plane_name: str,
    body_name: str,
    mode: str,
    source_ref: str | None = None,
    face_a: str | None = None,
    face_b: str | None = None,
    offset_along_normal: list[float] | None = None,
    map_mode: str = "FlatFace",
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/create_datum_plane.py.txt",
        plane_name=repr(plane_name),
        body_name=repr(body_name),
        mode=repr(mode),
        source_ref=repr(source_ref),
        face_a=repr(face_a),
        face_b=repr(face_b),
        offset_along_normal=repr(offset_along_normal),
        map_mode=repr(map_mode),
        if_exists=repr(if_exists),
    ) + render_template_lines(
        "diagnostics/cross_body_preflight.py.txt", obj_name=repr(plane_name),
    )
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to create datum plane", screenshot=True)


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
        "Failed to solve assembly", screenshot=True,
    )


def get_sketch_geometry_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    sketch_name: str,
    include_constraints: bool = True,
    include_external: bool = True,
    global_coords: bool = True,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/get_sketch_geometry.py.txt",
        sketch_name=repr(sketch_name),
        include_constraints=repr(include_constraints),
        include_external=repr(include_external),
        global_coords=repr(global_coords),
    )
    return _run_json_code(freecad, True, "\n".join(lines), "Failed to get sketch geometry")


def sketch_add_external_projection_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    source_ref: str,
    projection_mode: str = "auto",
    defining: bool = False,
) -> ToolResponse:
    if projection_mode not in {"auto", "edge", "face", "point"}:
        return text_response("projection_mode must be one of: auto, edge, face, point")
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/sketch_add_external_projection.py.txt",
        sketch_name=repr(sketch_name),
        source_ref=repr(source_ref),
        projection_mode=repr(projection_mode),
        defining=repr(defining),
    )
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to add external projection", screenshot=True)


def build_path_wire_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    wire_name: str,
    segments: list[dict[str, Any]],
    tolerance_mm: float = 0.5,
    container: str | None = None,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/build_path_wire.py.txt",
        wire_name=repr(wire_name),
        segments=repr(segments),
        tolerance_mm=repr(tolerance_mm),
        container=repr(container),
        if_exists=repr(if_exists),
    )
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to build path wire", screenshot=True)


def sweep_pipe_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    path_wire: str,
    diameter_mm: float,
    solid_name: str,
    profile_mode: str = "frenet",
    color: list[float] | None = None,
    container: str | None = None,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    sweep_code = render_template_text(
        "p7_assembly/sweep_pipe.py.txt",
        path_wire_name=repr(path_wire),
        diameter=repr(diameter_mm),
        solid_name=repr(solid_name),
        profile_mode=repr(profile_mode),
        color=repr(color),
        container_name=repr(container),
        if_exists=repr(if_exists),
    )
    lines = _doc_preamble(doc_name) + _shared_helpers() + sweep_code.strip().splitlines()
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to sweep pipe", screenshot=True)
