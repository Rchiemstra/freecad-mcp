"""Stable document model-state oracle for native qualification tests."""

from __future__ import annotations

# Object.State flags that are execution bookkeeping, not durable model content.
_TRANSIENT_STATE_FLAGS = frozenset({"Touched"})

# Unnamed locker bits that flap on rollback (e.g. Body.Group User3); keep schema flags.
_TRANSIENT_PROPERTY_STATUS_BITS = frozenset({15, 18, 29, 30, 31})


def _round_float(value: float) -> float:
    return round(value, 9)


def _object_name(obj: object) -> str | None:
    if obj is None:
        return None
    try:
        name = getattr(obj, "Name", None)
    except ReferenceError:
        return None
    return str(name) if name else None


def _expression_engine_fingerprint(item: object, name: str) -> tuple[tuple[str, str], ...] | None:
    engine = getattr(item, name, None)
    if not engine:
        return None
    bindings: list[tuple[str, str]] = []
    for entry in engine:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            bindings.append((str(entry[0]), str(entry[1])))
        else:
            bindings.append((str(entry), ""))
    if not bindings:
        return None
    return tuple(sorted(bindings))


def _vector_fingerprint(vec: object) -> tuple[float, float, float]:
    return (
        _round_float(float(vec.x)),
        _round_float(float(vec.y)),
        _round_float(float(vec.z)),
    )


def _rotation_fingerprint(rot: object) -> tuple[float, ...]:
    quat = getattr(rot, "Q", rot)
    try:
        return tuple(_round_float(float(quat[index])) for index in range(4))
    except (AttributeError, IndexError, TypeError, ValueError):
        return (str(rot),)


def _placement_fingerprint(pl: object) -> tuple[object, ...]:
    return (_vector_fingerprint(pl.Base), _rotation_fingerprint(pl.Rotation))


def _quantity_fingerprint(value: object) -> tuple[float, str]:
    return (_round_float(float(value)), str(value.Unit))


def _shape_fingerprint(shape: object) -> tuple[object, ...]:
    if shape is None:
        return ("empty",)
    is_null = getattr(shape, "isNull", None)
    if callable(is_null) and is_null():
        return ("empty",)
    volume = _round_float(float(shape.Volume))
    bbox = shape.BoundBox
    bounds = (
        _round_float(float(bbox.XMin)),
        _round_float(float(bbox.XMax)),
        _round_float(float(bbox.YMin)),
        _round_float(float(bbox.YMax)),
        _round_float(float(bbox.ZMin)),
        _round_float(float(bbox.ZMax)),
    )
    return (
        "shape",
        volume,
        bounds,
        len(shape.Faces),
        len(shape.Edges),
        len(shape.Vertexes),
    )


def _link_fingerprint(value: object, type_id: str) -> object | None:
    if value is None:
        return None
    if "LinkSubList" in type_id:
        entries: list[tuple[str | None, tuple[str, ...]]] = []
        for item in value:
            if isinstance(item, tuple) and len(item) >= 2:
                subs = item[1]
                entries.append(
                    (
                        _object_name(item[0]),
                        tuple(str(part) for part in subs) if subs else (),
                    )
                )
            else:
                entries.append((_object_name(item), ()))
        return tuple(sorted(entries, key=lambda entry: entry[0] or ""))
    if "LinkList" in type_id:
        return tuple(sorted(_object_name(item) or "" for item in value))
    if "LinkSub" in type_id:
        if isinstance(value, tuple) and len(value) >= 2:
            subs = value[1]
            return (
                _object_name(value[0]),
                tuple(str(part) for part in subs) if subs else (),
            )
        return (_object_name(value), ())
    if isinstance(value, tuple) and value:
        return _object_name(value[0])
    return _object_name(value)


def _fem_mesh_fingerprint(mesh: object) -> object:
    if mesh is None:
        return ("empty_mesh",)
    counts = []
    for attr in ("NodeCount", "EdgeCount", "FaceCount", "TriangleCount", "VolumeCount"):
        raw = getattr(mesh, attr, None)
        try:
            counts.append(int(raw))
        except (TypeError, ValueError):
            counts.append(None)
    if all(count is None for count in counts):
        return ("femmesh", type(mesh).__name__)
    return ("femmesh", tuple(counts))


def _material_fingerprint(value: object) -> object:
    if value is None:
        return None
    uuid = getattr(value, "UUID", None)
    if uuid:
        return ("material", str(uuid))
    name = getattr(value, "Name", None)
    if name:
        return ("material", str(name))
    label = getattr(value, "Label", None)
    if label:
        return ("material", str(label))
    return ("material", type(value).__name__)


def _scalar_fingerprint(value: object, type_id: str) -> object:
    if "Quantity" in type_id:
        return _quantity_fingerprint(value)
    if "Enumeration" in type_id:
        return str(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _round_float(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return repr(value)


def _property_type_id(item: object, name: str) -> str:
    getter = getattr(item, "getTypeIdOfProperty", None)
    if not callable(getter):
        return ""
    try:
        return str(getter(name))
    except Exception:
        return ""


def property_content(item: object, name: str) -> object | None:
    if name == "Proxy":
        proxy = getattr(item, "Proxy", None)
        if proxy is None:
            return None
        return f"{type(proxy).__module__}.{type(proxy).__qualname__}"
    if name == "ExpressionEngine":
        return _expression_engine_fingerprint(item, name)

    type_id = _property_type_id(item, name)
    try:
        value = getattr(item, name)
    except Exception:
        return None

    if name in {"Shape", "InternalShape"} or "PropertyPartShape" in type_id or "PropertyComplexGeoData" in type_id:
        try:
            return _shape_fingerprint(value)
        except Exception:
            return ("empty",)
    if "ElementMap" in name:
        size = getattr(item, "ElementMapSize", None)
        if size is None and value is not None:
            size = getattr(value, "ElementMapSize", None)
        return ("element_map", int(size)) if size is not None else None
    if name in {"AttacherEngine", "AttachmentOffset"}:
        if isinstance(value, str):
            return value
        if "Placement" in type_id or name == "AttachmentOffset":
            try:
                return _placement_fingerprint(value)
            except Exception:
                pass
        if "Link" in type_id:
            return _link_fingerprint(value, type_id)
    if "PropertyPlacement" in type_id or name == "Placement":
        try:
            return _placement_fingerprint(value)
        except Exception:
            pass
    if "PropertyRotation" in type_id:
        try:
            return _rotation_fingerprint(value)
        except Exception:
            pass
    if "PropertyVector" in type_id:
        try:
            return _vector_fingerprint(value)
        except Exception:
            pass
    if "Link" in type_id:
        return _link_fingerprint(value, type_id)
    if "PropertyMaterial" in type_id or name == "ShapeMaterial":
        return _material_fingerprint(value)
    if "FemMesh" in type_id or name == "FemMesh":
        try:
            return _fem_mesh_fingerprint(value)
        except Exception:
            return ("empty_mesh",)
    if any(token in type_id for token in ("Float", "Integer", "Bool", "String", "Enumeration", "Quantity")):
        return _scalar_fingerprint(value, type_id)
    if isinstance(value, (bool, int, float, str)):
        return value if not isinstance(value, float) else _round_float(value)
    if value is None:
        return None
    return repr(value)


def _stable_state(item: object) -> tuple[str, ...]:
    state = getattr(item, "State", ())
    if not isinstance(state, (list, tuple)):
        return ()
    return tuple(sorted(str(flag) for flag in state if str(flag) not in _TRANSIENT_STATE_FLAGS))


def _stable_property_status(item: object, name: str) -> tuple:
    status = tuple(item.getPropertyStatus(name))
    filtered: list[object] = []
    for flag in status:
        if isinstance(flag, int) and flag in _TRANSIENT_PROPERTY_STATUS_BITS:
            continue
        filtered.append(flag)
    return tuple(filtered)


def model_state(document: object) -> tuple:
    objects = getattr(document, "Objects", ())
    return tuple(
        (
            item.Name,
            item.TypeId,
            _stable_state(item),
            tuple(sorted(obj.Name for obj in item.InList)),
            tuple(sorted(obj.Name for obj in item.OutList)),
            tuple(
                (
                    name,
                    item.getTypeIdOfProperty(name),
                    item.getGroupOfProperty(name),
                    _stable_property_status(item, name),
                    property_content(item, name),
                )
                for name in sorted(item.PropertiesList)
            ),
        )
        for item in objects
    )


_REVISION_PROBE_SUBJECTS = frozenset(
    {
        "RejectedBody",
        "RejectedFeature",
        "TransientSupport",
        "NativeSketch",
        "NativePad",
        "NativePocket",
    }
)


def settle_stable_read_boundary(document: object) -> None:
    """Make snapshotForEdit legal after a rollback that left mustExecute set."""

    must_execute = getattr(document, "mustExecute", None)
    if not callable(must_execute) or not must_execute():
        return
    purge = getattr(document, "purgeTouched", None)
    if callable(purge):
        purge()
    if callable(must_execute) and must_execute():
        recompute = getattr(document, "recompute", None)
        if callable(recompute):
            recompute()


def revision_state(document: object, op: str = "native-state") -> object:
    settle_stable_read_boundary(document)
    keys = [{"kind": "UnknownModelMutation"}, {"kind": "DocumentStructure"}]
    names = {item.Name for item in document.Objects} | _REVISION_PROBE_SUBJECTS
    for name in sorted(names):
        keys.extend(
            {"kind": kind, "subject": name} for kind in ("ObjectExistence", "ObjectStructure")
        )
        item = document.getObject(name)
        if item is not None:
            keys.extend(
                {"kind": "ObjectProperty", "subject": name, "property_name": prop}
                for prop in sorted(item.PropertiesList)
            )
    session = document.beginEditSession(f"{op}-native-state-probe")
    try:
        snapshot = document.snapshotForEdit(session["session_id"], keys)
        return snapshot["revisions"]
    finally:
        document.cancelEdit(session["session_id"])


__all__ = [
    "model_state",
    "property_content",
    "revision_state",
    "settle_stable_read_boundary",
]
