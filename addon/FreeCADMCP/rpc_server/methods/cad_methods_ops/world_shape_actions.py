"""Shared world-frame shape resolution for measure and diagnostics."""

from __future__ import annotations

import math

from .typed_runtime import TypedMutationError, load_module, module_callable


def _freecad() -> object:
    return load_module("FreeCAD")


def _shape_has_topology(shape: object) -> bool:
    if shape is None:
        return False
    is_null = getattr(shape, "isNull", None)
    if callable(is_null):
        try:
            if bool(is_null()):
                return False
        except Exception:
            return False
    return bool(
        getattr(shape, "Faces", None)
        or getattr(shape, "Edges", None)
        or getattr(shape, "Vertexes", None)
    )


def _linked_target(obj: object) -> object | None:
    linked = getattr(obj, "LinkedObject", None)
    if isinstance(linked, tuple):
        if not linked or linked[0] is None:
            raise TypedMutationError(
                "SHAPE_NOT_FOUND",
                "cross-document link target is missing or unresolved",
            )
        linked = linked[0]
    return linked


def _is_link_type(obj: object) -> bool:
    type_id = str(getattr(obj, "TypeId", ""))
    return type_id == "App::Link" or type_id.startswith("App::Link")


def _resolve_shape_source(obj: object) -> tuple[object | None, object | None]:
    if obj is None:
        return None, None
    shape = getattr(obj, "Shape", None)
    if _shape_has_topology(shape):
        return shape, obj
    linked = _linked_target(obj)
    if linked is not None and linked is not obj:
        return _resolve_shape_source(linked)
    return None, None


def _parent_geo_feature_groups(obj: object) -> list[object]:
    groups: list[object] = []
    cursor: object | None = obj
    seen: set[int] = set()
    while cursor is not None:
        getter = getattr(cursor, "getParentGeoFeatureGroup", None)
        parent: object | None = getter() if callable(getter) else None
        if parent is None:
            break
        parent_id = id(parent)
        if parent_id in seen:
            break
        seen.add(parent_id)
        groups.append(parent)
        cursor = parent
    return groups


def _compose_global_from_parents(obj: object) -> object | None:
    local = getattr(obj, "Placement", None)
    if local is None:
        return None
    result = local
    for parent in _parent_geo_feature_groups(obj):
        parent_pl = getattr(parent, "Placement", None)
        if parent_pl is not None:
            result = parent_pl * result  # type: ignore[operator]
    return result


def read_global_placement(obj: object) -> object:
    getter = getattr(obj, "getGlobalPlacement", None)
    if callable(getter):
        placement: object | None = None
        try:
            placement = getter()
        except Exception:
            placement = None
        if placement is not None:
            return placement
    composed = _compose_global_from_parents(obj)
    if composed is not None:
        return composed
    placement = getattr(obj, "Placement", None)
    if placement is None:
        raise TypedMutationError("INVALID_OBJECT", "object must provide Placement")
    return placement


def _scale_factors(obj: object) -> tuple[float, float, float]:
    scale_vector = getattr(obj, "ScaleVector", None)
    if scale_vector is not None:
        return (
            float(getattr(scale_vector, "x", 1.0)),
            float(getattr(scale_vector, "y", 1.0)),
            float(getattr(scale_vector, "z", 1.0)),
        )
    scale = getattr(obj, "Scale", None)
    if scale is not None:
        value = float(scale)
        return (value, value, value)
    return (1.0, 1.0, 1.0)


def _identity_matrix() -> object:
    return module_callable(_freecad(), "Matrix")()


def _matrix_multiply(left: object, right: object) -> object:
    multiply = getattr(left, "__mul__", None)
    if not callable(multiply):
        raise TypedMutationError("INVALID_SHAPE", "matrix does not support multiply")
    return multiply(right)


def _compose_matrices_parent_first(mats: list[object]) -> object:
    if not mats:
        return _identity_matrix()
    result = _identity_matrix()
    for matrix in mats:
        result = _matrix_multiply(matrix, result)
    return result


def _apply_scale_to_matrix(matrix: object, obj: object) -> object:
    sx, sy, sz = _scale_factors(obj)
    if sx == 1.0 and sy == 1.0 and sz == 1.0:
        return matrix
    scale_matrix = _identity_matrix()
    scaler = getattr(scale_matrix, "scale", None)
    if not callable(scaler):
        raise TypedMutationError("MISSING_DEPENDENCY", "Matrix.scale is not available")
    scaler(sx, sy, sz)
    return _matrix_multiply(matrix, scale_matrix)


def _placement_to_matrix(placement: object) -> object:
    to_matrix = getattr(placement, "toMatrix", None)
    if not callable(to_matrix):
        raise TypedMutationError("INVALID_SHAPE", "placement must provide toMatrix")
    return to_matrix()


def _link_world_matrix(obj: object) -> object:
    """Build link transform from Placement/LinkPlacement + Scale/ScaleVector only."""
    link_transform = bool(getattr(obj, "LinkTransform", False))
    if link_transform:
        placement = getattr(obj, "LinkPlacement", None) or getattr(obj, "Placement", None)
    else:
        placement = getattr(obj, "Placement", None)
    matrix = _placement_to_matrix(placement) if placement is not None else _identity_matrix()
    return _apply_scale_to_matrix(matrix, obj)


def _container_placement_matrix(obj: object) -> object | None:
    groups = _parent_geo_feature_groups(obj)
    if not groups:
        return None
    freecad = _freecad()
    placement_cls = module_callable(freecad, "Placement")
    result = placement_cls()
    for parent in groups:
        parent_pl = getattr(parent, "Placement", None)
        if parent_pl is not None:
            result = parent_pl * result  # type: ignore[operator]
    return _placement_to_matrix(result)


def _world_transform_matrix(
    obj: object,
    *,
    used_linked_object: bool,
    healthy_link_proxy: bool,
) -> object | None:
    mats: list[object] = []
    if used_linked_object:
        mats.append(_link_world_matrix(obj))
        container = _container_placement_matrix(obj)
        if container is not None:
            mats.append(container)
    elif healthy_link_proxy:
        container = _container_placement_matrix(obj)
        if container is not None:
            mats.append(container)
    else:
        mats.append(_placement_to_matrix(read_global_placement(obj)))
    if not mats:
        return None
    return _compose_matrices_parent_first(mats)


def _copy_shape(shape: object) -> object:
    part = load_module("Part")
    shape_cls = module_callable(part, "Shape")
    try:
        return shape_cls(shape)
    except Exception:
        copied = getattr(shape, "copy", None)
        if not callable(copied):
            raise TypedMutationError("INVALID_SHAPE", "shape must provide copy")
        return copied()


def _placement_meta(placement: object) -> dict[str, object]:
    rotation = getattr(placement, "Rotation", None)
    base = getattr(placement, "Base", None)
    return {
        "base": [
            round(float(getattr(base, "x", 0.0)), 6),
            round(float(getattr(base, "y", 0.0)), 6),
            round(float(getattr(base, "z", 0.0)), 6),
        ],
        "rotation_axis": [
            round(float(getattr(getattr(rotation, "Axis", None), "x", 0.0)), 6),
            round(float(getattr(getattr(rotation, "Axis", None), "y", 0.0)), 6),
            round(float(getattr(getattr(rotation, "Axis", None), "z", 0.0)), 6),
        ],
        "rotation_angle_deg": round(
            float(getattr(rotation, "Angle", 0.0)) * 180.0 / math.pi, 6
        ),
    }


def resolve_global_shape(obj: object) -> tuple[object, dict[str, object]]:
    shape, source = _resolve_shape_source(obj)
    if shape is None or source is None:
        raise TypedMutationError(
            "SHAPE_NOT_FOUND",
            f"No usable Shape on {getattr(obj, 'Name', obj)!r}",
        )
    used_linked_object = source is not obj
    healthy_link_proxy = (
        not used_linked_object
        and _is_link_type(obj)
        and _shape_has_topology(getattr(obj, "Shape", None))
    )
    out = _copy_shape(shape)
    matrix = _world_transform_matrix(
        obj,
        used_linked_object=used_linked_object,
        healthy_link_proxy=healthy_link_proxy,
    )
    if matrix is not None:
        transform = getattr(out, "transformShape", None)
        if not callable(transform):
            raise TypedMutationError("INVALID_SHAPE", "shape must provide transformShape")
        transform(matrix)
    try:
        global_pl = read_global_placement(obj)
    except TypedMutationError:
        global_pl = getattr(obj, "Placement", None)
    meta: dict[str, object] = {
        "object": getattr(obj, "Name", None),
        "type_id": getattr(obj, "TypeId", None),
        "shape_source": getattr(source, "Name", None),
        "used_linked_object": used_linked_object,
        "global_placement": _placement_meta(global_pl) if global_pl is not None else {},
    }
    return out, meta


__all__ = [
    "read_global_placement",
    "resolve_global_shape",
]
