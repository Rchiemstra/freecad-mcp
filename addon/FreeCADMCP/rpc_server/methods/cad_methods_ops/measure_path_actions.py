"""Path sampling helpers for common-volume queries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .measure_io_actions import resolve_global_shape
from .typed_runtime import (
    TypedMutationError,
    load_module,
    module_callable,
    require_object,
)


def _vector(x: float, y: float, z: float = 0.0) -> object:
    freecad = load_module("FreeCAD")
    return module_callable(freecad, "Vector")(x, y, z)


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



__all__ = ["common_volume_along_path"]
