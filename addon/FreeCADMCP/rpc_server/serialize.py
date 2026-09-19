import contextlib

import FreeCAD as App

try:
    from .placement_codec import placement_to_dict, rotation_to_dict, vector_to_dict
except ImportError:  # pragma: no cover - flat addon import path
    from placement_codec import placement_to_dict, rotation_to_dict, vector_to_dict


def _get_optional_app_type(name: str) -> type | tuple[type, ...] | None:
    value = getattr(App, name, None)
    if isinstance(value, type):
        return value
    if isinstance(value, tuple) and all(isinstance(item, type) for item in value):
        return value
    return None


_COLOR_TYPE = _get_optional_app_type("Color")


def serialize_value(value):
    if isinstance(value, (int, float, str, bool)):
        return value
    elif isinstance(value, App.Vector):
        return vector_to_dict(value)
    elif isinstance(value, App.Rotation):
        # Public contract: Angle is degrees (FreeCAD's .Angle is radians).
        return rotation_to_dict(value)
    elif isinstance(value, App.Placement):
        return placement_to_dict(value)
    elif isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    elif _COLOR_TYPE is not None and isinstance(value, _COLOR_TYPE):
        return tuple(value)
    else:
        return str(value)


def serialize_shape(shape):
    if shape is None:
        return None
    try:
        return {
            "Volume": shape.Volume,
            "Area": shape.Area,
            "VertexCount": len(shape.Vertexes),
            "EdgeCount": len(shape.Edges),
            "FaceCount": len(shape.Faces),
        }
    except Exception as e:
        return {"error": f"Invalid shape: {e}"}


def serialize_view_object(view):
    if view is None:
        return None
    result = {}
    for attr in ("ShapeColor", "Transparency", "Visibility"):
        with contextlib.suppress(Exception):
            value = getattr(view, attr)
            if attr == "ShapeColor" and isinstance(value, (list, tuple)):
                result[attr] = [serialize_value(item) for item in value]
            else:
                result[attr] = serialize_value(value)
    return result


def _serialize_property_value(obj, prop: str):
    if prop == "Shape":
        return serialize_shape(getattr(obj, prop, None))
    if prop == "ViewObject":
        return serialize_view_object(getattr(obj, prop, None))
    return serialize_value(getattr(obj, prop))


def project_listing_object(
    obj,
    *,
    fields: tuple[str, ...],
    include_properties: tuple[str, ...] | None,
    include_shape: bool,
    include_view: bool,
) -> dict[str, object]:
    row: dict[str, object] = {}
    for field in fields:
        if field == "Placement":
            row[field] = serialize_value(getattr(obj, "Placement", None))
        else:
            row[field] = getattr(obj, field, None)
    if include_shape:
        row["Shape"] = serialize_shape(getattr(obj, "Shape", None))
    if include_view:
        row["ViewObject"] = serialize_view_object(getattr(obj, "ViewObject", None))
    if include_properties:
        properties: dict[str, object] = {}
        for prop in include_properties:
            try:
                properties[prop] = _serialize_property_value(obj, prop)
            except Exception as exc:
                properties[prop] = f"<error: {exc!s}>"
        row["Properties"] = properties
    return row


def serialize_object(obj):
    if isinstance(obj, list):
        return [serialize_object(item) for item in obj]
    elif isinstance(obj, App.Document):
        return {
            "Name": obj.Name,
            "Label": obj.Label,
            "FileName": obj.FileName,
            "Objects": [serialize_object(child) for child in obj.Objects],
        }
    else:
        result = {
            "Name": obj.Name,
            "Label": obj.Label,
            "TypeId": obj.TypeId,
            "Properties": {},
            "Placement": serialize_value(getattr(obj, "Placement", None)),
            "Shape": serialize_shape(getattr(obj, "Shape", None)),
            "ViewObject": {},
        }

        for prop in obj.PropertiesList:
            try:
                result["Properties"][prop] = _serialize_property_value(obj, prop)
            except Exception as e:
                result["Properties"][prop] = f"<error: {e!s}>"

        try:
            if hasattr(obj, "ViewObject") and obj.ViewObject is not None:
                result["ViewObject"] = serialize_view_object(obj.ViewObject)
        except Exception as exc:
            result["ViewObject"] = {"error": f"ViewObject unavailable: {exc!s}"}

        return result
