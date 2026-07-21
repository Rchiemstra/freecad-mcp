"""
Diagnostics operations — read-only tools that surface the silent FreeCAD
behaviours called out in doc/mcp-feedback.md (P1 cross-body placement drop,
P8 axis/normal confusion, face/edge indexing fragility).

These do not mutate the document.
"""
from __future__ import annotations

import json
import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, text_response, tool_ok
from ..template_resources import render_template_lines, render_template_text
from .p7_assembly import _doc_preamble, _run_json_code, _shared_helpers


def _response_text(resp: ToolResponse) -> str:
    return "".join(
        item.text for item in resp.content if getattr(item, "type", "") == "text"
    )


def _diag_preamble(doc_name: str) -> list[str]:
    return _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "diagnostics/body_subpath_helpers.py.txt"
    )

logger = logging.getLogger("FreeCADMCPserver")


def preview_attachment_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    datum_name: str,
) -> ToolResponse:
    """I1 — preview an existing datum's attachment.

    Returns the support reference, the support face/edge global centre and
    normal, the datum's global base/normal, the owning bodies and their
    placements, ``source_body_placement_dropped`` (the P1 risk flag), and a
    signed distance + normal-angle diff between the datum and its support.

    Read-only. Saves the agent from rebuilding the whole model to discover that
    a cross-body datum dropped the source body's placement.
    """
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/preview_attachment.py.txt",
        datum_name=repr(datum_name),
    )]
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(code),
        "Failed to preview attachment",
        screenshot=False,
        document=doc_name,
    )


def _find_subshapes_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    kind: str,
    type_filter: str | None,
    normal_approx: dict | list | None,
    center_approx: dict | list | None,
    radius: float | None,
    tol: float,
    center_tol: float,
    limit: int,
) -> ToolResponse:
    """I4 — find_faces / find_edges by geometry. See ``find_faces_operation``."""
    kind_singular = "Face" if kind == "Faces" else "Edge"
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/find_subshapes.py.txt",
        object_name=repr(object_name),
        kind=repr(kind),
        kind_singular=repr(kind_singular),
        type_filter=repr(type_filter),
        normal_approx=repr(normal_approx),
        center_approx=repr(center_approx),
        radius=repr(radius),
        tol=repr(tol),
        center_tol=repr(center_tol),
        limit=repr(limit),
    )]
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(code),
        f"Failed to find {kind_singular.lower()}s",
        screenshot=False,
        document=doc_name,
    )


def find_faces_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    type: str | None = None,
    normal_approx: dict | list | None = None,
    center_approx: dict | list | None = None,
    radius: float | None = None,
    tol: float = 1e-3,
    center_tol: float = 1.0,
    limit: int = 10,
) -> ToolResponse:
    """I4 — list faces of an object matching geometric criteria, ranked.

    Filters by surface ``type`` ('Plane'/'Cylinder'/'Cone'/'Sphere'/'Toroid'),
    a ``normal_approx`` vector (kept when parallel within ``tol``), a
    ``center_approx`` point (kept when within ``center_tol`` mm), and/or a
    ``radius``. Returns each match's global centre, global normal, area and
    radius, ranked by closeness to ``center_approx`` (or by area descending).

    Removes face-index fragility: ask for "the top planar face" instead of
    guessing ``Face6``.
    """
    return _find_subshapes_operation(
        freecad, only_text_feedback, doc_name, object_name, "Faces",
        type, normal_approx, center_approx, radius, tol, center_tol, limit,
    )


def find_edges_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    type: str | None = None,
    direction_approx: dict | list | None = None,
    center_approx: dict | list | None = None,
    radius: float | None = None,
    tol: float = 1e-3,
    center_tol: float = 1.0,
    limit: int = 10,
) -> ToolResponse:
    """I4 — list edges of an object matching geometric criteria, ranked.

    Filters by curve ``type`` ('Line'/'Circle'/'Ellipse'/'BSplineCurve'), a
    ``direction_approx`` vector (kept when the edge axis is parallel within
    ``tol``), a ``center_approx`` point, and/or a ``radius``. Returns each
    match's global centre, global direction, length and radius, ranked.
    """
    return _find_subshapes_operation(
        freecad, only_text_feedback, doc_name, object_name, "Edges",
        type, direction_approx, center_approx, radius, tol, center_tol, limit,
    )


def _subshape_pose_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    subshape: str,
) -> ToolResponse:
    """M6 — shared face_normal / edge_axis implementation. Returns the global
    centre, global normal/direction, type and radius of a single subshape."""
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/subshape_pose.py.txt",
        object_name=repr(object_name),
        subshape=repr(subshape),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to inspect subshape", screenshot=False, document=doc_name,
    )


def face_normal_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    face: str,
) -> ToolResponse:
    """M6 — return the global normal (and centre) of a face.

    Avoids the P8 Direction-vs-Axis trap by deriving the vector from the face
    geometry via ``normalAt`` rotated by the object's global placement. Returns
    JSON ``{ok, object, subshape, type, global_center, global_normal, radius}``.
    """
    return _subshape_pose_operation(
        freecad, only_text_feedback, doc_name, object_name, face,
    )


def edge_axis_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    edge: str,
) -> ToolResponse:
    """M6 — return the global axis/direction (and centre) of an edge.

    Avoids the P8 Direction-vs-Axis trap by deriving the vector from the curve
    geometry rotated by the object's global placement. Returns JSON
    ``{ok, object, subshape, type, global_center, global_normal, radius}``.
    """
    return _subshape_pose_operation(
        freecad, only_text_feedback, doc_name, object_name, edge,
    )


def placement_audit_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
) -> ToolResponse:
    """M3 — audit placements: per Body/Part list Placement, getGlobalPlacement()
    base, and the cross-body datums that reference it. Read-only; returns JSON
    ``{ok, doc, bodies: [{name, type, placement_base, placement_rotation,
    global_placement_base, cross_body_datums}]}``.
    """
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/placement_audit.py.txt",
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to audit placements", screenshot=False, document=doc_name,
    )


def relink_references_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    from_obj: str,
    to_obj: str,
) -> ToolResponse:
    """M5 — re-point every reference to ``from_obj`` so it points to ``to_obj``,
    across all link-type properties of all document objects. Makes rebuilds
    non-destructive. Returns JSON ``{ok, from, to, relinked, count}``.
    """
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/relink_references.py.txt",
        from_obj=repr(from_obj),
        to_obj=repr(to_obj),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to relink references", screenshot=False, document=doc_name,
    )


def capture_state_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_names: list[str] | None = None,
) -> ToolResponse:
    """I10 — capture a compact geometric state (placement + bbox + face/edge
    counts) for ``object_names`` (all objects when None). The returned JSON can
    be passed to ``geometric_diff`` to produce a text-only diff when a viewable
    image can't be returned (P10 fallback).
    """
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/capture_state.py.txt",
        object_names=repr(object_names),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to capture state", screenshot=False, document=doc_name,
    )


def _diff_states(before: dict, current: dict) -> dict:
    before_objs = {o["name"]: o for o in before.get("objects", [])}
    current_objs = {o["name"]: o for o in current.get("objects", [])}
    diffs = []
    for name in sorted(set(before_objs) | set(current_objs)):
        b = before_objs.get(name)
        c = current_objs.get(name)
        entry = {
            "name": name,
            "bbox_before": b.get("bbox") if b else None,
            "bbox_after": c.get("bbox") if c else None,
            "placement_before": {
                "base": b.get("placement_base"),
                "rotation": b.get("placement_rotation"),
            } if b else None,
            "placement_after": {
                "base": c.get("placement_base"),
                "rotation": c.get("placement_rotation"),
            } if c else None,
            "faces_before": b.get("face_count") if b else None,
            "faces_after": c.get("face_count") if c else None,
            "added": b is None,
            "removed": c is None,
        }
        fb = entry["faces_before"]
        fa = entry["faces_after"]
        if fb is not None and fa is not None and fa > fb:
            entry["faces_added"] = fa - fb
            entry["faces_removed"] = 0
        elif fb is not None and fa is not None and fb > fa:
            entry["faces_added"] = 0
            entry["faces_removed"] = fb - fa
        else:
            entry["faces_added"] = 0
            entry["faces_removed"] = 0
        entry["changed"] = (
            entry["added"] or entry["removed"]
            or entry["bbox_before"] != entry["bbox_after"]
            or entry["placement_before"] != entry["placement_after"]
            or entry["faces_added"] or entry["faces_removed"]
        )
        diffs.append(entry)
    return {"ok": True, "doc": current.get("doc", before.get("doc")), "diffs": diffs}


def geometric_diff_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    before: dict,
    object_names: list[str] | None = None,
) -> ToolResponse:
    """I10 — structured geometric diff between a captured ``before`` state and
    the current document state. The P10 text-only fallback: returns JSON
    ``{ok, doc, diffs: [{name, bbox_before/after, placement_before/after,
    faces_added/removed, changed}]}`` when a viewable image can't be returned.
    """
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/capture_state.py.txt",
        object_names=repr(object_names),
    )]
    resp = _run_json_code(
        freecad, True, "\n".join(code),
        "Failed to capture state for diff", screenshot=False, document=doc_name,
    )
    text = _response_text(resp)
    try:
        current = json.loads(text)
    except Exception:
        return tool_ok("Failed to capture current state for diff: " + text)
    return tool_ok(json.dumps(_diff_states(before, current)))


def create_placement_binder_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    owner_body: str,
    name: str,
    source: str,
    relative: bool = True,
    bind_mode: str = "Synchronized",
) -> ToolResponse:
    code = _diag_preamble(doc_name) + [render_template_text(
        "diagnostics/create_placement_binder.py.txt",
        owner_body=repr(owner_body),
        binder_name=repr(name),
        source=repr(source),
        relative=repr(relative),
        bind_mode=repr(bind_mode),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to create placement-aware binder",
        screenshot=True,
        document=doc_name,
        read_only=False,
    )


def create_placement_datum_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    owner_body: str,
    name: str,
    source: str,
    relative: bool = True,
    offset: list[float] | None = None,
) -> ToolResponse:
    code = _diag_preamble(doc_name) + [render_template_text(
        "diagnostics/create_placement_datum.py.txt",
        owner_body=repr(owner_body),
        datum_name=repr(name),
        source=repr(source),
        relative=repr(relative),
        offset=repr(offset or [0, 0, 0]),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to create placement-aware datum",
        screenshot=True,
        document=doc_name,
        read_only=False,
    )


def run_transaction_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    label: str,
    code: str,
    dry_run: bool = False,
    commit_on_success: bool = True,
) -> ToolResponse:
    preamble = _doc_preamble(doc_name)
    body = render_template_text(
        "diagnostics/run_transaction.py.txt",
        label=repr(label),
        code=repr(code),
        dry_run=repr(dry_run),
        commit_on_success=repr(commit_on_success),
    )
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(preamble) + "\n" + body,
        "Failed to run transaction",
        screenshot=True,
        document=doc_name,
        read_only=False,
    )


def validate_movement_follow_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    source: str,
    dependents: list[str],
    translation: list[float],
    axis: list[float],
    angle_deg: float,
    restore: bool = True,
    tolerance: float = 1e-7,
) -> ToolResponse:
    code = _diag_preamble(doc_name) + [render_template_text(
        "diagnostics/validate_movement_follow.py.txt",
        source=repr(source),
        dependents=repr(dependents),
        translation=repr(translation),
        axis=repr(axis),
        angle_deg=repr(angle_deg),
        restore=repr(restore),
        tolerance=repr(tolerance),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed movement-follow validation",
        screenshot=False,
        document=doc_name,
        read_only=False,
    )


def audit_hardcoded_dimensions_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
    flag_aliases: bool = True,
) -> ToolResponse:
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/audit_hardcoded_dimensions.py.txt",
        body_name=repr(body_name),
        flag_aliases=repr(flag_aliases),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed hard-coded dimension audit",
        screenshot=False,
        document=doc_name,
    )


def inspect_geometry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    subshape: str | None = None,
    activate: bool = False,
    restore_active_document: bool = True,
) -> ToolResponse:
    if activate:
        try:
            freecad.activate_document(doc_name)
        except Exception as exc:
            logger.warning("inspect_geometry activate_document failed: %s", exc)
        try:
            selection = [f"{object_name}:{subshape}"] if subshape else [object_name]
            freecad.select_subshapes(doc_name, selection, clear=True)
        except Exception as exc:
            logger.warning("inspect_geometry select_subshapes failed: %s", exc)

    code = _diag_preamble(doc_name) + [render_template_text(
        "diagnostics/inspect_geometry.py.txt",
        object_name=repr(object_name),
        subshape=repr(subshape),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed geometry inspection",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )


def get_dependency_graph_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    root: str,
) -> ToolResponse:
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/get_dependency_graph.py.txt",
        root=repr(root),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to build dependency graph",
        screenshot=False,
        document=doc_name,
    )


def match_subshape_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    source_object: str,
    source_subshape: str,
    target_object: str,
    limit: int = 10,
    tolerance: float = 1.0,
) -> ToolResponse:
    code = _diag_preamble(doc_name) + [render_template_text(
        "diagnostics/match_subshape.py.txt",
        source_object=repr(source_object),
        source_subshape=repr(source_subshape),
        target_object=repr(target_object),
        limit=repr(limit),
        tolerance=repr(tolerance),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed subshape matching",
        screenshot=False,
        document=doc_name,
    )
