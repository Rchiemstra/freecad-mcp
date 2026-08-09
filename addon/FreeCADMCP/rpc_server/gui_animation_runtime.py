"""Placement-only collaborators for actor-scoped view animation."""

from __future__ import annotations

_MAX_ANIMATION_FRAMES = 120


def _keyframe_positions(keyframes):
    if len(keyframes) > _MAX_ANIMATION_FRAMES:
        raise ValueError(
            f"placement animation exceeds maximum of {_MAX_ANIMATION_FRAMES} frames"
        )
    positions = []
    for index, sample in enumerate(keyframes):
        if not isinstance(sample, dict):
            raise ValueError("Each keyframe must be a dict with x/y/z")
        positions.append(
            {
                "index": index,
                "x": float(sample["x"]),
                "y": float(sample["y"]),
                "z": float(sample["z"]),
                "yaw_deg": (float(sample["yaw_deg"]) if "yaw_deg" in sample else None),
            }
        )
    return positions


def _path_positions(part_module, document, path_object, sample_count):
    path = document.getObject(path_object)
    if path is None or not hasattr(path, "Shape"):
        raise ValueError(f"Path object {path_object!r} not found")
    edges = list(getattr(path.Shape, "Edges", ()) or ())
    if not edges:
        raise ValueError(f"Path object {path_object!r} has no edges")
    try:
        wire = part_module.Wire(edges)
    except Exception:
        wire = edges[0]
    count = max(2, int(sample_count))
    if count > _MAX_ANIMATION_FRAMES:
        raise ValueError(
            f"placement animation exceeds maximum of {_MAX_ANIMATION_FRAMES} frames"
        )
    try:
        points = list(wire.discretize(Number=count))
    except Exception:
        length = float(getattr(wire, "Length", 0.0) or 0.0)
        points = []
        for index in range(count):
            ratio = 0.0 if count == 1 else index / float(count - 1)
            if hasattr(wire, "valueAt") and length > 0:
                points.append(wire.valueAt(ratio * length))
            else:
                edge = edges[0]
                parameter = edge.FirstParameter + ratio * (
                    edge.LastParameter - edge.FirstParameter
                )
                points.append(edge.valueAt(parameter))
    return [
        {
            "index": index,
            "x": float(point.x),
            "y": float(point.y),
            "z": float(point.z),
            "yaw_deg": None,
        }
        for index, point in enumerate(points)
    ]


def prepare(freecad, part_module, document_name, object_name, **options):
    document = freecad.getDocument(document_name)
    if document is None:
        raise ValueError(f"Document {document_name!r} not found")
    obj = document.getObject(object_name)
    if obj is None or not hasattr(obj, "Placement"):
        raise ValueError(f"Object {object_name!r} not found or has no Placement")
    keyframes = options.get("keyframes")
    path_object = options.get("path_object")
    if keyframes:
        positions = _keyframe_positions(keyframes)
    elif path_object:
        positions = _path_positions(
            part_module, document, path_object, options.get("sample_count", 12)
        )
    else:
        raise ValueError("Provide keyframes or path_object")
    return {
        "document": document,
        "object": obj,
        "original": freecad.Placement(obj.Placement),
        "positions": positions,
        "freecad": freecad,
    }


def apply_sample(plan, sample):
    freecad = plan["freecad"]
    original = plan["original"]
    rotation = original.Rotation
    if sample["yaw_deg"] is not None:
        rotation = freecad.Rotation(freecad.Vector(0, 0, 1), float(sample["yaw_deg"]))
    plan["object"].Placement = freecad.Placement(
        freecad.Vector(sample["x"], sample["y"], sample["z"]), rotation
    )


def restore(plan):
    plan["object"].Placement = plan["original"]
    return True


def repair_placements(freecad, document_name, object_names):
    document = freecad.getDocument(document_name)
    if document is None:
        raise ValueError(f"Document {document_name!r} not found")
    touched = []
    for name in object_names:
        obj = document.getObject(name)
        if obj is None or not hasattr(obj, "Placement"):
            continue
        obj.Placement = obj.Placement
        touched.append(str(name))
    return {"ok": True, "touched": touched}


__all__ = ["apply_sample", "prepare", "repair_placements", "restore"]
