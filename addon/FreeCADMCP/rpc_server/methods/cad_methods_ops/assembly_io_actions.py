# mypy: ignore-errors
"""Query helpers for assembly and sketch projection reads."""

from __future__ import annotations

from .typed_runtime import TypedMutationError, require_object


def _children(obj: object) -> list[object]:
    return list(getattr(obj, "Group", None) or [])


def _field(obj: object, name: str) -> object:
    if name == "Name":
        return getattr(obj, "Name", "")
    if name == "Label":
        return getattr(obj, "Label", getattr(obj, "Name", ""))
    if name == "TypeId":
        return getattr(obj, "TypeId", "")
    if name == "Visibility":
        try:
            view = getattr(obj, "ViewObject", None)
            return bool(view.Visibility) if view is not None else None
        except Exception:
            return None
    if name == "State":
        return list(getattr(obj, "State", []) or [])
    return str(getattr(obj, name, ""))


def get_document_tree(
    document: object,
    *,
    root_filter: str,
    max_depth: int,
    include: list[str] | None,
    include_properties: list[str] | None,
    selected_nodes: list[str] | None,
) -> dict[str, object]:
    include_fields = include or ["Name", "Label", "TypeId", "Visibility", "State"]
    include_properties = include_properties or []
    selected = set(selected_nodes or [])

    def node(obj: object, depth: int, seen: set[str]) -> dict[str, object]:
        data: dict[str, object] = {key: _field(obj, key) for key in include_fields}
        name = str(getattr(obj, "Name", ""))
        label = str(getattr(obj, "Label", name))
        if include_properties and (not selected or name in selected or label in selected):
            props: dict[str, object] = {}
            for prop in include_properties:
                try:
                    props[prop] = str(getattr(obj, prop))
                except Exception as exc:
                    props[prop] = f"<error: {exc}>"
            data["Properties"] = props
        if depth < max_depth and name not in seen:
            seen.add(name)
            data["children"] = [node(child, depth + 1, seen) for child in _children(obj)]
        return data

    contained: set[str] = set()
    objects = list(getattr(document, "Objects", []) or [])
    for obj in objects:
        for child in _children(obj):
            contained.add(str(getattr(child, "Name", "")))
    roots = [obj for obj in objects if str(getattr(obj, "Name", "")) not in contained]
    if root_filter:
        roots = [
            obj
            for obj in objects
            if root_filter in str(getattr(obj, "Name", ""))
            or root_filter in str(getattr(obj, "Label", ""))
        ]
    return {
        "doc_name": str(getattr(document, "Name", "")),
        "root_filter": root_filter,
        "max_depth": max_depth,
        "roots": [node(obj, 0, set()) for obj in roots],
    }


def _vec(value: object) -> dict[str, float] | None:
    if value is None:
        return None
    return {
        "x": round(float(getattr(value, "x", 0.0)), 6),
        "y": round(float(getattr(value, "y", 0.0)), 6),
        "z": round(float(getattr(value, "z", 0.0)), 6),
    }


def get_sketch_geometry(
    document: object,
    sketch_name: str,
    *,
    include_constraints: bool,
    include_external: bool,
    global_coords: bool,
) -> dict[str, object]:
    sketch = require_object(document, sketch_name)
    if getattr(sketch, "TypeId", "") != "Sketcher::SketchObject" and not getattr(
        sketch, "isDerivedFrom", lambda _t: False
    )("Sketcher::SketchObject"):
        raise TypedMutationError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")

    def maybe_global(vector: object) -> object:
        if not global_coords:
            return vector
        getter = getattr(sketch, "getGlobalPlacement", None)
        if callable(getter):
            try:
                return getter().multVec(vector)
            except Exception:
                pass
        placement = getattr(sketch, "Placement", None)
        if placement is not None and hasattr(placement, "multVec"):
            return placement.multVec(vector)
        return vector

    def construction(index: int, geo: object) -> bool:
        try:
            from Sketcher import GeometryFacade

            return bool(GeometryFacade.getConstruction(geo))
        except Exception:
            try:
                return bool(getattr(sketch, "getConstruction")(index))
            except Exception:
                return bool(getattr(geo, "Construction", False))

    def geo_info(index: int, geo: object) -> dict[str, object]:
        info: dict[str, object] = {
            "index": index,
            "type": type(geo).__name__,
            "construction": construction(index, geo),
        }
        for name in ("StartPoint", "EndPoint", "Center", "Location"):
            if hasattr(geo, name):
                val = getattr(geo, name)
                key = name[0].lower() + name[1:]
                info[f"{key}_local"] = _vec(val)
                info[f"{key}_global"] = _vec(maybe_global(val))
        if hasattr(geo, "Radius"):
            info["radius"] = round(float(getattr(geo, "Radius", 0.0)), 6)
        if hasattr(geo, "MajorRadius"):
            info["major_radius"] = round(float(getattr(geo, "MajorRadius", 0.0)), 6)
        if hasattr(geo, "MinorRadius"):
            info["minor_radius"] = round(float(getattr(geo, "MinorRadius", 0.0)), 6)
        return info

    geometry = list(getattr(sketch, "Geometry", []) or [])
    result: dict[str, object] = {
        "ok": True,
        "sketch_name": str(getattr(sketch, "Name", sketch_name)),
        "geometry_count": len(geometry),
        "geometry": [geo_info(i, g) for i, g in enumerate(geometry)],
    }
    if include_constraints:
        constraints = []
        for index, constraint in enumerate(getattr(sketch, "Constraints", []) or []):
            constraints.append(
                {
                    "index": index,
                    "type": str(getattr(constraint, "Type", "")),
                    "first": getattr(constraint, "First", None),
                    "first_pos": getattr(constraint, "FirstPos", None),
                    "second": getattr(constraint, "Second", None),
                    "second_pos": getattr(constraint, "SecondPos", None),
                    "third": getattr(constraint, "Third", None),
                    "third_pos": getattr(constraint, "ThirdPos", None),
                    "value": getattr(constraint, "Value", None),
                }
            )
        result["constraints"] = constraints
    if include_external:
        external = []
        for index, entry in enumerate(getattr(sketch, "ExternalGeometry", []) or []):
            try:
                obj, subs = entry
                external.append(
                    {
                        "index": index,
                        "negative_index": -3 - index,
                        "object": str(getattr(obj, "Name", obj)),
                        "sub_elements": list(subs) if isinstance(subs, (list, tuple)) else [subs],
                    }
                )
            except Exception as exc:
                external.append({"index": index, "error": str(exc)})
        result["external_geometry"] = external
    return result


__all__ = ["get_document_tree", "get_sketch_geometry"]
