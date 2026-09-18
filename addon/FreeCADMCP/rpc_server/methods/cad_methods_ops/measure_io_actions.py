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
from .world_shape_actions import resolve_global_shape


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
    current = placement_cls(current)
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


def _parse_edge_ref(document: object, ref: str) -> object:
    parts = ref.split(":")
    obj = require_object(document, parts[0])
    shape, _meta = resolve_global_shape(obj)
    if len(parts) > 1:
        sub = parts[1]
        if sub.startswith("Edge"):
            index = int(sub[4:]) - 1
            edges = getattr(shape, "Edges", None) or []
            if index < 0 or index >= len(edges):
                raise TypedMutationError("INVALID_ARGUMENT", f"edge index out of range: {ref!r}")
            return edges[index]
    return shape


def measure_distance(document: object, shape1_ref: str, shape2_ref: str) -> dict[str, object]:
    obj1 = require_object(document, shape1_ref)
    obj2 = require_object(document, shape2_ref)
    shape1, _meta1 = resolve_global_shape(obj1)
    shape2, _meta2 = resolve_global_shape(obj2)
    dist_to_shape = getattr(shape1, "distToShape", None)
    if not callable(dist_to_shape):
        raise TypedMutationError("MEASURE_DISTANCE_FAILED", "shape does not support distToShape")
    result = dist_to_shape(shape2)
    distance = float(result[0]) if isinstance(result, (list, tuple)) and result else float(result)
    return {"distance": round(distance, 6), "unit": "mm"}


def measure_angle(document: object, edge1_ref: str, edge2_ref: str) -> dict[str, object]:
    edge1 = _parse_edge_ref(document, edge1_ref)
    edge2 = _parse_edge_ref(document, edge2_ref)
    tangent_at = getattr(edge1, "tangentAt", None)
    if not callable(tangent_at):
        raise TypedMutationError("MEASURE_ANGLE_FAILED", "edge does not support tangentAt")
    first_param = getattr(edge1, "FirstParameter", 0.0)
    second_param = getattr(edge2, "FirstParameter", 0.0)
    vector1 = tangent_at(first_param)
    vector2 = getattr(edge2, "tangentAt")(second_param)
    length1 = float(getattr(vector1, "Length", 0.0) or 0.0)
    length2 = float(getattr(vector2, "Length", 0.0) or 0.0)
    if length1 <= 0 or length2 <= 0:
        raise TypedMutationError("MEASURE_ANGLE_FAILED", "edge tangent has zero length")
    dot = getattr(vector1, "dot", None)
    if not callable(dot):
        raise TypedMutationError("MEASURE_ANGLE_FAILED", "tangent vector does not support dot")
    cosine = max(-1.0, min(1.0, float(dot(vector2)) / (length1 * length2)))
    angle_deg = math.degrees(math.acos(cosine))
    return {"angle_deg": round(angle_deg, 6), "unit": "degrees"}


def measure_area(document: object, obj_name: str) -> dict[str, object]:
    obj = require_object(document, obj_name)
    shape, meta = resolve_global_shape(obj)
    area = float(getattr(shape, "Area", 0.0) or 0.0)
    payload: dict[str, object] = {
        "object": object_name(obj),
        "area_mm2": round(area, 6),
        "area_cm2": round(area / 100.0, 6),
        "unit": "mm²",
        "frame": "world",
    }
    payload.update(meta)
    return payload


def measure_volume(document: object, obj_name: str) -> dict[str, object]:
    obj = require_object(document, obj_name)
    shape, meta = resolve_global_shape(obj)
    volume = float(getattr(shape, "Volume", 0.0) or 0.0)
    payload: dict[str, object] = {
        "object": object_name(obj),
        "volume_mm3": round(volume, 6),
        "unit": "mm³",
        "frame": "world",
    }
    payload.update(meta)
    return payload


def get_global_shape(document: object, obj_name: str) -> dict[str, object]:
    obj = require_object(document, obj_name)
    shape, meta = resolve_global_shape(obj)
    box = getattr(shape, "BoundBox", None)
    if box is None:
        raise TypedMutationError("SHAPE_NOT_FOUND", f"Object has no BoundBox: {obj_name!r}")
    com = None
    center = getattr(shape, "CenterOfMass", None)
    if center is not None:
        com = [
            round(float(getattr(center, "x", 0.0)), 6),
            round(float(getattr(center, "y", 0.0)), 6),
            round(float(getattr(center, "z", 0.0)), 6),
        ]
    payload: dict[str, object] = {
        "object": object_name(obj),
        "frame": "world",
        "volume_mm3": round(float(getattr(shape, "Volume", 0.0) or 0.0), 6),
        "area_mm2": round(float(getattr(shape, "Area", 0.0) or 0.0), 6),
        "center_of_mass": com,
        "bbox": {
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
        },
        "solids": len(getattr(shape, "Solids", []) or []),
        "faces": len(getattr(shape, "Faces", []) or []),
        "edges": len(getattr(shape, "Edges", []) or []),
    }
    payload.update(meta)
    return payload


def validate_geometry(document: object, obj_name: str) -> dict[str, object]:
    obj = require_object(document, obj_name)
    shape = getattr(obj, "Shape", None)
    if shape is None:
        raise TypedMutationError("OBJECT_NOT_FOUND", "Object has no Shape")
    is_null = bool(getattr(shape, "isNull", lambda: True)())
    is_valid = bool(getattr(shape, "isValid", lambda: False)())
    is_closed = bool(getattr(shape, "isClosed", lambda: False)())
    result: dict[str, object] = {
        "object": object_name(obj),
        "is_null": is_null,
        "is_valid": is_valid,
        "is_closed": is_closed,
        "volume_mm3": round(float(getattr(shape, "Volume", 0.0) or 0.0), 6),
        "area_mm2": round(float(getattr(shape, "Area", 0.0) or 0.0), 6),
        "face_count": len(getattr(shape, "Faces", []) or []),
        "edge_count": len(getattr(shape, "Edges", []) or []),
        "vertex_count": len(getattr(shape, "Vertexes", []) or []),
        "shape_type": str(getattr(shape, "ShapeType", "")),
    }
    check = getattr(shape, "check", None)
    if callable(check):
        try:
            check(False)
            result["check_ok"] = True
            result["check_errors"] = []
        except Exception as exc:
            result["check_ok"] = False
            result["check_errors"] = [str(exc)]
    else:
        result["check_ok"] = is_valid
        result["check_errors"] = []
    return result


__all__ = [
    "bounding_box",
    "center_of_mass",
    "get_global_shape",
    "measure_angle",
    "measure_area",
    "measure_distance",
    "measure_volume",
    "resolve_global_shape",
    "validate_geometry",
    "export_brep",
    "export_step",
    "export_stl",
    "import_brep",
    "import_step",
    "rotate",
    "scale",
    "translate",
]
