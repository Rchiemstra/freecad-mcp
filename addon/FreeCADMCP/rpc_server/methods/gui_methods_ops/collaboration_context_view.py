"""Canonical schema and camera transforms for actor-scoped contexts."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from typing import Any

from .collaboration_context_core import (
    _document_name,
    _member,
    activate_personal_target,
    collaborators,
    request_actor,
    resolve_document,
)
from .collaboration_context_dispatch import dispatch_gui

_ORIENTATION = re.compile(
    r"(orientation\s+)([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+"
    r"([-+0-9.eE]+)\s+([-+0-9.eE]+)"
)
_POSITION = re.compile(r"(position\s+)([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)")
_FOCAL_DISTANCE = re.compile(r"(focalDistance\s+)([-+0-9.eE]+)")
_HEIGHT = re.compile(r"(height\s+)([-+0-9.eE]+)")
_HEIGHT_ANGLE = re.compile(r"heightAngle\s+([-+0-9.eE]+)")
_NEAR_DISTANCE = re.compile(r"(nearDistance\s+)([-+0-9.eE]+)")
_FAR_DISTANCE = re.compile(r"(farDistance\s+)([-+0-9.eE]+)")
_NAMED_VIEW_QUATERNIONS = {
    "top": (0.0, 0.0, 0.0, 1.0),
    "bottom": (1.0, 0.0, 0.0, 0.0),
    "front": (math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)),
    "back": (0.0, math.sqrt(0.5), math.sqrt(0.5), 0.0),
    "right": (0.5, 0.5, 0.5, 0.5),
    "left": (-0.5, 0.5, 0.5, -0.5),
    "isometric": (0.424708, 0.17592, 0.339851, 0.820473),
    "axonometric": (0.424708, 0.17592, 0.339851, 0.820473),
    "dimetric": (0.567952, 0.103751, 0.146726, 0.803205),
    "trimetric": (0.446015, 0.119509, 0.229575, 0.856787),
}
_NAMED_VIEW_ALIASES = {
    "rear": "back",
    "side": "right",
    "sideright": "right",
    "sideleft": "left",
}


def normalize_focus_paths(
    document: Any,
    focus_object: str | None,
    focus_objects: Any,
) -> list[str]:
    raw = []
    if focus_objects:
        raw.extend(focus_objects)
    if focus_object:
        raw.extend(part.strip() for part in str(focus_object).split(","))
    paths: list[str] = []
    for item in raw:
        path = str(item or "").strip()
        if not path:
            continue
        object_name = path.split(".", 1)[0]
        obj = document.getObject(object_name)
        if obj is None:
            raise ValueError("focus object is not present in the selected document")
        if "." in path and not path.split(".", 1)[1]:
            raise ValueError("focus selection path is incomplete")
        subname = path.partition(".")[2]
        get_subobject = getattr(obj, "getSubObject", None)
        if subname and callable(get_subobject) and get_subobject(subname) is None:
            raise ValueError("focus subshape is not present in the selected document")
        if path not in paths:
            paths.append(path)
    return paths


def _normalize_overlays(source: Mapping[str, Any]) -> list[dict[str, str]]:
    overlays = source.get("temporary_overlays", [])
    if not isinstance(overlays, (list, tuple)):
        raise TypeError("personal view field temporary_overlays must be a list")
    normalized = []
    for overlay in overlays:
        fields = ("identifier", "kind", "payload")
        if not isinstance(overlay, Mapping) or any(
            not isinstance(overlay.get(field), str) for field in fields
        ):
            raise TypeError(
                "personal view overlays require string identifier, kind, and payload"
            )
        normalized.append({field: overlay[field] for field in fields})
    return normalized


def _native_context_schema(
    source: Mapping[str, Any],
    document_name: str,
) -> dict[str, Any]:
    def string(name: str, default: str = "") -> str:
        value = source.get(name, default)
        if not isinstance(value, str):
            raise TypeError(f"personal view field {name} must be a string")
        return value

    def strings(name: str) -> list[str]:
        value = source.get(name, [])
        if not isinstance(value, (list, tuple)) or not all(
            isinstance(item, str) for item in value
        ):
            raise TypeError(f"personal view field {name} must be a string list")
        return list(value)

    def integer(name: str) -> int:
        value = source.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"personal view field {name} must be an integer")
        return value

    preselection = source.get("preselection_path")
    if preselection is not None and not isinstance(preselection, str):
        raise TypeError(
            "personal view field preselection_path must be a string or None"
        )
    return {
        "camera": string("camera"),
        "projection": string("projection"),
        "selection_paths": strings("selection_paths"),
        "preselection_path": preselection,
        "expanded_tree_paths": strings("expanded_tree_paths"),
        "tree_horizontal_scroll": integer("tree_horizontal_scroll"),
        "tree_vertical_scroll": integer("tree_vertical_scroll"),
        "active_document": document_name,
        "active_view": string("active_view"),
        "active_workbench": string("active_workbench"),
        "edit_focus": string("edit_focus"),
        "temporary_overlays": _normalize_overlays(source),
    }


def _replace_camera_orientation(
    camera: str,
    orientation: tuple[float, float, float, float],
) -> str:
    if not camera:
        return camera
    replacement = " ".join(f"{value:.10g}" for value in orientation)
    updated, count = _ORIENTATION.subn(
        lambda match: match.group(1) + replacement,
        camera,
        count=1,
    )
    if count != 1:
        raise ValueError("serialized camera has no transformable orientation")
    return updated


def _camera_for_named_view(camera: str, view_name: str) -> str:
    name = view_name.strip().lower()
    name = _NAMED_VIEW_ALIASES.get(name, name)
    quaternion = _NAMED_VIEW_QUATERNIONS.get(name)
    if quaternion is None:
        raise ValueError("unsupported named personal view")
    return _replace_camera_orientation(
        camera,
        _quaternion_to_axis_angle(quaternion),
    )


def _camera_with_yaw(camera: str, yaw_deg: float) -> str:
    if not math.isfinite(yaw_deg):
        raise ValueError("yaw must be finite")
    if not camera or yaw_deg == 0:
        return camera
    match = _ORIENTATION.search(camera)
    if match is None:
        raise ValueError("serialized camera has no transformable orientation")
    orientation = tuple(float(match.group(index)) for index in range(2, 6))
    x, y, z, w = _axis_angle_to_quaternion(orientation)
    half_angle = math.radians(yaw_deg) / 2.0
    sine, cosine = math.sin(half_angle), math.cos(half_angle)
    return _replace_camera_orientation(
        camera,
        _quaternion_to_axis_angle(
            (
                cosine * x - sine * y,
                sine * x + cosine * y,
                cosine * z + sine * w,
                cosine * w - sine * z,
            )
        ),
    )


def _axis_angle_to_quaternion(
    orientation: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    axis_x, axis_y, axis_z, angle = orientation
    length = math.sqrt(axis_x * axis_x + axis_y * axis_y + axis_z * axis_z)
    if length == 0:
        return (0.0, 0.0, 0.0, 1.0)
    sine = math.sin(angle / 2.0) / length
    return (
        axis_x * sine,
        axis_y * sine,
        axis_z * sine,
        math.cos(angle / 2.0),
    )


def _quaternion_to_axis_angle(
    quaternion: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    x, y, z, w = quaternion
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length == 0:
        raise ValueError("camera orientation has zero length")
    x, y, z, w = x / length, y / length, z / length, w / length
    vector_length = math.sqrt(x * x + y * y + z * z)
    if vector_length < 1e-12:
        return (0.0, 0.0, 1.0, 0.0)
    return (
        x / vector_length,
        y / vector_length,
        z / vector_length,
        2.0 * math.atan2(vector_length, w),
    )


def _rotate_vector(
    quaternion: tuple[float, float, float, float],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    qx, qy, qz, qw = quaternion
    vx, vy, vz = vector
    dot = qx * vx + qy * vy + qz * vz
    cross = (qy * vz - qz * vy, qz * vx - qx * vz, qx * vy - qy * vx)
    scale = qw * qw - (qx * qx + qy * qy + qz * qz)
    return (
        scale * vx + 2.0 * dot * qx + 2.0 * qw * cross[0],
        scale * vy + 2.0 * dot * qy + 2.0 * qw * cross[1],
        scale * vz + 2.0 * dot * qz + 2.0 * qw * cross[2],
    )


def _camera_vectors(camera: str) -> tuple[tuple[float, float, float], ...]:
    match = _ORIENTATION.search(camera)
    if match is None:
        raise ValueError("serialized camera has no transformable orientation")
    orientation = tuple(float(match.group(index)) for index in range(2, 6))
    quaternion = _axis_angle_to_quaternion(orientation)
    return (
        _rotate_vector(quaternion, (1.0, 0.0, 0.0)),
        _rotate_vector(quaternion, (0.0, 1.0, 0.0)),
        _rotate_vector(quaternion, (0.0, 0.0, -1.0)),
    )


def _bound_box(value: Any) -> Any:
    bound = getattr(value, "BoundBox", None)
    if bound is None:
        return None
    valid = getattr(bound, "isValid", None)
    if callable(valid) and not valid():
        return None
    try:
        for name in ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax"):
            float(getattr(bound, name))
    except (AttributeError, TypeError, ValueError):
        return None
    return bound


def _candidate_bounds(candidate: Any, seen: set[int]) -> list[Any]:
    if candidate is None or id(candidate) in seen:
        return []
    seen.add(id(candidate))
    bounds = [
        bound
        for value in (
            candidate,
            getattr(candidate, "Shape", None),
            getattr(candidate, "Mesh", None),
        )
        if (bound := _bound_box(value)) is not None
    ]
    children = []
    for name in ("Group", "Objects", "OutList"):
        value = getattr(candidate, name, None)
        if isinstance(value, (list, tuple, set)):
            children.extend(value)
    for child in children:
        bounds.extend(_candidate_bounds(child, seen))
    return bounds


def _bounds_for_paths(document: Any, paths: list[str], fit_all: bool) -> list[Any]:
    candidates = []
    if paths:
        for path in paths:
            object_name, _, subname = path.partition(".")
            obj = document.getObject(object_name)
            target = obj
            if subname and callable(getattr(obj, "getSubObject", None)):
                target = obj.getSubObject(subname)
            candidates.append(target)
    elif fit_all:
        candidates.extend(getattr(document, "Objects", ()) or ())
    bounds = []
    seen: set[int] = set()
    for candidate in candidates:
        bounds.extend(_candidate_bounds(candidate, seen))
    return bounds


def _replace_or_insert_camera_scalar(
    camera: str, pattern: re.Pattern[str], name: str, value: float
) -> str:
    replacement = f"{value:.10g}"
    updated, count = pattern.subn(
        lambda match: match.group(1) + replacement, camera, count=1
    )
    if count:
        return updated
    index = camera.rfind("}")
    if index < 0:
        raise ValueError("serialized camera has no transformable framing fields")
    return f"{camera[:index].rstrip()} {name} {replacement} {camera[index:]}"


def _fit_personal_camera(
    document: Any,
    camera: str,
    paths: list[str],
    fit_all: bool,
    width: int | None = None,
    height: int | None = None,
) -> str:
    bounds = _bounds_for_paths(document, paths, fit_all)
    if not bounds:
        raise ValueError("personal view focus has no renderable bounds")
    minimum = (
        min(float(bound.XMin) for bound in bounds),
        min(float(bound.YMin) for bound in bounds),
        min(float(bound.ZMin) for bound in bounds),
    )
    maximum = (
        max(float(bound.XMax) for bound in bounds),
        max(float(bound.YMax) for bound in bounds),
        max(float(bound.ZMax) for bound in bounds),
    )
    center = tuple(
        (low + high) / 2.0 for low, high in zip(minimum, maximum, strict=True)
    )
    corners = [
        (x, y, z)
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    ]
    right, up, forward = _camera_vectors(camera)

    def half_extent(axis):
        return max(
            abs(
                (corner[0] - center[0]) * axis[0]
                + (corner[1] - center[1]) * axis[1]
                + (corner[2] - center[2]) * axis[2]
            )
            for corner in corners
        )

    half_width = max(half_extent(right), 0.5)
    half_height = max(half_extent(up), 0.5)
    half_depth = max(half_extent(forward), 0.5)
    if width is not None and height is not None and int(width) > 0 and int(height) > 0:
        aspect_ratio = float(width) / float(height)
    else:
        aspect_ratio = 1.0
    vertical_span = max(half_height, half_width / aspect_ratio)
    margin = 1.2
    if "PerspectiveCamera" in camera:
        angle_match = _HEIGHT_ANGLE.search(camera)
        angle = float(angle_match.group(1)) if angle_match else math.radians(45.0)
        distance = vertical_span * margin / max(math.tan(angle / 2.0), 1e-6)
        distance += half_depth
    else:
        distance = max(vertical_span * 2.5, half_depth * 2.5, 1.0)
        camera, height_count = _HEIGHT.subn(
            lambda match: match.group(1) + f"{2.0 * margin * vertical_span:.10g}",
            camera,
            count=1,
        )
        if height_count != 1:
            raise ValueError("orthographic camera has no transformable height")
    position = tuple(center[index] - forward[index] * distance for index in range(3))
    camera, position_count = _POSITION.subn(
        lambda match: match.group(1) + " ".join(f"{value:.10g}" for value in position),
        camera,
        count=1,
    )
    camera, focal_count = _FOCAL_DISTANCE.subn(
        lambda match: match.group(1) + f"{distance:.10g}", camera, count=1
    )
    if position_count != 1 or focal_count != 1:
        raise ValueError("serialized camera has no transformable framing fields")
    near_distance = max(0.001, distance - (half_depth * margin))
    far_distance = max(near_distance + 0.001, distance + (half_depth * margin))
    camera = _replace_or_insert_camera_scalar(
        camera, _NEAR_DISTANCE, "nearDistance", near_distance
    )
    return _replace_or_insert_camera_scalar(
        camera, _FAR_DISTANCE, "farDistance", far_distance
    )


def build_view_context(
    facade: Any,
    document: Any,
    actor: str,
    *,
    view_name: str | None = None,
    focus_object: str | None = None,
    focus_objects: Any = None,
    yaw_deg: float | None = None,
    fit: bool | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    collabs = collaborators(facade)
    document_name = _document_name(document)
    baseline = _member(collabs, "snapshot_view_context")(document_name)
    if baseline is not None and not isinstance(baseline, Mapping):
        raise TypeError("native view baseline must be a mapping")
    remembered = _member(collabs, "snapshot_personal_view_context")(
        document_name, actor
    )
    if remembered is not None and not isinstance(remembered, Mapping):
        raise TypeError("stored personal view context must be a mapping")
    source = dict(baseline or {})
    source.update(remembered or {})
    context = _native_context_schema(source, document_name)
    registry = _member(collabs, "personal_view_registry")
    registry.remember(
        actor,
        document_name,
        {"active_body": str((baseline or {}).get("active_body") or "")},
    )
    paths = normalize_focus_paths(document, focus_object, focus_objects)
    if paths:
        context["selection_paths"] = paths
    if view_name:
        context["camera"] = _camera_for_named_view(context["camera"], str(view_name))
    if yaw_deg is not None:
        context["camera"] = _camera_with_yaw(context["camera"], float(yaw_deg))
    if paths or fit:
        fit_width = width if width is not None else baseline.get("viewport_width")
        fit_height = height if height is not None else baseline.get("viewport_height")
        context["camera"] = _fit_personal_camera(
            document,
            context["camera"],
            paths,
            bool(fit),
            fit_width,
            fit_height,
        )
    return context


def update_personal_view(
    facade: Any,
    hint: Any,
    updater: Callable[[Any, dict[str, Any]], Any],
) -> tuple[Any, dict[str, Any], Any]:
    actor = request_actor(facade)

    def update() -> tuple[Any, dict[str, Any], Any]:
        document = resolve_document(facade, actor, hint)
        context = build_view_context(facade, document, actor)
        result = updater(document, context)
        _member(collaborators(facade), "store_personal_view_context")(
            _document_name(document), actor, context
        )
        activate_personal_target(facade, actor, document)
        return document, context, result

    return dispatch_gui(facade, update)


def snapshot_personal_view(
    facade: Any,
    hint: Any = None,
) -> tuple[Any, dict[str, Any]]:
    actor = request_actor(facade)

    def snapshot() -> tuple[Any, dict[str, Any]]:
        document = resolve_document(facade, actor, hint)
        context = build_view_context(facade, document, actor)
        _member(collaborators(facade), "store_personal_view_context")(
            _document_name(document), actor, context
        )
        activate_personal_target(facade, actor, document)
        return document, context

    return dispatch_gui(facade, snapshot)


__all__ = [
    "_camera_for_named_view",
    "_camera_with_yaw",
    "build_view_context",
    "snapshot_personal_view",
    "update_personal_view",
]
