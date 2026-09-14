"""Apply helpers for typed measure, transform, and IO mutations.

Apply never recomputes the document. Export still runs inside a native
transaction; inspect remains read-only.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .typed_runtime import (
    TypedMutationError,
    load_module,
    module_callable,
    object_name,
    require_object,
)


def _freecad() -> object:
    return load_module("FreeCAD")


def _vector(x: float, y: float, z: float = 0.0) -> object:
    return module_callable(_freecad(), "Vector")(x, y, z)


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
        linked = linked[0] if linked else None
    return linked


def _raw_shape(obj: object) -> tuple[object | None, object | None]:
    if obj is None:
        return None, None
    shape = getattr(obj, "Shape", None)
    if _shape_has_topology(shape):
        return shape, obj
    linked = _linked_target(obj)
    if linked is not None and linked is not obj:
        return _raw_shape(linked)
    return None, None


def _is_document_child(obj: object) -> bool:
    for parent in getattr(obj, "InList", None) or []:
        if getattr(parent, "TypeId", "") == "App::Document":
            return True
    return False


def _read_global_placement(obj: object) -> object:
    if _is_document_child(obj):
        placement = getattr(obj, "Placement", None)
        if placement is None:
            raise TypedMutationError("INVALID_OBJECT", "object must provide Placement")
        return placement
    geo_feature = getattr(_freecad(), "GeoFeature", None)
    if geo_feature is not None:
        getter = getattr(geo_feature, "getGlobalPlacementOf", None)
        if callable(getter):
            placement = getter(obj, obj, "")
            if placement is not None:
                return placement
    placement = getattr(obj, "Placement", None)
    if placement is None:
        raise TypedMutationError("INVALID_OBJECT", "object must provide Placement")
    return placement


def resolve_global_shape(obj: object) -> tuple[object, dict[str, object]]:
    shape, source = _raw_shape(obj)
    if shape is None or source is None:
        raise TypedMutationError(
            "SHAPE_NOT_FOUND",
            f"No usable Shape on {getattr(obj, 'Name', obj)!r}",
        )
    placement = _read_global_placement(obj)
    part = load_module("Part")
    shape_cls = module_callable(part, "Shape")
    try:
        out = shape_cls(shape)
    except Exception:
        copied = getattr(shape, "copy", None)
        if not callable(copied):
            raise TypedMutationError("INVALID_SHAPE", "shape must provide copy")
        out = copied()
    transform = getattr(out, "transformShape", None)
    matrix = getattr(placement, "toMatrix", None)
    if not callable(transform) or not callable(matrix):
        raise TypedMutationError("INVALID_SHAPE", "shape must provide transformShape")
    transform(matrix())
    rotation = getattr(placement, "Rotation", None)
    base = getattr(placement, "Base", None)
    meta: dict[str, object] = {
        "object": getattr(obj, "Name", None),
        "type_id": getattr(obj, "TypeId", None),
        "shape_source": getattr(source, "Name", None),
        "used_linked_object": source is not obj,
        "global_placement": {
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
        },
    }
    return out, meta


def bounding_box(document: object, obj_name: str) -> dict[str, object]:
    obj = require_object(document, obj_name)
    shape, meta = resolve_global_shape(obj)
    box = getattr(shape, "BoundBox", None)
    if box is None:
        raise TypedMutationError("SHAPE_NOT_FOUND", f"Object has no BoundBox: {obj_name!r}")
    payload: dict[str, object] = {
        "object": object_name(obj),
        "xmin": round(float(getattr(box, "XMin", 0.0)), 6),
        "ymin": round(float(getattr(box, "YMin", 0.0)), 6),
        "zmin": round(float(getattr(box, "ZMin", 0.0)), 6),
        "xmax": round(float(getattr(box, "XMax", 0.0)), 6),
        "ymax": round(float(getattr(box, "YMax", 0.0)), 6),
        "zmax": round(float(getattr(box, "ZMax", 0.0)), 6),
        "dx": round(float(getattr(box, "XLength", 0.0)), 6),
        "dy": round(float(getattr(box, "YLength", 0.0)), 6),
        "dz": round(float(getattr(box, "ZLength", 0.0)), 6),
        "diagonal": round(float(getattr(box, "DiagonalLength", 0.0)), 6),
        "frame": "world",
    }
    payload.update(meta)
    return payload


def center_of_mass(document: object, obj_name: str) -> dict[str, object]:
    obj = require_object(document, obj_name)
    shape, meta = resolve_global_shape(obj)
    solids = getattr(shape, "Solids", None)
    com = getattr(shape, "CenterOfMass", None)
    method = "shape"
    if com is not None and solids:
        method = "solid"
    elif solids:
        total = 0.0
        wx = 0.0
        wy = 0.0
        wz = 0.0
        for solid in solids:
            volume = float(getattr(solid, "Volume", 0.0) or 0.0)
            total += volume
            center = getattr(solid, "CenterOfMass", None)
            wx += float(getattr(center, "x", 0.0)) * volume
            wy += float(getattr(center, "y", 0.0)) * volume
            wz += float(getattr(center, "z", 0.0)) * volume
        if total <= 0:
            raise TypedMutationError("INVALID_SHAPE", "Compound has zero volume")
        com = _vector(wx / total, wy / total, wz / total)
        method = "solid"
    if com is None:
        raise TypedMutationError("SHAPE_NOT_FOUND", f"Object has no CenterOfMass: {obj_name!r}")
    payload: dict[str, object] = {
        "object": object_name(obj),
        "x": round(float(getattr(com, "x", 0.0)), 6),
        "y": round(float(getattr(com, "y", 0.0)), 6),
        "z": round(float(getattr(com, "z", 0.0)), 6),
        "unit": "mm",
        "method": method,
        "frame": "world",
    }
    payload.update(meta)
    return payload


def _as_float_map(sample: object) -> Mapping[str, object]:
    if not isinstance(sample, Mapping):
        raise TypedMutationError("INVALID_ARGUMENT", "Each sample must be a dict with x/y/z")
    return sample



def _require_coord(item: Mapping[str, object], key: str) -> float:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypedMutationError("INVALID_ARGUMENT", f"sample {key} must be a number")
    return float(value)


def common_volume_along_path(
    document: object,
    *,
    moving_object: str,
    obstacle_objects: Sequence[str],
    path_object: str | None,
    sample_count: int,
    samples: Sequence[object] | None,
    volume_threshold_mm3: float,
    stop_on_first_hit: bool,
) -> dict[str, object]:
    if not obstacle_objects:
        raise TypedMutationError("INVALID_ARGUMENT", "obstacle_objects must contain at least one object name")
    moving = require_object(document, moving_object)
    moving_shape, moving_meta = resolve_global_shape(moving)
    origin_map = moving_meta.get("global_placement")
    origin_base = origin_map.get("base") if isinstance(origin_map, Mapping) else None
    if not isinstance(origin_base, list) or len(origin_base) != 3:
        raise TypedMutationError("INVALID_SHAPE", "moving object is missing global placement")
    origin = _vector(
        _require_coord({"x": origin_base[0]}, "x"),
        _require_coord({"x": origin_base[1]}, "x"),
        _require_coord({"x": origin_base[2]}, "x"),
    )
    obstacles: list[tuple[str, object, dict[str, object]]] = []
    for name in obstacle_objects:
        obj = require_object(document, name, code="OBSTACLE_NOT_FOUND")
        shape, meta = resolve_global_shape(obj)
        obstacles.append((name, shape, meta))

    positions: list[dict[str, object]] = []
    if samples:
        for index, sample in enumerate(samples):
            item = _as_float_map(sample)
            yaw = item.get("yaw_deg")
            positions.append(
                {
                    "index": index,
                    "parameter": _require_coord({"x": item.get("parameter", index)}, "x"),
                    "x": _require_coord(item, "x"),
                    "y": _require_coord(item, "y"),
                    "z": _require_coord(item, "z"),
                    "yaw_deg": float(yaw) if isinstance(yaw, (int, float)) and not isinstance(yaw, bool) else None,
                }
            )
    elif path_object:
        path_obj = require_object(document, path_object, code="PATH_NOT_FOUND")
        path_shape, _meta = resolve_global_shape(path_obj)
        edges = list(getattr(path_shape, "Edges", []) or [])
        if not edges:
            raise TypedMutationError("INVALID_PATH", f"Path object has no edges: {path_object!r}")
        if sample_count < 2:
            raise TypedMutationError("INVALID_ARGUMENT", "sample_count must be >= 2 when sampling a path")
        part = load_module("Part")
        try:
            wire = module_callable(part, "Wire")(edges)
        except Exception:
            wire = edges[0]
        pts: list[object] = []
        discretize = getattr(wire, "discretize", None)
        if callable(discretize):
            try:
                pts = list(discretize(Number=sample_count))
            except Exception:
                pts = []
        if not pts:
            length = float(getattr(wire, "Length", 0.0) or 0.0)
            for index in range(sample_count):
                u = 0.0 if sample_count == 1 else (index / float(sample_count - 1))
                value_at = getattr(wire, "valueAt", None)
                if callable(value_at) and length > 0:
                    pts.append(value_at(u * length))
                else:
                    edge = edges[0]
                    first = float(getattr(edge, "FirstParameter", 0.0))
                    last = float(getattr(edge, "LastParameter", 0.0))
                    pts.append(module_callable(edge, "valueAt")(first + u * (last - first)))
        for index, point in enumerate(pts):
            u = 0.0 if len(pts) == 1 else (index / float(len(pts) - 1))
            positions.append(
                {
                    "index": index,
                    "parameter": round(u, 6),
                    "x": float(getattr(point, "x", 0.0)),
                    "y": float(getattr(point, "y", 0.0)),
                    "z": float(getattr(point, "z", 0.0)),
                    "yaw_deg": None,
                }
            )
    else:
        raise TypedMutationError("INVALID_ARGUMENT", "Provide samples or path_object")

    results: list[dict[str, object]] = []
    max_volume = 0.0
    any_hit = False
    for pos in positions:
        target = _vector(_require_coord(pos, "x"), _require_coord(pos, "y"), _require_coord(pos, "z"))
        delta = module_callable(target, "sub")(origin) if callable(getattr(target, "sub", None)) else target
        probe_copy = getattr(moving_shape, "copy", None)
        if not callable(probe_copy):
            raise TypedMutationError("INVALID_SHAPE", "moving shape must provide copy")
        probe = probe_copy()
        translate = getattr(probe, "translate", None)
        if callable(translate):
            translate(delta)
        yaw_deg = pos.get("yaw_deg")
        if isinstance(yaw_deg, float):
            rotate = getattr(probe, "rotate", None)
            if callable(rotate):
                rotate(target, _vector(0.0, 0.0, 1.0), yaw_deg)
        common_volume = 0.0
        hits: list[dict[str, object]] = []
        for oname, oshape, _ometa in obstacles:
            try:
                common = module_callable(probe, "common")(oshape)
                volume = float(getattr(common, "Volume", 0.0) or 0.0)
            except Exception as exc:
                hits.append({"object": oname, "error": str(exc), "volume_mm3": None})
                continue
            if volume > 0.0:
                hits.append({"object": oname, "volume_mm3": round(volume, 6)})
                common_volume += volume
        colliding = common_volume >= volume_threshold_mm3
        if colliding:
            any_hit = True
        if common_volume > max_volume:
            max_volume = common_volume
        results.append(
            {
                "index": pos["index"],
                "parameter": pos["parameter"],
                "position": [
                    round(_require_coord(pos, "x"), 6),
                    round(_require_coord(pos, "y"), 6),
                    round(_require_coord(pos, "z"), 6),
                ],
                "common_volume_mm3": round(common_volume, 6),
                "colliding": colliding,
                "hits": hits,
            }
        )
        if stop_on_first_hit and colliding:
            break
    return {
        "moving_object": str(moving_meta.get("object") or moving_object),
        "sample_count": len(results),
        "volume_threshold_mm3": volume_threshold_mm3,
        "max_common_volume_mm3": round(max_volume, 6),
        "any_collision": any_hit,
        "samples": results,
    }


def translate(document: object, obj_name: str, dx: float, dy: float, dz: float) -> dict[str, str]:
    obj = require_object(document, obj_name)
    current = getattr(obj, "Placement", None)
    if current is None:
        raise TypedMutationError("INVALID_OBJECT", f"Object has no Placement: {obj_name!r}")
    placement_cls = module_callable(_freecad(), "Placement")
    updated = placement_cls(current)
    base = getattr(updated, "Base", None)
    setattr(updated, "Base", base + _vector(dx, dy, dz))  # type: ignore[operator]
    setattr(obj, "Placement", updated)
    return {"object": object_name(obj), "label": str(getattr(obj, "Label", obj_name))}


def rotate(
    document: object,
    obj_name: str,
    *,
    axis_x: float,
    axis_y: float,
    axis_z: float,
    angle_deg: float,
    center_x: float,
    center_y: float,
    center_z: float,
) -> dict[str, str]:
    obj = require_object(document, obj_name)
    freecad = _freecad()
    rotation_cls = module_callable(freecad, "Rotation")
    placement_cls = module_callable(freecad, "Placement")
    axis = _vector(axis_x, axis_y, axis_z)
    center = _vector(center_x, center_y, center_z)
    rot = rotation_cls(axis, angle_deg)
    current = getattr(obj, "Placement", None)
    if current is None:
        raise TypedMutationError("INVALID_OBJECT", f"Object has no Placement: {obj_name!r}")
    identity = rotation_cls()
    composed = placement_cls(center, identity)
    composed = composed * placement_cls(_vector(0.0, 0.0, 0.0), rot)  # type: ignore[operator]
    composed = composed * placement_cls(_vector(-center_x, -center_y, -center_z), identity)
    composed = composed * current
    setattr(obj, "Placement", composed)
    return {"object": object_name(obj), "label": str(getattr(obj, "Label", obj_name))}


def scale(document: object, obj_name: str, sx: float, sy: float, sz: float) -> dict[str, str]:
    obj = require_object(document, obj_name)
    type_id = str(getattr(obj, "TypeId", ""))
    if type_id.startswith("Part::") and type_id != "Part::Feature":
        raise TypedMutationError(
            "SCALE_NOT_SUPPORTED",
            f"Cannot scale parametric primitive directly: {obj_name!r}",
        )
    shape = getattr(obj, "Shape", None)
    if shape is None:
        raise TypedMutationError("SHAPE_NOT_FOUND", f"Object with Shape not found: {obj_name!r}")
    matrix_cls = module_callable(_freecad(), "Matrix")
    matrix = matrix_cls()
    scaler = getattr(matrix, "scale", None)
    if not callable(scaler):
        raise TypedMutationError("MISSING_DEPENDENCY", "Matrix.scale is not available")
    scaler(sx, sy, sz)
    transform = getattr(shape, "transformGeometry", None)
    if not callable(transform):
        raise TypedMutationError("INVALID_SHAPE", "shape must provide transformGeometry")
    setattr(obj, "Shape", transform(matrix))
    return {"object": object_name(obj), "label": str(getattr(obj, "Label", obj_name))}


def _exportable_objects(document: object, obj_names: Sequence[str] | None) -> list[object]:
    if obj_names:
        found = [require_object(document, name) for name in obj_names]
    else:
        found = list(getattr(document, "Objects", []) or [])
    exportable = [obj for obj in found if obj is not None and hasattr(obj, "Shape")]
    if not exportable:
        raise TypedMutationError("OBJECT_NOT_FOUND", "No exportable objects found")
    return exportable


def export_step(document: object, file_path: str, obj_names: Sequence[str] | None) -> dict[str, object]:
    objs = _exportable_objects(document, obj_names)
    exporter = module_callable(load_module("Import"), "export")
    exporter(objs, file_path)
    return {"path": file_path, "exported": len(objs)}


def export_stl(
    document: object,
    file_path: str,
    obj_names: Sequence[str] | None,
    mesh_deviation: float,
) -> dict[str, object]:
    objs = _exportable_objects(document, obj_names)
    mesh_mod = load_module("Mesh")
    mesh_cls = module_callable(mesh_mod, "Mesh")
    meshes = []
    for obj in objs:
        shape = getattr(obj, "Shape", None)
        tessellate = getattr(shape, "tessellate", None)
        if not callable(tessellate):
            raise TypedMutationError("INVALID_SHAPE", "shape must provide tessellate")
        meshes.append(mesh_cls(tessellate(mesh_deviation)))
    combined = mesh_cls()
    add_mesh = getattr(combined, "addMesh", None)
    if not callable(add_mesh):
        raise TypedMutationError("MISSING_DEPENDENCY", "Mesh.addMesh is not available")
    for mesh in meshes:
        add_mesh(mesh)
    writer = getattr(combined, "write", None)
    if not callable(writer):
        raise TypedMutationError("MISSING_DEPENDENCY", "Mesh.write is not available")
    writer(file_path)
    return {
        "path": file_path,
        "exported": len(objs),
        "faces": int(getattr(combined, "CountFacets", 0) or 0),
    }


def export_brep(document: object, obj_name: str, file_path: str) -> dict[str, object]:
    obj = require_object(document, obj_name)
    shape = getattr(obj, "Shape", None)
    exporter = getattr(shape, "exportBrep", None)
    if not callable(exporter):
        raise TypedMutationError("SHAPE_NOT_FOUND", f"Object not found or has no Shape: {obj_name!r}")
    exporter(file_path)
    return {"path": file_path, "exported": True, "object": object_name(obj)}


def import_step(document: object, file_path: str) -> dict[str, object]:
    inserter = module_callable(load_module("Import"), "insert")
    inserter(file_path, str(getattr(document, "Name", "")))
    return {"path": file_path, "imported": True}


def import_brep(document: object, file_path: str, obj_name: str) -> dict[str, object]:
    part = load_module("Part")
    shape_cls = module_callable(part, "Shape")
    shape = shape_cls()
    importer = getattr(shape, "importBrep", None)
    if not callable(importer):
        raise TypedMutationError("MISSING_DEPENDENCY", "Part.Shape.importBrep is not available")
    importer(file_path)
    adder = getattr(document, "addObject", None)
    if not callable(adder):
        raise TypedMutationError("INVALID_DOCUMENT", "document must provide addObject")
    obj = adder("Part::Feature", obj_name)
    setattr(obj, "Shape", shape)
    return {"path": file_path, "object": object_name(obj), "imported": True}


__all__ = [
    "bounding_box",
    "center_of_mass",
    "common_volume_along_path",
    "export_brep",
    "export_step",
    "export_stl",
    "import_brep",
    "import_step",
    "rotate",
    "scale",
    "translate",
]
