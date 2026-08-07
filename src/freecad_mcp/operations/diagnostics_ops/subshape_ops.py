from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...template_resources import render_template_text
from ..p7_assembly import _doc_preamble, _run_json_code


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
    code = [*_doc_preamble(doc_name), render_template_text(
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
        read_only=True,
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
    code = [*_doc_preamble(doc_name), render_template_text(
        "diagnostics/subshape_pose.py.txt",
        object_name=repr(object_name),
        subshape=repr(subshape),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to inspect subshape", screenshot=False, document=doc_name,
        read_only=True,
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
