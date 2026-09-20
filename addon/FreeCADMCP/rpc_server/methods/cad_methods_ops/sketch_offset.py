"""Typed ``sketch_offset`` mutation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.sketch_offset_contract import (
        SketchOffsetCollaborators,
        SketchOffsetFailure,
        SketchOffsetRequest,
        SketchOffsetResult,
        DocumentName,
        SketchDocument,
        SketchFreeCAD,
        SketchName,
        SketchObject,
        SketchPart,
        SketchReadDocument,
        make_sketch_offset_failure,
        make_sketch_offset_success,
        make_sketch_offset_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_offset_contract import (
        SketchOffsetCollaborators,
        SketchOffsetFailure,
        SketchOffsetRequest,
        SketchOffsetResult,
        DocumentName,
        SketchDocument,
        SketchFreeCAD,
        SketchName,
        SketchObject,
        SketchPart,
        SketchReadDocument,
        make_sketch_offset_failure,
        make_sketch_offset_success,
        make_sketch_offset_uncertain,
    )
from .sketch_offset_mutation import SketchOffsetError, run_sketch_offset_native_mutation


@dataclass(frozen=True, slots=True)
class SketchExecReceipt:
    name: str
    sketch: SketchObject
    geometry_index: int
    geometry_count_before: int
    constraint_count_before: int
    sample_count: int


@dataclass(frozen=True, slots=True)
class SketchExecInspection:
    sketch_name: SketchName
    geometry_index: int
    geometry_indices: list[int]
    constraint_index: int
    sample_count: int


def _failure(error: SketchOffsetError, *, retry_safe: bool = True) -> SketchOffsetFailure:
    return make_sketch_offset_failure(error.code, str(error), retry_safe=retry_safe)


def _require_name(value: object, field: str) -> str | SketchOffsetFailure:
    if not isinstance(value, str) or not value.strip():
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} must be a nonempty string"))
    return value


def _require_float(value: object, field: str) -> float | SketchOffsetFailure:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} must be a number"))
    return float(value)


def _require_int(value: object, field: str) -> int | SketchOffsetFailure:
    if type(value) is not int:
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_bool(value: object, field: str, *, default: bool) -> bool | SketchOffsetFailure:
    if value is None:
        return default
    if type(value) is not bool:
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} must be a boolean"))
    return value


def _require_optional_int(value: object, field: str) -> int | None | SketchOffsetFailure:
    if value is None:
        return None
    if type(value) is not int:
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} must be an integer"))
    return value


def _require_optional_str(value: object, field: str) -> str | None | SketchOffsetFailure:
    if value is None:
        return None
    if not isinstance(value, str):
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} must be a string"))
    return value


def _require_points(
    value: object, field: str, *, min_count: int
) -> tuple[tuple[float, float], ...] | SketchOffsetFailure:
    if not isinstance(value, list):
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} must be a list of points"))
    points: list[tuple[float, float]] = []
    for item in value:
        if not isinstance(item, dict):
            return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} entries must be objects"))
        x_value = _require_float(item.get("x"), f"{field}.x")
        y_value = _require_float(item.get("y"), f"{field}.y")
        if isinstance(x_value, dict):
            return x_value
        if isinstance(y_value, dict):
            return y_value
        points.append((x_value, y_value))
    if len(points) < min_count:
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} requires at least {min_count} points"))
    return tuple(points)


def _require_int_list(value: object, field: str) -> tuple[int, ...] | SketchOffsetFailure:
    if not isinstance(value, list) or not value:
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} must be a nonempty list of integers"))
    indices: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        indices.append(parsed)
    return tuple(indices)


def _require_optional_floats(value: object, field: str) -> tuple[float, ...] | None | SketchOffsetFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} must be a list of numbers"))
    numbers: list[float] = []
    for item in value:
        parsed = _require_float(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _require_optional_ints(value: object, field: str) -> tuple[int, ...] | None | SketchOffsetFailure:
    if value is None:
        return None
    if not isinstance(value, list):
        return _failure(SketchOffsetError("INVALID_ARGUMENT", f"{field} must be a list of integers"))
    numbers: list[int] = []
    for item in value:
        parsed = _require_int(item, field)
        if isinstance(parsed, dict):
            return parsed
        numbers.append(parsed)
    return tuple(numbers)


def _is_sketch(sketch: SketchObject) -> bool:
    try:
        return bool(sketch.isDerivedFrom("Sketcher::SketchObject"))
    except (AttributeError, TypeError):
        return sketch.TypeId == "Sketcher::SketchObject"


def _require_sketch(doc: SketchDocument, sketch_name: SketchName) -> SketchObject:
    sketch = doc.getObject(sketch_name)
    if sketch is None:
        raise SketchOffsetError("SKETCH_NOT_FOUND", f"Sketch not found: {sketch_name!r}")
    if not _is_sketch(sketch):
        raise SketchOffsetError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {sketch_name!r}")
    return sketch

def build_sketch_offset_request(
    doc_name: object,
    sketch_name: object,
    geo_indices: object,
    offset: object,
    copy: object,
    construction: object,
) -> SketchOffsetRequest | SketchOffsetFailure:
    doc_name_value = _require_name(doc_name, "doc_name")
    if isinstance(doc_name_value, dict):
        return doc_name_value
    sketch_name_value = _require_name(sketch_name, "sketch_name")
    if isinstance(sketch_name_value, dict):
        return sketch_name_value
    geo_indices_value = _require_int_list(geo_indices, "geo_indices")
    if isinstance(geo_indices_value, dict):
        return geo_indices_value
    offset_value = _require_float(offset, "offset")
    if isinstance(offset_value, dict):
        return offset_value
    if offset_value == 0:
        return _failure(SketchOffsetError("INVALID_ARGUMENT", "offset must be nonzero"))
    copy_value = _require_bool(copy, "copy", default=True)
    if isinstance(copy_value, dict):
        return copy_value
    construction_value = _require_bool(construction, "construction", default=False)
    if isinstance(construction_value, dict):
        return construction_value
    return SketchOffsetRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=SketchName(sketch_name_value),
        geo_indices=geo_indices_value,
        offset=offset_value,
        copy=copy_value,
        construction=construction_value,
    )


def _vector_xyz(point: object) -> tuple[float, float, float]:
    return (
        float(getattr(point, "x")),
        float(getattr(point, "y")),
        float(getattr(point, "z", 0.0)),
    )


def _edge_endpoints(shape: object) -> tuple[object, object] | None:
    vertices = getattr(shape, "Vertexes", None)
    if vertices is not None and len(vertices) == 2:
        return getattr(vertices[0], "Point", vertices[0]), getattr(vertices[1], "Point", vertices[1])
    return None


def _offset_line_endpoints(
    freecad: SketchFreeCAD,
    part: SketchPart,
    start: object,
    end: object,
    offset: float,
) -> object:
    sx, sy, _sz = _vector_xyz(start)
    ex, ey, _ez = _vector_xyz(end)
    dx = ex - sx
    dy = ey - sy
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        raise SketchOffsetError("OFFSET_FAILED", "degenerate line cannot be offset")
    nx = -dy / length * offset
    ny = dx / length * offset
    return part.LineSegment(
        freecad.Vector(sx + nx, sy + ny, 0.0),
        freecad.Vector(ex + nx, ey + ny, 0.0),
    )


def _offset_circle_like(
    freecad: SketchFreeCAD,
    part: SketchPart,
    center: object,
    radius: float,
    offset: float,
    *,
    first_parameter: float | None = None,
    last_parameter: float | None = None,
) -> object:
    new_radius = float(radius) + offset
    if new_radius <= 0:
        raise SketchOffsetError("OFFSET_FAILED", "offset would collapse circle")
    cx, cy, _cz = _vector_xyz(center)
    sketch_center = freecad.Vector(cx, cy, 0.0)
    sketch_axis = freecad.Vector(0.0, 0.0, 1.0)
    circle = part.Circle(sketch_center, sketch_axis, new_radius)
    if first_parameter is not None and last_parameter is not None:
        return part.ArcOfCircle(circle, first_parameter, last_parameter)
    return circle


def _offset_sketch_geometry(
    freecad: SketchFreeCAD,
    part: SketchPart,
    geom: object,
    offset: float,
) -> object | None:
    start = getattr(geom, "StartPoint", None)
    end = getattr(geom, "EndPoint", None)
    if start is not None and end is not None:
        return _offset_line_endpoints(freecad, part, start, end, offset)

    radius = getattr(geom, "Radius", None)
    center = getattr(geom, "Center", None)
    if radius is not None and center is not None:
        return _offset_circle_like(
            freecad,
            part,
            center,
            float(radius),
            offset,
            first_parameter=getattr(geom, "FirstParameter", None),
            last_parameter=getattr(geom, "LastParameter", None),
        )

    return None


def _call_make_offset2d(shape: object, offset: float) -> object:
    offset_fn = getattr(shape, "makeOffset2D", None)
    if not callable(offset_fn):
        raise SketchOffsetError("OFFSET_FAILED", "shape does not support makeOffset2D")
    return offset_fn(offset)


def _collect_offset_edges(offset_result: object) -> list[object]:
    edges = getattr(offset_result, "Edges", None)
    if edges is not None:
        return list(edges)
    wires = getattr(offset_result, "Wires", None)
    if wires is not None:
        collected: list[object] = []
        for wire in wires:
            wire_edges = getattr(wire, "Edges", None)
            if wire_edges is not None:
                collected.extend(wire_edges)
        return collected
    return [offset_result]


def _edge_to_sketch_geometry(
    freecad: SketchFreeCAD,
    part: SketchPart,
    edge: object,
) -> object:
    endpoints = _edge_endpoints(edge)
    if endpoints is not None:
        x1, y1, _z1 = _vector_xyz(endpoints[0])
        x2, y2, _z2 = _vector_xyz(endpoints[1])
        return part.LineSegment(
            freecad.Vector(x1, y1, 0.0),
            freecad.Vector(x2, y2, 0.0),
        )

    curve = getattr(edge, "Curve", None)
    if curve is not None:
        radius = getattr(curve, "Radius", None)
        center = getattr(curve, "Center", None)
        if radius is not None and center is not None:
            first = getattr(edge, "FirstParameter", None)
            last = getattr(edge, "LastParameter", None)
            return _offset_circle_like(
                freecad,
                part,
                center,
                float(radius),
                0.0,
                first_parameter=float(first) if first is not None else None,
                last_parameter=float(last) if last is not None else None,
            )

    if hasattr(edge, "toShape"):
        return edge

    raise SketchOffsetError("OFFSET_FAILED", "offset produced unsupported geometry")


def _offset_geometries(
    freecad: SketchFreeCAD,
    part: SketchPart,
    geometries: Sequence[object],
    offset: float,
) -> list[object]:
    results: list[object] = []
    pending: list[object] = []

    for geom in geometries:
        sketch_geom = _offset_sketch_geometry(freecad, part, geom, offset)
        if sketch_geom is not None:
            results.append(sketch_geom)
        else:
            pending.append(geom)

    if pending:
        try:
            shapes = []
            for geom in pending:
                if hasattr(geom, "toShape"):
                    shapes.append(geom.toShape())
                else:
                    shapes.append(part.Edge(geom))
            wire = part.Wire(shapes) if len(shapes) > 1 else part.Wire([shapes[0]])
            offset_result = _call_make_offset2d(wire, offset)
            for edge in _collect_offset_edges(offset_result):
                results.append(_edge_to_sketch_geometry(freecad, part, edge))
        except SketchOffsetError:
            raise
        except (TypeError, Exception) as exc:
            raise SketchOffsetError("OFFSET_FAILED", str(exc) or type(exc).__name__) from exc

    return results


def apply_sketch_offset(
    doc: SketchDocument,
    request: SketchOffsetRequest,
    collaborators: SketchOffsetCollaborators,
) -> SketchExecReceipt:
    """Mutate the sketch without recomputing or managing a transaction."""

    sketch = _require_sketch(doc, request.sketch_name)
    before_geo = sketch.GeometryCount
    before_con = sketch.ConstraintCount
    geo_count = sketch.GeometryCount
    for geo_index in request.geo_indices:
        if geo_index < 0 or geo_index >= geo_count:
            raise SketchOffsetError(
                "INVALID_ARGUMENT",
                f"geo_indices contains out-of-range index: {geo_index}",
            )

    part = collaborators.part
    freecad = collaborators.freecad
    try:
        geometries = [sketch.Geometry[geo_index] for geo_index in request.geo_indices]
        new_geos = _offset_geometries(freecad, part, geometries, request.offset)
    except SketchOffsetError:
        raise
    except (TypeError, Exception) as exc:
        raise SketchOffsetError("OFFSET_FAILED", str(exc) or type(exc).__name__) from exc

    if not new_geos:
        raise SketchOffsetError("OFFSET_FAILED", "offset produced no geometry")

    new_indices: list[int] = []
    for geometry in new_geos:
        idx = sketch.addGeometry(geometry, request.construction)
        if int(idx) < 0:
            raise SketchOffsetError("OFFSET_FAILED", "sketch rejected offset geometry")
        new_indices.append(int(idx))

    if not request.copy:
        del_geometry = getattr(sketch, "delGeometry", None)
        if not callable(del_geometry):
            raise SketchOffsetError("OFFSET_FAILED", "sketch does not support deleting geometry")
        for geo_index in sorted(request.geo_indices, reverse=True):
            del_geometry(geo_index)

    solve_fn = getattr(sketch, "solve", None)
    if callable(solve_fn):
        solve_fn()

    return SketchExecReceipt(
        name=sketch.Name,
        sketch=sketch,
        geometry_index=new_indices[0] if new_indices else -1,
        geometry_count_before=before_geo,
        constraint_count_before=before_con,
        sample_count=len(new_indices),
    )

def read_sketch_offset_result(doc: SketchReadDocument, receipt: SketchExecReceipt) -> SketchExecInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchOffsetError("SKETCH_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchOffsetError("SKETCH_REPLACED", f"Sketch was replaced before commit: {receipt.name!r}")
    if not _is_sketch(sketch):
        raise SketchOffsetError("SKETCH_WRONG_TYPE", f"Object is not a sketch: {receipt.name!r}")
    geometry_indices = (
        [receipt.geometry_index]
        if receipt.geometry_index >= 0
        else []
    )
    return SketchExecInspection(
        sketch_name=SketchName(receipt.name),
        geometry_index=receipt.geometry_index,
        geometry_indices=geometry_indices,
        constraint_index=receipt.geometry_index,
        sample_count=receipt.sample_count,
    )


@dataclass(slots=True)
class _SketchOffsetExecution:
    collaborators: SketchOffsetCollaborators
    request: SketchOffsetRequest
    created: SketchExecReceipt | None = None
    inspected: SketchExecInspection | None = None

    def apply(self, doc: SketchDocument) -> None:
        self.created = apply_sketch_offset(doc, self.request, self.collaborators)

    def inspect(self, doc: SketchReadDocument) -> None:
        if self.created is None:
            raise SketchOffsetError(
                "INVALID_SKETCH_OFFSET_RESULT",
                "sketch_offset did not return an identity receipt",
            )
        self.inspected = read_sketch_offset_result(doc, self.created)

    def run(self) -> SketchOffsetResult:
        result = run_sketch_offset_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_offset_uncertain(
                "SKETCH_OFFSET_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sketch_offset result",
                committed=True,
            )
        return make_sketch_offset_success(SketchName(self.inspected.sketch_name))


def run_sketch_offset(
    collaborators: SketchOffsetCollaborators,
    doc_name: object,
    sketch_name: object,
    geo_indices: object,
    offset: object,
    copy: object,
    construction: object,
) -> SketchOffsetResult:
    request = build_sketch_offset_request(
        doc_name, sketch_name, geo_indices, offset, copy, construction
    )
    if isinstance(request, dict):
        return request
    return _SketchOffsetExecution(collaborators, request).run()


class _SketchOffsetRpcFacade(Protocol):
    _cad_collaborators: SketchOffsetCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_offset(
    self: _SketchOffsetRpcFacade,
    doc_name: str,
    sketch_name: str,
    geo_indices: list[int],
    offset: float,
    copy: bool = True,
    construction: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_offset(
            collaborators,
            doc_name,
            sketch_name,
            geo_indices,
            offset,
            copy,
            construction,
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_offset", rpc_sketch_offset)


__all__ = [
    "SketchOffsetCollaborators",
    "SketchOffsetError",
    "apply_sketch_offset",
    "build_sketch_offset_request",
    "read_sketch_offset_result",
    "rpc_sketch_offset",
    "run_sketch_offset",
    "TYPED_RPC_HANDLER",
]
