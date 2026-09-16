"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from __future__ import annotations


class _DeferredFeatureCommit:
    """Validate a feature after native recompute, then publish presentation."""

    __slots__ = (
        "_body",
        "_diagnostics",
        "_doc",
        "_feature",
        "_message",
        "_operation",
        "_print_message",
        "_sketch",
        "_source_feature",
        "_volume_before",
    )

    def __init__(
        self,
        doc,
        body,
        sketch,
        feature,
        diagnostics,
        message,
        print_message,
        *,
        operation,
        source_feature,
        volume_before,
    ) -> None:
        self._doc = doc
        self._body = body
        self._sketch = sketch
        self._feature = feature
        self._diagnostics = diagnostics
        self._message = message
        self._print_message = print_message
        self._operation = operation
        self._source_feature = source_feature
        self._volume_before = volume_before

    def validate_after_recompute(self):
        try:
            return _build_feature_result(
                self._doc,
                self._body,
                self._sketch,
                self._feature,
                self._diagnostics,
                operation=self._operation,
                source_feature=self._source_feature,
                volume_before=self._volume_before,
            )
        except Exception as exc:
            return {
                "success": False,
                "ok": False,
                "error": str(exc),
                "diagnostics": self._diagnostics,
            }

    def apply_after_commit(self) -> None:
        self._sketch.Visibility = False
        self._print_message(self._message)


def _profile_diagnostics(sketch):
    diagnostics = {
        "conflicting": list(getattr(sketch, "ConflictingConstraints", []) or []),
        "redundant": list(getattr(sketch, "RedundantConstraints", []) or []),
        "malformed": list(getattr(sketch, "MalformedConstraints", []) or []),
        "solver_message": getattr(sketch, "SolverMessage", None),
        "is_closed": None,
    }
    try:
        shape = sketch.Shape
        if shape and not shape.isNull():
            diagnostics["is_closed"] = bool(shape.isClosed())
    except Exception:
        pass
    return diagnostics


def _resolve_feature_body(doc, sketch, body_name, strict, feature_kind, feature_name):
    if strict and not body_name:
        return None, (
            f"strict PartDesign mode requires an explicit body_name for "
            f"{feature_kind} '{feature_name}'"
        )
    if body_name and not doc.getObject(body_name):
        return None, f"Body '{body_name}' not found."
    body = doc.getObject(body_name) if body_name else None
    if not body:
        for obj in doc.Objects:
            if obj.TypeId == "PartDesign::Body" and sketch in obj.Group:
                body = obj
                break
    if body is None or body.TypeId != "PartDesign::Body":
        return None, (
            f"No PartDesign::Body found to own {feature_kind} '{feature_name}'. Sketch "
            f"'{sketch.Name}' is not inside a Body; create a Body first."
        )
    return body, None


def _solid_volume(candidate):
    shape = getattr(candidate, "Shape", None)
    if not shape or shape.isNull() or not getattr(shape, "Solids", []):
        return None
    return float(shape.Volume)


def _material_baseline(body, sketch):
    for candidate in reversed(list(getattr(body, "Group", []) or [])):
        if candidate is sketch:
            continue
        volume = _solid_volume(candidate)
        if volume is not None:
            return getattr(candidate, "Name", None), volume
    return None, 0.0


def _build_feature_result(
    doc,
    body,
    sketch,
    feature,
    diagnostics,
    *,
    operation,
    source_feature,
    volume_before,
):
    shape = getattr(feature, "Shape", None)
    has_shape = bool(shape) and not shape.isNull()
    state = list(getattr(feature, "State", []) or [])
    if feature not in body.Group:
        return {
            "success": False,
            "ok": False,
            "error": f"{feature.Name} is not a Body member",
        }
    if getattr(body, "Tip", None) is not feature:
        return {
            "success": False,
            "ok": False,
            "error": f"Body '{body.Name}' Tip did not advance",
        }
    if any(item in ("Invalid", "Error", "Erroneous") for item in state):
        return {
            "success": False,
            "ok": False,
            "error": f"{feature.Name} is in state {state}",
        }
    if not has_shape or not getattr(shape, "Solids", []):
        return {
            "success": False,
            "ok": False,
            "error": f"{feature.Name} did not produce a solid",
        }
    volume_after = float(shape.Volume)
    material_delta = volume_after - volume_before
    delta_tolerance = max(1.0e-9, max(abs(volume_before), abs(volume_after)) * 1.0e-12)
    material_fields = {
        "source_feature": source_feature,
        "volume_before_mm3": volume_before,
        "volume_after_mm3": volume_after,
        "material_delta_mm3": material_delta,
        "material_delta_tolerance_mm3": delta_tolerance,
    }
    if abs(material_delta) <= delta_tolerance:
        return {
            "success": False,
            "ok": False,
            "error_code": "ZERO_MATERIAL_DELTA",
            "error": f"{feature.Name} did not change the body's material volume",
            **material_fields,
        }
    expected_direction = 1.0 if operation == "additive" else -1.0
    if material_delta * expected_direction <= 0.0:
        return {
            "success": False,
            "ok": False,
            "error_code": "MATERIAL_DELTA_DIRECTION_MISMATCH",
            "error": (
                f"{feature.Name} changed material in the wrong direction for "
                f"an {operation} feature"
            ),
            **material_fields,
        }
    bbox = shape.BoundBox
    return {
        "success": True,
        "ok": True,
        "document": doc.Name,
        "body": body.Name,
        "sketch": sketch.Name,
        "feature": feature.Name,
        "tip": getattr(body.Tip, "Name", None),
        "solid_count": len(shape.Solids),
        "state": state,
        "bbox": [bbox.XMin, bbox.YMin, bbox.ZMin, bbox.XMax, bbox.YMax, bbox.ZMax],
        "diagnostics": diagnostics,
        **material_fields,
    }


def pad_feature_gui(
    doc_name,
    sketch_name,
    pad_name,
    length,
    body_name,
    symmetric,
    reversed_dir,
    strict=False,
    *,
    freecad,
    set_extrusion_symmetric,
    set_feature_bool,
):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sketch = doc.getObject(sketch_name)
        if not sketch:
            return f"Sketch '{sketch_name}' not found."

        diagnostics = _profile_diagnostics(sketch)
        if (
            diagnostics["conflicting"]
            or diagnostics["malformed"]
            or diagnostics["is_closed"] is not True
        ):
            return {
                "success": False,
                "ok": False,
                "error": "Sketch profile is not pad-ready",
                "diagnostics": diagnostics,
            }
        body, error = _resolve_feature_body(
            doc, sketch, body_name, strict, "pad", pad_name
        )
        if error:
            return {
                "success": False,
                "ok": False,
                "error": error,
                "diagnostics": diagnostics,
            }
        source_feature, volume_before = _material_baseline(body, sketch)
        pad = body.newObject("PartDesign::Pad", pad_name)

        pad.Profile = (sketch, [""])
        pad.Length = length
        set_extrusion_symmetric(pad, symmetric)
        set_feature_bool(pad, ("Reversed",), reversed_dir)
        body.Tip = pad
        return _DeferredFeatureCommit(
            doc,
            body,
            sketch,
            pad,
            diagnostics,
            f"Pad '{pad_name}' created in '{doc_name}'.\n",
            freecad.Console.PrintMessage,
            operation="additive",
            source_feature=source_feature,
            volume_before=volume_before,
        )
    except Exception as e:
        return str(e)


def pocket_feature_gui(
    doc_name,
    sketch_name,
    pocket_name,
    length,
    body_name,
    symmetric,
    reversed_dir,
    strict=False,
    *,
    freecad,
    set_extrusion_symmetric,
    set_feature_bool,
):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sketch = doc.getObject(sketch_name)
        if not sketch:
            return f"Sketch '{sketch_name}' not found."

        diagnostics = _profile_diagnostics(sketch)
        if (
            diagnostics["conflicting"]
            or diagnostics["malformed"]
            or diagnostics["is_closed"] is not True
        ):
            return {
                "success": False,
                "ok": False,
                "error": "Sketch profile is not pocket-ready",
                "diagnostics": diagnostics,
            }
        body, error = _resolve_feature_body(
            doc, sketch, body_name, strict, "pocket", pocket_name
        )
        if error:
            return {
                "success": False,
                "ok": False,
                "error": error,
                "diagnostics": diagnostics,
            }
        source_feature, volume_before = _material_baseline(body, sketch)
        pocket = body.newObject("PartDesign::Pocket", pocket_name)

        pocket.Profile = (sketch, [""])
        pocket.Length = length
        set_extrusion_symmetric(pocket, symmetric)
        set_feature_bool(pocket, ("Reversed",), reversed_dir)
        body.Tip = pocket
        return _DeferredFeatureCommit(
            doc,
            body,
            sketch,
            pocket,
            diagnostics,
            f"Pocket '{pocket_name}' created in '{doc_name}'.\n",
            freecad.Console.PrintMessage,
            operation="subtractive",
            source_feature=source_feature,
            volume_before=volume_before,
        )
    except Exception as e:
        return str(e)


def body_create_gui(doc_name, body_name, *, freecad, recompute: bool = True):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        if doc.getObject(body_name):
            return f"Object already exists: {body_name}"
        body = doc.addObject("PartDesign::Body", body_name)
        if recompute:
            doc.recompute()
        return {"success": True, "body": body.Name}
    except Exception as e:
        return str(e)


def body_set_tip_gui(
    doc_name,
    body_name,
    feature_name,
    *,
    freecad,
    recompute: bool = True,
):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        body = doc.getObject(body_name)
        if not body:
            return f"Body '{body_name}' not found."
        feat = doc.getObject(feature_name)
        if not feat:
            return f"Feature '{feature_name}' not found."
        body.Tip = feat
        if recompute:
            doc.recompute()
        tip = getattr(body, "Tip", None)
        return {
            "success": True,
            "body": body.Name,
            "tip": getattr(tip, "Name", None),
        }
    except Exception as e:
        return str(e)
