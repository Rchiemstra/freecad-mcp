"""Shape/subshape diagnostics helpers for typed query handlers."""

from __future__ import annotations

import math
from typing import cast

from .typed_runtime import (
    TypedMutationError,
    load_module,
    module_callable,
    require_object,
)
from .world_shape_actions import read_global_placement, resolve_global_shape


def _vector(x: float, y: float, z: float = 0.0) -> object:
    freecad = load_module("FreeCAD")
    return module_callable(freecad, "Vector")(x, y, z)


def _placement() -> object:
    freecad = load_module("FreeCAD")
    return module_callable(freecad, "Placement")()


def _transform_point(placement: object, point: object) -> object:
    multiply = getattr(placement, "__mul__", None)
    if not callable(multiply):
        raise TypeError("placement does not support point transform")
    return multiply(point)


def _vector_length(value: object) -> float:
    return float(getattr(value, "Length", 0.0))


def _vector_sub(left: object, right: object) -> object:
    subtract = getattr(left, "__sub__", None)
    if not callable(subtract):
        raise TypeError("vector does not support subtraction")
    return subtract(right)


def _subshape_collection_item(shape: object | None, collection: str, index: int) -> object | None:
    if shape is None:
        return None
    items = getattr(shape, collection, None)
    if not isinstance(items, (list, tuple)) or index < 0 or index >= len(items):
        return None
    return cast(object, items[index])


def _vec(value: object) -> dict[str, float] | None:
    if value is None:
        return None
    return {
        "x": round(float(getattr(value, "x", 0.0)), 6),
        "y": round(float(getattr(value, "y", 0.0)), 6),
        "z": round(float(getattr(value, "z", 0.0)), 6),
    }


def _row_number(row: dict[str, object], field: str) -> float:
    value = row.get(field, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


_SUBSHAPE_TYPE_ALIASES = {
    "planar": "Plane", "plane": "Plane",
    "cylinder": "Cylinder", "cylindrical": "Cylinder",
    "cone": "Cone", "sphere": "Sphere", "toroidal": "Toroid", "toroid": "Toroid",
    "line": "Line", "circle": "Circle", "arc": "Circle", "ellipse": "Ellipse",
    "bspline": "BSplineCurve", "bezier": "BezierCurve",
}


def _normalized_subshape_type(value: object) -> str:
    text = str(value or "").strip()
    return _SUBSHAPE_TYPE_ALIASES.get(text.lower(), text[:1].upper() + text[1:])


def _subshape_geometry(sub: object) -> object | None:
    return getattr(sub, "Surface", None) if hasattr(sub, "Surface") else getattr(sub, "Curve", None)


def _subshape_type(sub: object) -> str:
    # type(...).__name__ is the bare geometry class ('Plane', 'Line'); str() renders '<Plane object>'.
    geometry = _subshape_geometry(sub)
    return type(geometry).__name__ if geometry is not None else ""


def _subshape_direction(sub: object) -> object | None:
    """Face: normal at the parametric start; edge: curve axis, else line direction."""
    try:
        if hasattr(sub, "Surface"):
            try:
                u_range = getattr(sub, "ParameterRange")
                return getattr(sub, "normalAt")(u_range[0], u_range[2])
            except Exception:
                axis = getattr(getattr(sub, "Surface"), "Axis", None)
                return _vector(axis.x, axis.y, axis.z) if axis is not None else None
        curve = getattr(sub, "Curve", None)
        axis = getattr(curve, "Axis", None)
        if axis is not None:
            return _vector(axis.x, axis.y, axis.z)
        direction = getattr(curve, "Direction", None)
        return _vector(direction.x, direction.y, direction.z) if direction is not None else None
    except Exception:
        return None


def _subshape_radius(sub: object) -> float | None:
    geometry = _subshape_geometry(sub)
    radius = getattr(geometry, "Radius", None)
    if radius is None and hasattr(sub, "Surface"):
        radius = getattr(geometry, "Radius1", None)
    try:
        return float(radius) if radius is not None else None
    except (TypeError, ValueError):
        return None


def _global_direction(placement: object, direction: object | None) -> object | None:
    if direction is None:
        return None
    try:
        rotated = getattr(placement, "Rotation") * direction
        return rotated.normalize()
    except Exception:
        return None


def find_subshapes(
    document: object,
    object_name: str,
    kind: str,
    *,
    type_filter: str | None = None,
    normal_approx: object = None,
    center_approx: object = None,
    radius: float | None = None,
    tol: float = 1e-3,
    center_tol: float = 1.0,
    limit: int = 10,
) -> dict[str, object]:
    obj = require_object(document, object_name)
    shape = getattr(obj, "Shape", None)
    if shape is None or getattr(shape, "isNull", lambda: True)():
        raise TypedMutationError("SHAPE_NOT_FOUND", f"Object has no shape: {object_name}")
    gp = read_global_placement(obj)
    kind_singular = "Face" if kind == "Faces" else "Edge"

    def to_vec(point: object) -> object | None:
        if point is None:
            return None
        if isinstance(point, dict):
            return _vector(float(point.get("x", 0.0)), float(point.get("y", 0.0)), float(point.get("z", 0.0)))
        if isinstance(point, (list, tuple)):
            return _vector(float(point[0]), float(point[1]), float(point[2]))
        return None

    nv = to_vec(normal_approx)
    if nv is not None and _vector_length(nv) > 0:
        nv = nv.normalize()  # type: ignore[attr-defined]
    cv = to_vec(center_approx)
    type_want = _normalized_subshape_type(type_filter) if type_filter else None
    results: list[dict[str, object]] = []
    for index, sub in enumerate(getattr(shape, kind, []), start=1):
        try:
            center = _transform_point(gp, getattr(sub, "CenterOfMass"))
        except Exception:
            try:
                center = _transform_point(gp, getattr(sub, "CenterOfBoundBox"))
            except Exception:
                continue
        sub_type = _subshape_type(sub)
        if type_want and _normalized_subshape_type(sub_type) != type_want:
            continue
        direction = _global_direction(gp, _subshape_direction(sub))
        if nv is not None and direction is not None:
            try:
                dot = abs(float(direction.dot(nv)))  # type: ignore[attr-defined]
            except Exception:
                dot = 0.0
            if dot < 1.0 - float(tol):
                continue
        if cv is not None and _vector_length(_vector_sub(center, cv)) > center_tol:
            continue
        sub_radius = _subshape_radius(sub)
        if radius is not None and (sub_radius is None or abs(sub_radius - float(radius)) > float(tol)):
            continue
        measure = float(getattr(sub, "Area", 0.0)) if kind == "Faces" else float(getattr(sub, "Length", 0.0))
        results.append(
            {
                "sub": f"{kind_singular}{index}",
                "type": sub_type,
                "global_center": _vec(center),
                "global_normal": _vec(direction),
                "radius": round(sub_radius, 6) if sub_radius is not None else None,
                "area" if kind == "Faces" else "length": round(measure, 6),
            }
        )
    if cv is not None:
        results.sort(
            key=lambda row: _vector_length(_vector_sub(to_vec(row["global_center"]), cv))
        )
    elif kind == "Faces":
        results.sort(key=lambda row: _row_number(row, "area"), reverse=True)
    else:
        results.sort(key=lambda row: _row_number(row, "length"), reverse=True)
    return {
        "ok": True,
        "object": str(getattr(obj, "Name", object_name)),
        "kind": kind_singular,
        "count": len(results),
        "results": results[: int(limit)],
    }


def diagnose_pocket(document: object, pocket_name: str) -> dict[str, object]:
    obj = require_object(document, pocket_name)
    shape = getattr(obj, "Shape", None)
    bbox = None
    if shape is not None and not getattr(shape, "isNull", lambda: True)():
        try:
            box = getattr(shape, "BoundBox", None)
            bbox = {
                "xmin": float(getattr(box, "XMin", 0.0)),
                "ymin": float(getattr(box, "YMin", 0.0)),
                "zmin": float(getattr(box, "ZMin", 0.0)),
                "xmax": float(getattr(box, "XMax", 0.0)),
                "ymax": float(getattr(box, "YMax", 0.0)),
                "zmax": float(getattr(box, "ZMax", 0.0)),
            }
        except Exception:
            bbox = None
    faces = getattr(shape, "Faces", None) if shape is not None else None
    face_count = len(faces) if isinstance(faces, (list, tuple)) else None
    return {
        "ok": True,
        "pocket": pocket_name,
        "type_id": str(getattr(obj, "TypeId", "")),
        "shape_null": shape is None or getattr(shape, "isNull", lambda: True)(),
        "bbox": bbox,
        "face_count": face_count,
    }


def diagnose_helix(document: object, helix_name: str) -> dict[str, object]:
    obj = require_object(document, helix_name)
    return {
        "ok": True,
        "helix": helix_name,
        "type_id": str(getattr(obj, "TypeId", "")),
        "label": str(getattr(obj, "Label", helix_name)),
        "state": list(getattr(obj, "State", [])),
    }


def _bb(box: object) -> dict[str, float] | None:
    if box is None:
        return None
    return {
        "xmin": float(getattr(box, "XMin", 0.0)),
        "ymin": float(getattr(box, "YMin", 0.0)),
        "zmin": float(getattr(box, "ZMin", 0.0)),
        "xmax": float(getattr(box, "XMax", 0.0)),
        "ymax": float(getattr(box, "YMax", 0.0)),
        "zmax": float(getattr(box, "ZMax", 0.0)),
    }


def _parent_of(document: object, obj: object) -> object | None:
    for candidate in getattr(document, "Objects", []) or []:
        group = getattr(candidate, "Group", None) or []
        if obj in group:
            return cast(object, candidate)
        out_list = getattr(candidate, "OutList", None) or []
        if obj in out_list:
            return cast(object, candidate)
    return None


def _subshape_object(obj: object, subshape: str) -> object | None:
    shape = getattr(obj, "Shape", None)
    if shape is None:
        return None
    if subshape.startswith("Face"):
        return _subshape_collection_item(shape, "Faces", int(subshape[4:]) - 1)
    if subshape.startswith("Edge"):
        return _subshape_collection_item(shape, "Edges", int(subshape[4:]) - 1)
    return None


def subshape_pose(document: object, object_name: str, subshape: str) -> dict[str, object]:
    obj = require_object(document, object_name)
    shape = getattr(obj, "Shape", None)
    if shape is None or getattr(shape, "isNull", lambda: True)():
        raise TypedMutationError("SHAPE_NOT_FOUND", f"Object has no shape: {object_name}")
    if not subshape or not (subshape.startswith("Face") or subshape.startswith("Edge")):
        raise TypedMutationError(
            "INVALID_ARGUMENT",
            f'subshape must be like "Face3" or "Edge2": {subshape!r}',
        )
    sub_obj = _subshape_object(obj, subshape)
    if sub_obj is None:
        raise TypedMutationError("SHAPE_NOT_FOUND", f"Subshape not found: {subshape}")
    gp = read_global_placement(obj)
    center = None
    try:
        center = _transform_point(gp, getattr(sub_obj, "CenterOfMass"))
    except Exception:
        try:
            center = _transform_point(gp, getattr(sub_obj, "CenterOfBoundBox"))
        except Exception:
            center = None
    normal = None
    try:
        if hasattr(sub_obj, "Surface"):
            param_range = getattr(sub_obj, "ParameterRange", None)
            if isinstance(param_range, (list, tuple)) and len(param_range) >= 3:
                normal_at = getattr(sub_obj, "normalAt", None)
                if callable(normal_at):
                    n = normal_at(param_range[0], param_range[2])
                else:
                    n = None
            else:
                n = None
        else:
            curve = getattr(sub_obj, "Curve", None)
            axis = getattr(curve, "Axis", None) if curve is not None else None
            if axis is not None:
                n = _vector(getattr(axis, "x", 0.0), getattr(axis, "y", 0.0), getattr(axis, "z", 0.0))
            else:
                direction = getattr(curve, "Direction", None) if curve is not None else None
                n = (
                    _vector(
                        getattr(direction, "x", 0.0),
                        getattr(direction, "y", 0.0),
                        getattr(direction, "z", 0.0),
                    )
                    if direction is not None
                    else None
                )
        if n is not None:
            rotation = getattr(gp, "Rotation", None)
            rot_mul = getattr(rotation, "__mul__", None) if rotation is not None else None
            if callable(rot_mul):
                normal = rot_mul(n)
                normalize = getattr(normal, "normalize", None)
                if callable(normalize):
                    normalize()
    except Exception:
        normal = None
    surface_type = ""
    try:
        if hasattr(sub_obj, "Surface"):
            surface_type = type(getattr(sub_obj, "Surface")).__name__
        elif hasattr(sub_obj, "Curve"):
            surface_type = type(getattr(sub_obj, "Curve")).__name__
    except Exception:
        surface_type = ""
    radius = None
    try:
        if hasattr(sub_obj, "Surface"):
            surface = getattr(sub_obj, "Surface", None)
            radius = float(getattr(surface, "Radius", getattr(surface, "Radius1", 0.0)))
        elif hasattr(sub_obj, "Curve"):
            curve = getattr(sub_obj, "Curve", None)
            radius = float(getattr(curve, "Radius", 0.0))
    except Exception:
        radius = None
    return {
        "ok": True,
        "object": str(getattr(obj, "Name", object_name)),
        "subshape": subshape,
        "type": surface_type,
        "global_center": _vec(center),
        "global_normal": _vec(normal),
        "radius": round(radius, 6) if radius is not None else None,
    }


def face_normal(document: object, object_name: str, face: str) -> dict[str, object]:
    return subshape_pose(document, object_name, face)


def edge_axis(document: object, object_name: str, edge: str) -> dict[str, object]:
    return subshape_pose(document, object_name, edge)


def inspect_geometry(document: object, object_name: str, subshape: str | None = None) -> dict[str, object]:
    obj = require_object(document, object_name)
    chain: list[dict[str, object]] = []
    cursor: object | None = obj
    while cursor is not None:
        placement = getattr(cursor, "Placement", None)
        chain.append(
            {
                "name": str(getattr(cursor, "Name", "")),
                "type": str(getattr(cursor, "TypeId", "")),
                "placement_base": _vec(getattr(placement, "Base", None)) if placement else None,
            }
        )
        cursor = _parent_of(document, cursor)
    try:
        global_pl = read_global_placement(obj)
    except TypedMutationError:
        global_pl = getattr(obj, "Placement", _placement())
    local_bb = None
    global_bb = None
    shape = getattr(obj, "Shape", None)
    if shape is not None and not getattr(shape, "isNull", lambda: True)():
        local_bb = _bb(getattr(shape, "BoundBox", None))
    try:
        world_shape, _meta = resolve_global_shape(obj)
        global_bb = _bb(getattr(world_shape, "BoundBox", None))
    except TypedMutationError:
        global_bb = None
    placement = getattr(obj, "Placement", None)
    result: dict[str, object] = {
        "ok": True,
        "object": object_name,
        "type_id": str(getattr(obj, "TypeId", "")),
        "placement": {
            "base": _vec(getattr(placement, "Base", None)) if placement else None,
            "rotation": str(getattr(placement, "Rotation", "")) if placement else "",
        },
        "global_placement": {
            "base": _vec(getattr(global_pl, "Base", None)) if global_pl else None,
            "rotation": str(getattr(global_pl, "Rotation", "")) if global_pl else "",
        },
        "parent_chain": list(reversed(chain)),
        "local_bbox": local_bb,
        "global_bbox": global_bb,
    }
    if subshape:
        pose = subshape_pose(document, object_name, subshape)
        result["subshape"] = subshape
        result["global_center"] = pose.get("global_center")
        result["global_normal"] = pose.get("global_normal")
    return result


def audit_hardcoded_dimensions(document: object, body_name: str, flag_aliases: bool = True) -> dict[str, object]:
    del flag_aliases
    body = require_object(document, body_name)
    findings: list[dict[str, object]] = []
    for obj in getattr(body, "Group", []) or []:
        type_id = str(getattr(obj, "TypeId", ""))
        if type_id == "Sketcher::SketchObject":
            for index, constraint in enumerate(getattr(obj, "Constraints", []) or []):
                ctype = getattr(constraint, "Type", None)
                if ctype is None:
                    continue
                name = str(ctype)
                if name not in ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle"):
                    continue
                expr = None
                try:
                    expr = obj.getExpression(f"Constraints[{index}]")
                except Exception:
                    pass
                if not expr:
                    findings.append({"object": obj.Name, "kind": "sketch_constraint", "index": index, "type": name})
        if type_id in ("PartDesign::Pad", "PartDesign::Pocket"):
            for prop in ("Length", "Length2"):
                if prop not in getattr(obj, "PropertiesList", []):
                    continue
                expr = None
                try:
                    expr = obj.getExpression(prop)
                except Exception:
                    pass
                if not expr:
                    value = getattr(obj, prop, None)
                    findings.append(
                        {
                            "object": obj.Name,
                            "kind": "extrusion_length",
                            "property": prop,
                            "value": float(value) if value is not None else None,
                        }
                    )
    return {"ok": len(findings) == 0, "body": body_name, "findings": findings, "count": len(findings)}


def get_dependency_graph(document: object, root: str) -> dict[str, object]:
    root_obj = require_object(document, root)
    edges: list[dict[str, object]] = []
    seen: set[str] = set()
    link_props = ("Support", "AttachmentSupport", "Profile", "Base", "Tool", "Source", "Original", "Originals", "References")

    def walk(obj: object, stage: int) -> None:
        name = str(getattr(obj, "Name", ""))
        if name in seen:
            return
        seen.add(name)
        for prop in link_props:
            if prop not in getattr(obj, "PropertiesList", []):
                continue
            try:
                value = getattr(obj, prop)
            except Exception:
                continue
            targets: list[tuple[object, list[str]]] = []
            if isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, tuple) and item:
                        targets.append((item[0], list(item[1:]) if len(item) > 1 else []))
                    elif hasattr(item, "Name"):
                        targets.append((item, []))
            elif hasattr(value, "Name"):
                targets.append((value, []))
            for target, subs in targets:
                if target is None or not hasattr(target, "Name"):
                    continue
                edges.append(
                    {
                        "from": name,
                        "to": str(getattr(target, "Name", "")),
                        "property": prop,
                        "subelements": subs,
                        "stage": stage,
                    }
                )
                if str(getattr(target, "Name", "")) not in seen:
                    walk(target, stage + 1)

    history = [str(getattr(item, "Name", "")) for item in getattr(root_obj, "Group", []) or []]
    walk(root_obj, 0)
    names = {edge["from"] for edge in edges} | {edge["to"] for edge in edges}
    return {
        "ok": True,
        "root": root,
        "history_order": history,
        "edges": edges,
        "cycle_detected": False,
        "node_count": len(names),
    }


def match_subshape(
    document: object,
    source_object: str,
    source_subshape: str,
    target_object: str,
    limit: int = 10,
    tolerance: float = 1.0,
) -> dict[str, object]:
    src = require_object(document, source_object)
    tgt = require_object(document, target_object)
    src_shape = _subshape_object(src, source_subshape)
    if src_shape is None:
        raise TypedMutationError("SHAPE_NOT_FOUND", "Source subshape not found")
    src_area = float(getattr(src_shape, "Area", 0.0)) if hasattr(src_shape, "Area") else None
    src_center = _vec(getattr(src_shape, "CenterOfMass", None))
    src_normal = None
    try:
        if source_subshape.startswith("Face"):
            index = int(source_subshape[4:]) - 1
            face = _subshape_collection_item(getattr(src, "Shape", None), "Faces", index)
            if face is not None:
                param_range = getattr(face, "ParameterRange", None)
                normal_at = getattr(face, "normalAt", None)
                global_pl = read_global_placement(src)
                rotation = getattr(global_pl, "Rotation", None)
                mult_vec = getattr(rotation, "multVec", None) if rotation is not None else None
                if (
                    isinstance(param_range, (list, tuple))
                    and len(param_range) >= 4
                    and callable(normal_at)
                    and callable(mult_vec)
                ):
                    normal = mult_vec(
                        normal_at((param_range[0] + param_range[1]) * 0.5, (param_range[2] + param_range[3]) * 0.5)
                    ).normalize()
                    src_normal = _vec(normal)
    except Exception:
        src_normal = None
    kind = "Faces" if source_subshape.startswith("Face") else "Edges"
    candidates: list[dict[str, object]] = []
    target_shape = getattr(tgt, "Shape", None)
    for index, sub in enumerate(getattr(target_shape, kind, []), start=1):
        name = kind[:-1] + str(index)
        score = 0.0
        area = float(getattr(sub, "Area", 0.0)) if hasattr(sub, "Area") else None
        if src_area and area:
            score += max(0.0, 1.0 - abs(src_area - area) / max(src_area, area))
        center = _vec(getattr(sub, "CenterOfMass", None))
        if center and src_center:
            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(center.values(), src_center.values())))
            score += max(0.0, 1.0 - dist / max(tolerance, 1e-9))
        candidates.append({"subshape": name, "score": round(score, 6), "area": area, "global_center": center})
    candidates.sort(key=lambda row: _row_number(row, "score"), reverse=True)
    return {
        "ok": True,
        "source": f"{source_object}:{source_subshape}",
        "target": target_object,
        "matches": candidates[: int(limit)],
    }


def placement_audit(document: object) -> dict[str, object]:
    bodies: list[dict[str, object]] = []
    for obj in getattr(document, "Objects", []) or []:
        type_id = str(getattr(obj, "TypeId", ""))
        if "Body" not in type_id and "Part" not in type_id:
            continue
        placement = getattr(obj, "Placement", None)
        bodies.append(
            {
                "name": str(getattr(obj, "Name", "")),
                "type": type_id,
                "placement_base": _vec(getattr(placement, "Base", None)) if placement else None,
            }
        )
    return {"ok": True, "doc": str(getattr(document, "Name", "")), "bodies": bodies}



__all__ = [
    "find_subshapes",
    "diagnose_pocket",
    "diagnose_helix",
    "placement_audit",
    "subshape_pose",
    "face_normal",
    "edge_axis",
    "inspect_geometry",
    "audit_hardcoded_dimensions",
    "get_dependency_graph",
    "match_subshape",
]
