"""Sketch creation attachment helpers (Phase 4 slice 4F)."""

from __future__ import annotations


def create_sketch_object(doc, sketch_name: str, body_name: str | None):
    if body_name:
        body = doc.getObject(body_name)
        if not body:
            return None, f"Body '{body_name}' not found."
        return body.newObject("Sketcher::SketchObject", sketch_name), None
    return doc.addObject("Sketcher::SketchObject", sketch_name), None


def apply_create_attach_to(sketch, doc, attach_to: str, *, freecad) -> str | None:
    if attach_to in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
        return _attach_origin_plane_on_create(sketch, doc, attach_to, freecad=freecad)
    if ":" in attach_to:
        obj_name, face = attach_to.split(":", 1)
        ref_obj = doc.getObject(obj_name)
        if not ref_obj:
            return f"Object '{obj_name}' not found for attach_to."
        sketch.AttachmentSupport = [(ref_obj, face)]
        sketch.MapMode = "FlatFace"
    return None


def _attach_origin_plane_on_create(
    sketch, doc, plane_name: str, *, freecad
) -> str | None:
    plane_obj = None
    for obj in doc.Objects:
        if obj.TypeId == "App::Origin":
            for feat in getattr(obj, "OriginFeatures", []):
                if feat.Label == plane_name:
                    plane_obj = feat
                    break
        if plane_obj:
            break
    if plane_obj:
        sketch.AttachmentSupport = [(plane_obj, "")]
        sketch.MapMode = "FlatFace"
        return None
    if plane_name == "XZ_Plane":
        sketch.Placement = freecad.Placement(
            freecad.Vector(0, 0, 0),
            freecad.Rotation(freecad.Vector(1, 0, 0), 90),
        )
    elif plane_name == "YZ_Plane":
        sketch.Placement = freecad.Placement(
            freecad.Vector(0, 0, 0),
            freecad.Rotation(freecad.Vector(0, 1, 0), -90),
        )
    return None
