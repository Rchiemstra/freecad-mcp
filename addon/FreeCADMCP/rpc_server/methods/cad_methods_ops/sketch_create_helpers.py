"""Sketch creation attachment helpers (Phase 4 slice 4F)."""

from __future__ import annotations

from .sketch_attach_helpers import find_origin_plane


def create_sketch_object(doc, sketch_name: str, body_name: str | None):
    if body_name:
        body = doc.getObject(body_name)
        if not body:
            return None, f"Body '{body_name}' not found."
        return body.newObject("Sketcher::SketchObject", sketch_name), None
    return doc.addObject("Sketcher::SketchObject", sketch_name), None


def apply_create_attach_to(sketch, doc, attach_to: str) -> str | None:
    if attach_to in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
        return _attach_origin_plane_on_create(sketch, doc, attach_to)
    if ":" in attach_to:
        obj_name, face = attach_to.split(":", 1)
        ref_obj = doc.getObject(obj_name)
        if not ref_obj:
            return f"Object '{obj_name}' not found for attach_to."
        sketch.AttachmentSupport = [(ref_obj, face)]
        sketch.MapMode = "FlatFace"
        return None
    return f"Unsupported attach_to: {attach_to}"


def _attach_origin_plane_on_create(sketch, doc, plane_name: str) -> str | None:
    plane_obj = find_origin_plane(doc, sketch, plane_name)
    if plane_obj is None:
        # Never emulate an attachment with Placement.  A deactivated sketch can
        # silently lose that rotation during later feature recomputes (P3).
        return f"Origin plane not found: {plane_name}"
    sketch.AttachmentSupport = [(plane_obj, "")]
    sketch.MapMode = "FlatFace"
    return None
