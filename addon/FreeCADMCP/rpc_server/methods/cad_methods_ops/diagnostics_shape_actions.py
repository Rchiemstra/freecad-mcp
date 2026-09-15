# mypy: ignore-errors
"""Shape/subshape diagnostics helpers for typed query handlers."""

from __future__ import annotations

import math

from .typed_runtime import TypedMutationError, require_object


def _vec(value: object) -> dict[str, float] | None:
    if value is None:
        return None
    return {
        "x": round(float(getattr(value, "x", 0.0)), 6),
        "y": round(float(getattr(value, "y", 0.0)), 6),
        "z": round(float(getattr(value, "z", 0.0)), 6),
    }


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
    import FreeCAD  # noqa: PLC0415

    obj = require_object(document, object_name)
    shape = getattr(obj, "Shape", None)
    if shape is None or getattr(shape, "isNull", lambda: True)():
        raise TypedMutationError(f"Object has no shape: {object_name}")
    gp = obj.getGlobalPlacement()
    kind_singular = "Face" if kind == "Faces" else "Edge"

    def to_vec(point: object) -> object | None:
        if point is None:
            return None
        if isinstance(point, dict):
            return FreeCAD.Vector(float(point.get("x", 0.0)), float(point.get("y", 0.0)), float(point.get("z", 0.0)))
        if isinstance(point, (list, tuple)):
            return FreeCAD.Vector(float(point[0]), float(point[1]), float(point[2]))
        return None

    nv = to_vec(normal_approx)
    cv = to_vec(center_approx)
    results: list[dict[str, object]] = []
    for index, sub in enumerate(getattr(shape, kind, []), start=1):
        try:
            center = gp * sub.CenterOfMass
        except Exception:
            try:
                center = gp * sub.CenterOfBoundBox
            except Exception:
                continue
        if cv is not None and float((center - cv).Length) > center_tol:
            continue
        measure = float(sub.Area) if kind == "Faces" else float(sub.Length)
        results.append(
            {
                "sub": f"{kind_singular}{index}",
                "global_center": _vec(center),
                "area" if kind == "Faces" else "length": round(measure, 6),
            }
        )
    if cv is not None:
        results.sort(key=lambda row: float((to_vec(row["global_center"]) - cv).Length))  # type: ignore[operator]
    elif kind == "Faces":
        results.sort(key=lambda row: row.get("area", 0.0), reverse=True)  # type: ignore[arg-type,return-value]
    else:
        results.sort(key=lambda row: row.get("length", 0.0), reverse=True)  # type: ignore[arg-type,return-value]
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
            box = shape.BoundBox
            bbox = {
                "xmin": float(box.XMin),
                "ymin": float(box.YMin),
                "zmin": float(box.ZMin),
                "xmax": float(box.XMax),
                "ymax": float(box.YMax),
                "zmax": float(box.ZMax),
            }
        except Exception:
            bbox = None
    return {
        "ok": True,
        "pocket": pocket_name,
        "type_id": str(getattr(obj, "TypeId", "")),
        "shape_null": shape is None or getattr(shape, "isNull", lambda: True)(),
        "bbox": bbox,
        "face_count": len(shape.Faces) if shape is not None and hasattr(shape, "Faces") else None,
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


def _global_placement(obj: object) -> object:
    getter = getattr(obj, "getGlobalPlacement", None)
    if callable(getter):
        return getter()
    return getattr(obj, "Placement", None)


def _parent_of(document: object, obj: object) -> object | None:
    for candidate in getattr(document, "Objects", []) or []:
        group = getattr(candidate, "Group", None) or []
        if obj in group:
            return candidate
        out_list = getattr(candidate, "OutList", None) or []
        if obj in out_list:
            return candidate
    return None


def _subshape_object(obj: object, subshape: str) -> object | None:
    shape = getattr(obj, "Shape", None)
    if shape is None:
        return None
    if subshape.startswith("Face"):
        index = int(subshape[4:]) - 1
        return shape.Faces[index]
    if subshape.startswith("Edge"):
        index = int(subshape[4:]) - 1
        return shape.Edges[index]
    return None


def subshape_pose(document: object, object_name: str, subshape: str) -> dict[str, object]:
    import FreeCAD  # noqa: PLC0415

    obj = require_object(document, object_name)
    shape = getattr(obj, "Shape", None)
    if shape is None or getattr(shape, "isNull", lambda: True)():
        raise TypedMutationError(f"Object has no shape: {object_name}")
    if not subshape or not (subshape.startswith("Face") or subshape.startswith("Edge")):
        raise TypedMutationError(f'subshape must be like "Face3" or "Edge2": {subshape!r}')
    sub_obj = _subshape_object(obj, subshape)
    if sub_obj is None:
        raise TypedMutationError(f"Subshape not found: {subshape}")
    gp = obj.getGlobalPlacement()
    center = None
    try:
        center = gp * sub_obj.CenterOfMass
    except Exception:
        try:
            center = gp * sub_obj.CenterOfBoundBox
        except Exception:
            center = None
    normal = None
    try:
        if hasattr(sub_obj, "Surface"):
            u_param = sub_obj.ParameterRange[0]
            v_param = sub_obj.ParameterRange[2]
            n = sub_obj.normalAt(u_param, v_param)
        else:
            axis = getattr(sub_obj.Curve, "Axis", None)
            if axis is not None:
                n = FreeCAD.Vector(axis.x, axis.y, axis.z)
            else:
                direction = getattr(sub_obj.Curve, "Direction", None)
                n = FreeCAD.Vector(direction.x, direction.y, direction.z) if direction is not None else None
        if n is not None:
            normal = gp.Rotation * n
            normal.normalize()
    except Exception:
        normal = None
    surface_type = ""
    try:
        if hasattr(sub_obj, "Surface"):
            surface_type = type(sub_obj.Surface).__name__
        elif hasattr(sub_obj, "Curve"):
            surface_type = type(sub_obj.Curve).__name__
    except Exception:
        surface_type = ""
    radius = None
    try:
        if hasattr(sub_obj, "Surface"):
            radius = float(getattr(sub_obj.Surface, "Radius", getattr(sub_obj.Surface, "Radius1", 0.0)))
        elif hasattr(sub_obj, "Curve"):
            radius = float(getattr(sub_obj.Curve, "Radius", 0.0))
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
    import FreeCAD  # noqa: PLC0415

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
        global_pl = _global_placement(obj)
    except Exception:
        global_pl = getattr(obj, "Placement", FreeCAD.Placement())
    local_bb = None
    global_bb = None
    shape = getattr(obj, "Shape", None)
    if shape is not None and not getattr(shape, "isNull", lambda: True)():
        local_bb = _bb(shape.BoundBox)
        try:
            copy = shape.copy()
            copy.Placement = global_pl
            global_bb = _bb(copy.BoundBox)
        except Exception:
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
        raise TypedMutationError("Source subshape not found")
    src_area = float(src_shape.Area) if hasattr(src_shape, "Area") else None
    src_center = _vec(src_shape.CenterOfMass)
    src_normal = None
    try:
        if source_subshape.startswith("Face"):
            index = int(source_subshape[4:]) - 1
            face = src.Shape.Faces[index]
            u0, u1, v0, v1 = face.ParameterRange
            normal = _global_placement(src).Rotation.multVec(face.normalAt((u0 + u1) * 0.5, (v0 + v1) * 0.5)).normalize()
            src_normal = _vec(normal)
    except Exception:
        src_normal = None
    kind = "Faces" if source_subshape.startswith("Face") else "Edges"
    candidates: list[dict[str, object]] = []
    for index, sub in enumerate(getattr(tgt.Shape, kind, []), start=1):
        name = kind[:-1] + str(index)
        score = 0.0
        area = float(sub.Area) if hasattr(sub, "Area") else None
        if src_area and area:
            score += max(0.0, 1.0 - abs(src_area - area) / max(src_area, area))
        center = _vec(sub.CenterOfMass)
        if center and src_center:
            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(center.values(), src_center.values())))
            score += max(0.0, 1.0 - dist / max(tolerance, 1e-9))
        candidates.append({"subshape": name, "score": round(score, 6), "area": area, "global_center": center})
    candidates.sort(key=lambda row: row["score"], reverse=True)  # type: ignore[arg-type,return-value]
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
