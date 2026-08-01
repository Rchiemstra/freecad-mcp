"""Sketch attach support resolution (Phase 4 slice 4F)."""

from __future__ import annotations


def find_origin_plane(doc, sketch, plane_name: str):
    body = None
    for obj in doc.Objects:
        if getattr(obj, "TypeId", "") == "PartDesign::Body" and sketch in getattr(
            obj, "Group", []
        ):
            body = obj
            break
    origins = []
    if body is not None and getattr(body, "Origin", None) is not None:
        origins.append(body.Origin)
    for origin in doc.Objects:
        if getattr(origin, "TypeId", "") == "App::Origin" and origin not in origins:
            origins.append(origin)
    for origin in origins:
        for feat in getattr(origin, "OriginFeatures", []) or []:
            if getattr(feat, "Label", "") == plane_name or getattr(feat, "Name", "") == plane_name:
                return feat
        if hasattr(origin, plane_name):
            return getattr(origin, plane_name)
    return None


def attach_origin_plane(sketch, doc, plane_name: str) -> tuple[dict | None, str | None]:
    plane = find_origin_plane(doc, sketch, plane_name)
    if plane is None:
        return None, f"Origin plane not found: {plane_name}"
    sketch.AttachmentSupport = [(plane, "")]
    sketch.MapMode = "FlatFace"
    return {
        "object": plane.Name,
        "subname": "",
        "kind": "origin_plane",
        "plane": plane_name,
    }, None


def attach_face_reference(sketch, doc, support: str) -> tuple[dict | None, str | None]:
    obj_name, sub = support.split(":", 1)
    ref = doc.getObject(obj_name)
    if not ref:
        return None, f"Support object not found: {obj_name}"
    sketch.AttachmentSupport = [(ref, sub)]
    sketch.MapMode = "FlatFace"
    return {"object": ref.Name, "subname": sub, "kind": "face_ref"}, None


def attach_dict_reference(sketch, doc, support: dict) -> tuple[dict | None, str | None]:
    obj_name = support.get("object") or support.get("object_name")
    sub = support.get("subname") or support.get("sub") or ""
    ref = doc.getObject(obj_name)
    if not ref:
        return None, f"Support object not found: {obj_name}"
    sketch.AttachmentSupport = [(ref, sub)]
    sketch.MapMode = "FlatFace"
    return {"object": ref.Name, "subname": sub, "kind": "dict_ref"}, None


def resolve_sketch_support(
    sketch, doc, support
) -> tuple[dict | None, str | None]:
    if isinstance(support, str):
        if support in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
            return attach_origin_plane(sketch, doc, support)
        if ":" in support:
            return attach_face_reference(sketch, doc, support)
        return None, f"Unsupported support string: {support}"
    if isinstance(support, dict):
        return attach_dict_reference(sketch, doc, support)
    return None, "support must be str or dict"
