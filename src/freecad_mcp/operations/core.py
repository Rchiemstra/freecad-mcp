import json
import logging
from typing import Any

from mcp.types import ImageContent

from ..freecad_client import FreeCADConnection
from ..responses import (
    ToolResponse,
    add_screenshot_if_available,
    from_execute_result,
    json_response,
    text_response,
    tool_fail,
    tool_ok,
)
from ..execute_options import ExecuteOptions, merge_execute_options
from ..template_resources import read_template_lines, render_template_lines, render_template_text


logger = logging.getLogger("FreeCADMCPserver")


_RECOMPUTE_LOG_SENTINEL = "__RECOMPUTE_LOG__"


def _format_recompute_log(output: str) -> str:
    """I3 — turn the `__RECOMPUTE_LOG__` JSON sentinel in the execute output into a
    compact human-readable summary. Returns '' when nothing is flagged (all Clean),
    so mutating tools that build cleanly stay quiet."""
    idx = output.rfind(_RECOMPUTE_LOG_SENTINEL)
    if idx < 0:
        return ""
    payload = output[idx + len(_RECOMPUTE_LOG_SENTINEL):]
    # The sentinel is the last printed line; trim any trailing addon chatter.
    payload = payload.strip().splitlines()[0] if payload.strip() else ""
    try:
        flagged = json.loads(payload) if payload else []
    except Exception:
        return ""
    if not flagged:
        return ""
    parts = []
    for e in flagged:
        mark = "" if e.get("valid", True) else " <INVALID>"
        parts.append(f"{e.get('name','?')} ({e.get('state','?')}){mark}")
    return "Recompute log (non-clean): " + ", ".join(parts)


def create_document_operation(freecad: FreeCADConnection, name: str) -> ToolResponse:
    try:
        res = freecad.create_document(name)
        if res["success"]:
            return tool_ok(f"Document '{res['document_name']}' created successfully")
        return tool_fail(f"Failed to create document: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to create document: {str(e)}")
        return tool_fail(f"Failed to create document: {str(e)}")


def create_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] | None = None,
) -> ToolResponse:
    try:
        obj_data = {
            "Name": obj_name,
            "Type": obj_type,
            "Properties": obj_properties or {},
            "Analysis": analysis_name,
        }
        res = freecad.create_object(doc_name, obj_data)
        if res["success"]:
            response = tool_ok(f"Object '{res['object_name']}' created successfully")
        else:
            response = tool_fail(f"Failed to create object: {res['error']}")
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to create object: {str(e)}")
        return tool_fail(f"Failed to create object: {str(e)}")


def edit_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    obj_properties: dict[str, Any],
) -> ToolResponse:
    try:
        res = freecad.edit_object(doc_name, obj_name, {"Properties": obj_properties})
        if res["success"]:
            response = tool_ok(f"Object '{res['object_name']}' edited successfully")
        else:
            response = tool_fail(f"Failed to edit object: {res['error']}")
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to edit object: {str(e)}")
        return tool_fail(f"Failed to edit object: {str(e)}")


def delete_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    recursive: bool = False,
    force: bool = False,
) -> ToolResponse:
    """I5 — delete an object without silently orphaning its dependents (P6).

    FreeCAD's ``Document.removeObject`` deliberately does not remove an object's
    dependents, leaving them Invalid. This op instead:
      * ``recursive=True`` -> remove dependents (leaves first) then the object;
      * ``force=True``      -> remove only the object and report the orphans left;
      * otherwise           -> refuse and list the dependents so the agent decides.

    Returns JSON ``{ok, object, deleted, refused, dependents|orphans_left, ...}``
    plus the I3 recompute log so any newly-Invalid objects surface immediately.
    """
    try:
        code = "\n".join(
            render_template_lines(
                "core/delete_object.py.txt",
                doc_name=repr(doc_name),
                obj_name=repr(obj_name),
                recursive=repr(recursive),
                force=repr(force),
            )
            + render_template_lines("diagnostics/recompute_log.py.txt")
        )
        res = freecad.execute_code(code)
        screenshot = freecad.get_active_screenshot()
        if res["success"]:
            output = res.get("message", "")
            marker = "Output:"
            if marker in output:
                output = output.split(marker, 1)[1].strip()
            # Split the delete JSON from the I3 recompute-log sentinel.
            log_summary = _format_recompute_log(output)
            json_part = output
            idx = output.rfind(_RECOMPUTE_LOG_SENTINEL)
            if idx >= 0:
                json_part = output[:idx].rstrip()
            msg = json_part
            if log_summary:
                msg += "\n" + log_summary
            response = tool_ok(msg)
        else:
            response = tool_fail(
                f"Failed to delete object: {res.get('error', res.get('message', 'unknown error'))}"
            )
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to delete object: {str(e)}")
        return tool_fail(f"Failed to delete object: {str(e)}")


def execute_code_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
    document: str | None = None,
    recompute: str = "none",
    recompute_documents: list[str] | None = None,
    read_only: bool = False,
    restore_active_document: bool = True,
    activate_document: bool = False,
    capture_view: bool = False,
    execution_mode: str = "auto",
    timeout_seconds: float | None = None,
) -> ToolResponse:
    opts = ExecuteOptions(
        document=document,
        recompute=recompute,  # type: ignore[arg-type]
        recompute_documents=recompute_documents,
        read_only=read_only,
        restore_active_document=restore_active_document,
        activate_document=activate_document,
        capture_view=capture_view,
        execution_mode=execution_mode,  # type: ignore[arg-type]
        timeout_seconds=timeout_seconds,
    )
    try:
        res = freecad.execute_code(code, opts)
        screenshot = (
            freecad.get_active_screenshot(view_name=None) if capture_view else None
        )
        if res["success"]:
            return from_execute_result(
                res,
                success_prefix="Code executed successfully",
                fail_prefix="Failed to execute code",
                screenshot=screenshot,
                only_text_feedback=only_text_feedback,
                capture_view=capture_view,
            )
        return from_execute_result(
            res,
            success_prefix="Code executed successfully",
            fail_prefix="Failed to execute code",
            screenshot=screenshot if capture_view else None,
            only_text_feedback=only_text_feedback,
            capture_view=False,
        )
    except Exception as e:
        logger.error(f"Failed to execute code: {str(e)}")
        return tool_fail(f"Failed to execute code: {str(e)}")


def execute_code_async_operation(
    freecad: FreeCADConnection,
    code: str,
) -> ToolResponse:
    try:
        res = freecad.execute_code_async(code)
        if res["success"]:
            return text_response(
                "Code execution started in background.\n"
                "Use get_object to poll a document object for completion "
                "(e.g. check SessionState.Label). "
                "FreeCAD's Report View will show output when done."
            )
        return text_response(f"Failed to start async execution: {res.get('error', 'unknown')}")
    except Exception as e:
        logger.error(f"Failed to start async code execution: {str(e)}")
        return text_response(f"Failed to start async code execution: {str(e)}")


def get_view_operation(
    freecad: FreeCADConnection,
    view_name: str,
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
) -> ToolResponse:
    screenshot = freecad.get_active_screenshot(view_name, width, height, focus_object)
    if screenshot is not None:
        label = f"View: {view_name}" + (f" | focus: {focus_object}" if focus_object else "")
        return tool_ok(label, screenshot=screenshot)
    # P10 / I10 fallback: no viewable image (headless / TechDraw / Spreadsheet).
    # Return a compact geometric state of the focus object (or all objects) as a
    # text-only stand-in so the agent still gets something to reason about.
    try:
        code = "\n".join(render_template_lines(
            "diagnostics/active_state.py.txt",
            focus_object=repr(focus_object),
        ))
        res = freecad.execute_code(
            code,
            ExecuteOptions(recompute="none", read_only=True, capture_view=False),
        )
        if res.get("success"):
            output = res.get("message", "")
            marker = "Output:"
            if marker in output:
                output = output.split(marker, 1)[1].strip()
            note = (
                "Cannot get a viewable screenshot in the current view type "
                "(such as headless, TechDraw or Spreadsheet). Returning a "
                "compact geometric state instead; use capture_state / "
                "geometric_diff for richer text-only diffs, and find_faces / "
                "face_normal for specific subshapes."
            )
            return tool_ok(note + "\n" + output)
    except Exception as e:
        logger.error(f"get_view fallback failed: {e}")
    return tool_fail("Cannot get screenshot in the current view type (such as TechDraw or Spreadsheet)")


def insert_part_from_library_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    relative_path: str,
) -> ToolResponse:
    try:
        res = freecad.insert_part_from_library(relative_path)
        if res["success"]:
            response = tool_ok(f"Part inserted from library: {res['message']}")
        else:
            response = tool_fail(f"Failed to insert part from library: {res['error']}")
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to insert part from library: {str(e)}")
        return tool_fail(f"Failed to insert part from library: {str(e)}")


def get_objects_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
) -> ToolResponse:
    try:
        response = json_response(freecad.get_objects(doc_name))
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to get objects: {str(e)}")
        return tool_fail(f"Failed to get objects: {str(e)}")


def get_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    try:
        response = json_response(freecad.get_object(doc_name, obj_name))
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to get object: {str(e)}")
        return tool_fail(f"Failed to get object: {str(e)}")


def get_parts_list_operation(freecad: FreeCADConnection) -> ToolResponse:
    try:
        parts = freecad.get_parts_list()
    except Exception as e:
        logger.error(f"Failed to get parts list: {str(e)}")
        return text_response(f"Failed to get parts list: {str(e)}")
    if parts:
        return json_response(parts)
    return text_response("No parts found in the parts library. You must add parts_library addon.")


def list_documents_operation(freecad: FreeCADConnection) -> ToolResponse:
    return json_response(freecad.list_documents())


<<<<<<< HEAD
# ---------------------------------------------------------------------------
# Code-generation helpers shared by all sketch / PartDesign / document ops.
# All sketch tools run through execute_code so they work with the original
# addon without any addon update or FreeCAD restart.
# ---------------------------------------------------------------------------

def _run_code(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
    success_msg: str,
    fail_prefix: str,
    *,
    document: str | None = None,
    recompute: str = "target",
    capture_view: bool = True,
    read_only: bool = False,
    execution_mode: str = "auto",
) -> ToolResponse:
    """Execute generated Python code in FreeCAD and return a formatted response."""
    try:
        full_code = code + "\n" + "\n".join(
            render_template_lines("diagnostics/recompute_log.py.txt")
        )
        opts = ExecuteOptions(
            document=document,
            recompute=recompute,  # type: ignore[arg-type]
            recompute_documents=[document] if document and recompute == "target" else None,
            capture_view=capture_view,
            read_only=read_only,
            execution_mode=execution_mode,  # type: ignore[arg-type]
        )
        res = freecad.execute_code(full_code, opts)
        screenshot = freecad.get_active_screenshot() if capture_view else None
        if res["success"]:
            output = res.get("message", "")
            msg = f"{success_msg}\n{output}".strip()
            log_summary = _format_recompute_log(output)
            if log_summary:
                msg += f"\n{log_summary}"
            errors = res.get("recompute_errors", [])
            if errors and not log_summary:
                names = ", ".join(
                    f"{e['name']} (doc={e.get('doc','?')}, state={e['state']})"
                    for e in errors
                )
                msg += f"\nRecompute errors detected: {names}"
            response = tool_ok(msg)
        else:
            response = tool_fail(
                f"{fail_prefix}: {res.get('error', res.get('message', 'unknown error'))}",
                structured=res.get("structured") if isinstance(res.get("structured"), dict) else None,
            )
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"{fail_prefix}: {e}")
        return tool_fail(f"{fail_prefix}: {e}")


def _build_assertion_code(
    feature_name: str,
    sketch_name: str,
    check_direction: bool = True,
) -> list[str]:
    """I2 — render the silent-build assertion snippet for a PartDesign feature.

    Appended to a pad/pocket/loft/sweep op's generated code so a wrong-direction
    or misplaced build (P2/P3) is surfaced as a clear failure instead of being
    silently marked Up-to-date.
    """
    return render_template_lines(
        "diagnostics/build_assertion.py.txt",
        feature_name=repr(feature_name),
        feature_name_repr=repr(feature_name),
        sketch_name=repr(sketch_name),
        check_direction=repr(check_direction),
    )


def _geom_line(code: str, geom: dict) -> str:
    """Return a Python expression that adds one geometry element to _sk."""
    t = geom.get("type", "").lower()
    c = repr(bool(geom.get("construction")))
    if t == "line":
        s, e = geom["start"], geom["end"]
        return render_template_text(
            "core/geom_line.py.txt",
            x1=repr(s["x"]),
            y1=repr(s["y"]),
            x2=repr(e["x"]),
            y2=repr(e["y"]),
            construction=c,
        ).strip()
    if t == "circle":
        ct = geom.get("center", {"x": 0, "y": 0})
        r = geom.get("radius", 1)
        return render_template_text(
            "core/geom_circle.py.txt",
            cx=repr(ct["x"]),
            cy=repr(ct["y"]),
            radius=repr(r),
            construction=c,
        ).strip()
    if t == "arc":
        ct = geom.get("center", {"x": 0, "y": 0})
        r = geom.get("radius", 1)
        sa = geom.get("start_angle", 0)
        ea = geom.get("end_angle", 90)
        return render_template_text(
            "core/geom_arc.py.txt",
            cx=repr(ct["x"]),
            cy=repr(ct["y"]),
            radius=repr(r),
            start_angle=repr(sa),
            end_angle=repr(ea),
            construction=c,
        ).strip()
    if t == "rectangle":
        x1, y1, x2, y2 = geom.get("x1", 0), geom.get("y1", 0), geom.get("x2", 10), geom.get("y2", 10)
        return render_template_text(
            "core/geom_rectangle.py.txt",
            x1=repr(x1),
            y1=repr(y1),
            x2=repr(x2),
            y2=repr(y2),
            construction=c,
        ).strip()
    if t == "point":
        x, y = geom.get("x", 0), geom.get("y", 0)
        return render_template_text(
            "core/geom_point.py.txt",
            x=repr(x),
            y=repr(y),
            construction=c,
        ).strip()
    return f"raise ValueError('Unknown geometry type: {t!r}')"


def _constraint_stmt(args: str) -> str:
    return render_template_text("core/constraint.py.txt", args=args).strip()


def _constraint_line(c: dict) -> str:
    """Return a Python expression that adds one Sketcher constraint to _sk."""
    t = c.get("type", "")
    if t == "Coincident":
        return _constraint_stmt(f"'Coincident',{c['geo1']},{c['pos1']},{c['geo2']},{c['pos2']}")
    if t == "Horizontal":
        return _constraint_stmt(f"'Horizontal',{c['geo']}")
    if t == "Vertical":
        return _constraint_stmt(f"'Vertical',{c['geo']}")
    if t == "Distance":
        if "geo2" in c:
            return _constraint_stmt(f"'Distance',{c['geo1']},{c.get('pos1',0)},{c['geo2']},{c.get('pos2',0)},{c['value']}")
        if "pos" in c:
            return _constraint_stmt(f"'Distance',{c['geo']},{c['pos']},{c['value']}")
        return _constraint_stmt(f"'Distance',{c['geo']},{c['value']}")
    if t == "DistanceX":
        if "pos" in c:
            return _constraint_stmt(f"'DistanceX',{c['geo']},{c['pos']},{c['value']}")
        return _constraint_stmt(f"'DistanceX',{c['geo']},{c['value']}")
    if t == "DistanceY":
        if "pos" in c:
            return _constraint_stmt(f"'DistanceY',{c['geo']},{c['pos']},{c['value']}")
        return _constraint_stmt(f"'DistanceY',{c['geo']},{c['value']}")
    if t == "Radius":
        return _constraint_stmt(f"'Radius',{c['geo']},{c['value']}")
    if t == "Diameter":
        return _constraint_stmt(f"'Diameter',{c['geo']},{c['value']}")
    if t == "Angle":
        if "geo2" in c:
            return _constraint_stmt(f"'Angle',{c['geo1']},{c.get('pos1',0)},{c['geo2']},{c.get('pos2',0)},{c['value']}")
        return _constraint_stmt(f"'Angle',{c['geo']},{c['value']}")
    if t in ("Parallel", "Perpendicular", "Equal", "Tangent"):
        return _constraint_stmt(f"{t!r},{c['geo1']},{c['geo2']}")
    if t == "PointOnObject":
        return _constraint_stmt(f"'PointOnObject',{c['geo1']},{c['pos1']},{c['geo2']}")
    if t == "Symmetric":
        return _constraint_stmt(f"'Symmetric',{c['geo1']},{c['pos1']},{c['geo2']},{c['pos2']},{c['geo3']},{c.get('pos3',0)}")
    if t == "Block":
        return _constraint_stmt(f"'Block',{c['geo']}")
    return f"raise ValueError('Unknown constraint type: {t!r}')"


def _partdesign_bool_property_helper_code() -> list[str]:
    return read_template_lines("core/partdesign_bool_property_helper.py.txt")


def _partdesign_extrusion_helper_code() -> list[str]:
    return read_template_lines("core/partdesign_extrusion_helper.py.txt")


def _partdesign_pattern_helper_code() -> list[str]:
    return read_template_lines("core/partdesign_pattern_helper.py.txt")


# ---------------------------------------------------------------------------
# Sketch operations (all use execute_code — no addon update required)
# ---------------------------------------------------------------------------

def sketch_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    body_name: str | None = None,
    attach_to: str | None = None,
) -> ToolResponse:
    attachment_code = ""
    if attach_to:
        if attach_to in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
            attachment_code = render_template_text(
                "core/attach_origin_plane.py.txt",
                attach_to=repr(attach_to),
            ).strip()
        elif ":" in attach_to:
            obj_n, face = attach_to.split(":", 1)
            attachment_code = render_template_text(
                "core/attach_face.py.txt",
                obj_name=repr(obj_n),
                face_name=repr(face),
            ).strip()
    lines = render_template_lines(
        "core/sketch_create.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        body_name=repr(body_name),
        body_missing=repr(f"Body {body_name!r} not found"),
        sketch_name=repr(sketch_name),
        attachment_code=attachment_code,
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Sketch '{sketch_name}' created", "Failed to create sketch")


def sketch_add_geometry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geometry: list,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_geometry.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        geometry_lines="\n".join(_geom_line("", geom) for geom in geometry),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Geometry added to '{sketch_name}'", "Failed to add geometry")


def sketch_add_constraint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    constraints: list,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_constraint.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        constraint_lines="\n".join(_constraint_line(c) for c in constraints),
        message=repr(f"{len(constraints)} constraint(s) added"),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Constraints added to '{sketch_name}'", "Failed to add constraints")


def pad_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    pad_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/pad_feature.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        body_name=repr(body_name),
        pad_name=repr(pad_name),
        length=repr(length),
        extrusion_helpers="\n".join(_partdesign_extrusion_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
        symmetric=repr(symmetric),
        reversed_dir=repr(reversed_dir),
    ) + _build_assertion_code(pad_name, sketch_name, check_direction=True)
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Pad '{pad_name}' created", "Failed to create pad")


def pocket_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    pocket_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/pocket_feature.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        body_name=repr(body_name),
        pocket_name=repr(pocket_name),
        length=repr(length),
        extrusion_helpers="\n".join(_partdesign_extrusion_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
        symmetric=repr(symmetric),
        reversed_dir=repr(reversed_dir),
    ) + _build_assertion_code(pocket_name, sketch_name, check_direction=True)
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Pocket '{pocket_name}' created", "Failed to create pocket")


def linear_pattern_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    feature_name: str,
    pattern_name: str,
    length: float,
    occurrences: int,
    direction: str = "X_Axis",
    body_name: str | None = None,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/linear_pattern_feature.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        feature_name=repr(feature_name),
        length=repr(length),
        occurrences=repr(occurrences),
        pattern_helpers="\n".join(_partdesign_pattern_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
        body_name=repr(body_name),
        pattern_name=repr(pattern_name),
        direction=repr(direction),
        reversed_dir=repr(reversed_dir),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Linear pattern '{pattern_name}' created", "Failed to create linear pattern")


def polar_pattern_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    feature_name: str,
    pattern_name: str,
    occurrences: int,
    angle: float = 360.0,
    axis: str = "Z_Axis",
    body_name: str | None = None,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/polar_pattern_feature.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        feature_name=repr(feature_name),
        occurrences=repr(occurrences),
        angle=repr(angle),
        pattern_helpers="\n".join(_partdesign_pattern_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
        body_name=repr(body_name),
        pattern_name=repr(pattern_name),
        axis=repr(axis),
        reversed_dir=repr(reversed_dir),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Polar pattern '{pattern_name}' created", "Failed to create polar pattern")


def mirror_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    feature_name: str,
    mirror_name: str,
    plane: str = "YZ_Plane",
    body_name: str | None = None,
) -> ToolResponse:
    lines = render_template_lines(
        "core/mirror_feature.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        feature_name=repr(feature_name),
        pattern_helpers="\n".join(_partdesign_pattern_helper_code()),
        body_name=repr(body_name),
        mirror_name=repr(mirror_name),
        plane=repr(plane),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Mirror feature '{mirror_name}' created", "Failed to create mirror feature")


def create_spur_gear_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    pressure_angle: float = 20.0,
    bore_diameter: float = 0.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    samples_per_flank: int = 8,
    body_name: str | None = None,
    sketch_name: str | None = None,
    tooth_profile: str = "involute",
) -> ToolResponse:
    lines = render_template_lines(
        "core/create_spur_gear.py.txt",
        doc_name=repr(doc_name),
        doc_missing=repr(f"Document {doc_name!r} not found"),
        gear_name=repr(gear_name),
        body_name=repr(body_name),
        sketch_name=repr(sketch_name),
        teeth=repr(teeth),
        module=repr(module),
        width=repr(width),
        pressure_angle=repr(pressure_angle),
        bore_diameter=repr(bore_diameter),
        clearance=repr(clearance),
        backlash=repr(backlash),
        samples_per_flank=repr(samples_per_flank),
        tooth_profile=repr(tooth_profile),
        extrusion_helpers="\n".join(_partdesign_extrusion_helper_code()),
        bool_helpers="\n".join(_partdesign_bool_property_helper_code()),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Spur gear '{gear_name}' sketch and pad created", "Failed to create spur gear")


def recompute_document_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = render_template_text(
        "core/doc_action.py.txt",
        doc_name=repr(doc_name),
        action_line="_d.recompute()",
        message=repr("recomputed"),
    )
    return _run_code(freecad, True, code,
                     f"Document '{doc_name}' recomputed", "Failed to recompute")


def undo_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = render_template_text(
        "core/doc_action.py.txt",
        doc_name=repr(doc_name),
        action_line="_d.undo()",
        message=repr("undo done"),
    )
    return _run_code(freecad, True, code,
                     f"Undo performed on '{doc_name}'", "Failed to undo")


def redo_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = render_template_text(
        "core/doc_action.py.txt",
        doc_name=repr(doc_name),
        action_line="_d.redo()",
        message=repr("redo done"),
    )
    return _run_code(freecad, True, code,
                     f"Redo performed on '{doc_name}'", "Failed to redo")


# ---------------------------------------------------------------------------
# Flat geometry helpers — each calls sketch_add_geometry_operation with one item
# ---------------------------------------------------------------------------

def sketch_add_line_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    x1: float, y1: float, x2: float, y2: float,
    construction: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_line.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        x1=repr(x1),
        y1=repr(y1),
        x2=repr(x2),
        y2=repr(y2),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Line added to '{sketch_name}'", "Failed to add line")


def sketch_add_circle_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    cx: float, cy: float, radius: float,
    construction: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_circle.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        cx=repr(cx),
        cy=repr(cy),
        radius=repr(radius),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Circle added to '{sketch_name}'", "Failed to add circle")


def sketch_add_arc_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    cx: float, cy: float, radius: float,
    start_angle: float, end_angle: float,
    construction: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_arc.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        cx=repr(cx),
        cy=repr(cy),
        radius=repr(radius),
        start_angle=repr(start_angle),
        end_angle=repr(end_angle),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Arc added to '{sketch_name}'", "Failed to add arc")


def sketch_add_rectangle_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    x1: float, y1: float, x2: float, y2: float,
    construction: bool = False,
) -> ToolResponse:
    lines = render_template_lines(
        "core/sketch_add_rectangle.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        x1=repr(x1),
        y1=repr(y1),
        x2=repr(x2),
        y2=repr(y2),
        construction=repr(construction),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Rectangle added to '{sketch_name}'", "Failed to add rectangle")


# ---------------------------------------------------------------------------
# Flat constraint helpers
# ---------------------------------------------------------------------------

def _run_constraint(freecad, only_text_feedback, doc_name, sketch_name, c_dict):
    lines = render_template_lines(
        "core/run_constraint.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
        constraint_line=_constraint_line(c_dict),
        message=repr(c_dict["type"] + " constraint added"),
    )
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"{c_dict['type']} constraint added to '{sketch_name}'",
                     "Failed to add constraint")


def sketch_constrain_coincident_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    geo1: int, pos1: int, geo2: int, pos2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Coincident", "geo1": geo1, "pos1": pos1, "geo2": geo2, "pos2": pos2})


def sketch_constrain_horizontal_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Horizontal", "geo": geo})


def sketch_constrain_vertical_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Vertical", "geo": geo})


def sketch_constrain_distance_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    geo: int, value: float, pos: int | None = None,
) -> ToolResponse:
    c: dict = {"type": "Distance", "geo": geo, "value": value}
    if pos is not None:
        c["pos"] = pos
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name, c)


def sketch_constrain_radius_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo: int, value: float,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Radius", "geo": geo, "value": value})


def sketch_constrain_equal_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Equal", "geo1": geo1, "geo2": geo2})


def sketch_constrain_parallel_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Parallel", "geo1": geo1, "geo2": geo2})


def sketch_constrain_perpendicular_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Perpendicular", "geo1": geo1, "geo2": geo2})


def sketch_constrain_tangent_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Tangent", "geo1": geo1, "geo2": geo2})


# ---------------------------------------------------------------------------
# Introspection / session hygiene
# ---------------------------------------------------------------------------

def get_recompute_log_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = render_template_text("core/get_recompute_log.py.txt", doc_name=repr(doc_name))
    return _run_code(freecad, True, code,
                     f"Recompute log for '{doc_name}'", "Failed to get recompute log")


def get_sketch_diagnostics_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    sketch_name: str,
) -> ToolResponse:
    code = render_template_text(
        "core/get_sketch_diagnostics.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
    )
    return _run_code(freecad, True, code,
                     f"Sketch diagnostics for '{sketch_name}'", "Failed to get sketch diagnostics")


def close_document_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = render_template_text("core/close_document.py.txt", doc_name=repr(doc_name))
    return _run_code(freecad, True, code,
                     f"Document '{doc_name}' closed", "Failed to close document")


def run_fem_analysis_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    analysis_name: str,
    timeout: int = 600,
) -> ToolResponse:
    try:
        res = freecad.run_fem_analysis(doc_name, analysis_name, timeout)
        if res.get("success"):
            def fmt(v, unit):
                return f"{v:.4g} {unit}" if isinstance(v, (int, float)) else f"unavailable ({unit})"
            screenshot = freecad.get_active_screenshot() if not only_text_feedback else None
            response = json_response({
                "summary": (
                    f"FEM analysis '{analysis_name}' solved. "
                    f"max von Mises = {fmt(res.get('max_von_mises_MPa'), 'MPa')}, "
                    f"max displacement = {fmt(res.get('max_displacement_mm'), 'mm')} "
                    f"({res.get('node_count')} nodes)."
                ),
                **res,
            })
            return add_screenshot_if_available(response, screenshot, only_text_feedback)
        return json_response({
            "summary": f"FEM analysis '{analysis_name}' failed: {res.get('error')}",
            **res,
        })
    except Exception as e:
        logger.error(f"Failed to run FEM analysis: {str(e)}")
        return text_response(f"Failed to run FEM analysis: {str(e)}")


def reload_document_operation(
    freecad: FreeCADConnection,
    doc_name: str,
) -> ToolResponse:
    """Close and re-open a document so the GUI picks up external file
    changes (e.g. headless edits via `freecadcmd`).
    """
    try:
        res = freecad.reload_document(doc_name)
        if res.get("success"):
            return text_response(
                f"Document '{res['document_name']}' reloaded from disk."
            )
        return text_response(f"Failed to reload document: {res.get('error')}")
    except Exception as e:
        logger.error(f"Failed to reload document: {str(e)}")
        return text_response(f"Failed to reload document: {str(e)}")
