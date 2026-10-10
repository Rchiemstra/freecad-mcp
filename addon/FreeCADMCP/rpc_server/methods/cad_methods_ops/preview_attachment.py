
"""Typed ``preview_attachment`` mutation."""
from __future__ import annotations

from .native_commit_wait import NativeOutcome, settle_native_commit

from .typed_rpc_support import (
    nonempty_string,
    object_label,
    object_name,
    require_object,
)

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, cast

try:
    from ...._shared.protocol.preview_attachment_contract import (
        PreviewAttachmentCollaborators,
        PreviewAttachmentDocument,
        PreviewAttachmentFailure,
        PreviewAttachmentName,
        PreviewAttachmentReadDocument,
        PreviewAttachmentRequest,
        PreviewAttachmentResult,
        PreviewAttachmentUncertain,
        DocumentName,
        make_preview_attachment_failure,
        make_preview_attachment_success,
        make_preview_attachment_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.preview_attachment_contract import (
        PreviewAttachmentCollaborators,
        PreviewAttachmentDocument,
        PreviewAttachmentFailure,
        PreviewAttachmentName,
        PreviewAttachmentReadDocument,
        PreviewAttachmentRequest,
        PreviewAttachmentResult,
        PreviewAttachmentUncertain,
        DocumentName,
        make_preview_attachment_failure,
        make_preview_attachment_success,
        make_preview_attachment_uncertain,
    )
from .preview_attachment_mutation import PreviewAttachmentError, run_preview_attachment_native_mutation



@dataclass(frozen=True, slots=True)
class PreviewAttachmentReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class PreviewAttachmentInspection:
    """Read-only data captured after the native-owned recompute."""

    name: PreviewAttachmentName
    label: str
    extra: object = None


def _failure(error: PreviewAttachmentError, *, retry_safe: bool = True) -> PreviewAttachmentFailure:
    return make_preview_attachment_failure(error.code, str(error), retry_safe=retry_safe)


def _support_object_name(item: object) -> str:
    name = object_name(item)
    if name:
        return name
    if isinstance(item, str) and item.strip():
        return item
    return ""


def _is_element_name(text: str) -> bool:
    for prefix in ("Face", "Edge", "Vertex"):
        if not text.startswith(prefix):
            continue
        rest = text[len(prefix):]
        if rest.isdigit():
            return True
    return False


def _unwrap_printed_element(text: str) -> str:
    """Turn a stringified one-element tuple such as ``('Face6',)`` into ``Face6``."""

    if _is_element_name(text):
        return text
    if len(text) < 2 or text[0] not in "([{" or text[-1] not in ")]}":
        return text
    inner = text[1:-1].strip().strip("'\"").rstrip(",").strip().strip("'\"")
    if _is_element_name(inner):
        return inner
    return text


def _collect_element_names(raw: object) -> list[str]:
    if isinstance(raw, (list, tuple)):
        names: list[str] = []
        for item in raw:
            names.extend(_collect_element_names(item))
        return names
    if isinstance(raw, str):
        text = _unwrap_printed_element(raw.strip())
        return [text] if text else []
    return []


def _subelement_name(raw: object) -> str:
    names = _collect_element_names(raw)
    if len(names) == 1:
        return names[0]
    if len(names) > 1:
        return ",".join(names)
    if isinstance(raw, str):
        return _unwrap_printed_element(raw.strip())
    return ""


def _support_entries(datum: object) -> list[dict[str, object]]:
    support = getattr(datum, "AttachmentSupport", None)
    if support is None:
        support = getattr(datum, "Support", None)
    if support is None:
        return []
    try:
        values = list(getattr(support, "getValues", lambda: support)() or [])
    except Exception:
        values = list(support) if isinstance(support, Sequence) and not isinstance(support, (str, bytes)) else []
    entries: list[dict[str, object]] = []
    for item in values:
        if item is None:
            continue
        if isinstance(item, (list, tuple)) and item:
            obj = item[0]
            sub = item[1] if len(item) > 1 else ""
            entries.append(
                {"object": _support_object_name(obj), "sub": _subelement_name(sub), "item": obj}
            )
        else:
            entries.append({"object": _support_object_name(item), "sub": "", "item": item})
    return entries


def _vector_dict(value: object) -> dict[str, float] | None:
    if value is None:
        return None
    for axis in ("x", "y", "z"):
        if not hasattr(value, axis):
            return None
    try:
        return {
            "x": round(float(getattr(value, "x")), 6),
            "y": round(float(getattr(value, "y")), 6),
            "z": round(float(getattr(value, "z")), 6),
        }
    except Exception:
        return None


def _placement_dict(placement: object) -> dict[str, object] | None:
    if placement is None:
        return None
    base = _vector_dict(getattr(placement, "Base", None))
    rotation = getattr(placement, "Rotation", None)
    axis = _vector_dict(getattr(rotation, "Axis", None)) if rotation is not None else None
    angle = getattr(rotation, "Angle", None) if rotation is not None else None
    angle_deg = None
    if isinstance(angle, (int, float)) and not isinstance(angle, bool):
        angle_deg = round(float(angle) * (180.0 / math.pi), 6)
    return {"base": base, "axis": axis, "angle_deg": angle_deg}


def _is_body(candidate: object) -> bool:
    derived = getattr(candidate, "isDerivedFrom", None)
    if callable(derived):
        try:
            if bool(derived("PartDesign::Body")):
                return True
        except Exception:
            pass
    return str(getattr(candidate, "TypeId", "") or "") == "PartDesign::Body"


def _owning_body(obj: object) -> object | None:
    getter = getattr(obj, "getParentGeoFeatureGroup", None)
    if callable(getter):
        try:
            owner: object | None = getter()
        except Exception:
            owner = None
        if owner is not None and _is_body(owner):
            located: object = owner
            return located
        if owner is not None:
            nested = _owning_body(owner)
            if nested is not None:
                return nested
    for candidate in getattr(obj, "InList", ()) or ():
        if not _is_body(candidate):
            continue
        located_candidate: object = candidate
        return located_candidate
    return None


def _placement_is_identity(placement: object) -> bool:
    base = getattr(placement, "Base", None)
    if base is None:
        return True
    try:
        length = float(getattr(base, "Length", 0.0))
    except Exception:
        try:
            length = (
                abs(float(base.x)) + abs(float(base.y)) + abs(float(base.z))
            )
        except Exception:
            return True
    if length > 1.0e-9:
        return False
    rotation = getattr(placement, "Rotation", None)
    angle = getattr(rotation, "Angle", 0.0) if rotation is not None else 0.0
    try:
        return abs(float(angle)) <= 1.0e-9
    except Exception:
        return True


class _Vector:
    """Stand-in when FreeCAD.Vector cannot be imported (unit-test fakes)."""

    def __init__(self, x: float, y: float, z: float) -> None:
        self.x = x
        self.y = y
        self.z = z


def _components(value: object) -> tuple[float, float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return (float(value[0]), float(value[1]), float(value[2]))
        except (TypeError, ValueError):
            return None
    if value is None:
        return None
    try:
        coords = [float(getattr(value, axis)) for axis in ("x", "y", "z")]
    except (AttributeError, TypeError, ValueError):
        return None
    return (coords[0], coords[1], coords[2])


def _dot(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float] | None:
    length = math.sqrt(_dot(vector, vector))
    if length <= 1.0e-12:
        return None
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _point_dict(point: tuple[float, float, float]) -> dict[str, float]:
    return {"x": round(point[0], 6), "y": round(point[1], 6), "z": round(point[2], 6)}


def _make_vector(x: float, y: float, z: float) -> object:
    try:
        from .typed_runtime import load_module

        vector = getattr(load_module("FreeCAD"), "Vector", None)
        if callable(vector):
            return vector(x, y, z)
    except Exception:
        pass
    return _Vector(x, y, z)


def _rotate(
    placement: object, direction: tuple[float, float, float]
) -> tuple[float, float, float]:
    rotation = getattr(placement, "Rotation", None) if placement is not None else None
    if rotation is None:
        return direction
    mult = getattr(rotation, "multVec", None)
    if callable(mult):
        try:
            rotated = _components(mult(_make_vector(*direction)))
        except Exception:
            rotated = None
        if rotated is not None:
            return rotated
    angle = getattr(rotation, "Angle", None)
    try:
        if angle is None or abs(float(angle)) <= 1.0e-12:
            return direction
    except (TypeError, ValueError):
        return direction
    return direction


def _transform_point(
    placement: object, point: tuple[float, float, float]
) -> tuple[float, float, float]:
    rotated = _rotate(placement, point)
    base = _components(getattr(placement, "Base", None)) if placement is not None else None
    if base is None:
        return rotated
    return (rotated[0] + base[0], rotated[1] + base[1], rotated[2] + base[2])


def _ancestor_placements(obj: object) -> list[object]:
    """Placements of enclosing bodies, innermost first.

    A feature shape already includes that feature's own placement. Only the
    enclosing GeoFeatureGroup placements remain to reach the global frame.
    """

    placements: list[object] = []
    current: object | None = obj
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parent = _owning_body(current)
        if parent is None or id(parent) in seen:
            break
        placement = getattr(parent, "Placement", None)
        if placement is not None:
            placements.append(placement)
        current = parent
    return placements


def _to_global_point(
    obj: object, point: tuple[float, float, float]
) -> tuple[float, float, float]:
    result = point
    for placement in _ancestor_placements(obj):
        result = _transform_point(placement, result)
    return result


def _to_global_direction(
    obj: object, direction: tuple[float, float, float]
) -> tuple[float, float, float]:
    result = direction
    for placement in _ancestor_placements(obj):
        result = _rotate(placement, result)
    unit = _unit(result)
    return unit if unit is not None else result


def _placement_z(placement: object) -> tuple[float, float, float] | None:
    """Plane normal: the placement's local +Z, not ``Rotation.Axis``."""

    if placement is None:
        return None
    return _unit(_rotate(placement, (0.0, 0.0, 1.0)))


def _datum_pose(
    datum: object,
) -> tuple[tuple[float, float, float] | None, tuple[float, float, float] | None]:
    placement = getattr(datum, "Placement", None)
    base = _components(getattr(placement, "Base", None)) if placement is not None else None
    normal = _placement_z(placement)
    if base is not None:
        base = _to_global_point(datum, base)
    if normal is not None:
        normal = _to_global_direction(datum, normal)
    return base, normal


def _element_tokens(sub_name: str) -> list[str]:
    return [part.strip() for part in sub_name.split(",") if part.strip()]


def _indexed_subshape(shape: object, name: str) -> object | None:
    if name.startswith("Face"):
        collection_name = "Faces"
    elif name.startswith("Edge"):
        collection_name = "Edges"
    else:
        return None
    try:
        index = int(name[4:]) - 1
    except ValueError:
        return None
    try:
        items = list(getattr(shape, collection_name, None) or [])
    except Exception:
        return None
    if index < 0 or index >= len(items):
        return None
    return cast(object, items[index])


def _shape_center(sub: object) -> tuple[float, float, float] | None:
    center = _components(getattr(sub, "CenterOfMass", None))
    if center is not None:
        return center
    return _components(getattr(sub, "CenterOfBoundBox", None))


def _surface_normal(face: object) -> tuple[float, float, float] | None:
    normal_at = getattr(face, "normalAt", None)
    if callable(normal_at):
        parameter = getattr(face, "ParameterRange", None)
        if isinstance(parameter, (list, tuple)) and len(parameter) >= 4:
            try:
                u_mid = (float(parameter[0]) + float(parameter[1])) / 2.0
                v_mid = (float(parameter[2]) + float(parameter[3])) / 2.0
                found = _components(normal_at(u_mid, v_mid))
                if found is not None:
                    return found
            except Exception:
                pass
    surface = getattr(face, "Surface", None)
    if surface is None:
        return None
    return _components(getattr(surface, "Axis", None))


def _curve_direction(edge: object) -> tuple[float, float, float] | None:
    curve = getattr(edge, "Curve", None)
    if curve is None:
        return None
    direction = _components(getattr(curve, "Direction", None))
    if direction is not None:
        return direction
    return _components(getattr(curve, "Axis", None))


def _local_frame(
    obj: object, sub_name: str
) -> tuple[tuple[float, float, float] | None, tuple[float, float, float] | None] | None:
    shape = getattr(obj, "Shape", None)
    if shape is None:
        return None
    for token in _element_tokens(sub_name):
        sub = _indexed_subshape(shape, token)
        if sub is None:
            continue
        center = _shape_center(sub)
        direction = _surface_normal(sub) if token.startswith("Face") else _curve_direction(sub)
        if center is None and direction is None:
            continue
        global_center = _to_global_point(obj, center) if center is not None else None
        global_direction = _to_global_direction(obj, direction) if direction is not None else None
        return global_center, global_direction
    return None


def _support_object(datum: object, entry: Mapping[str, object]) -> object | None:
    live = entry.get("item")
    if live is not None and not isinstance(live, str):
        return live
    name = str(entry.get("object", ""))
    getter = getattr(datum, "getDocument", None)
    document = getter() if callable(getter) else None
    get_object = getattr(document, "getObject", None)
    if callable(get_object) and name:
        found = get_object(name)
        if found is not None:
            return cast(object, found)
    return None


def _signed_distance(
    center: tuple[float, float, float],
    face_normal: tuple[float, float, float],
    point: tuple[float, float, float],
    plane_normal: tuple[float, float, float],
) -> float | None:
    """Signed distance from the face to the datum plane along the face normal."""

    normal = _unit(face_normal)
    plane = _unit(plane_normal)
    if normal is None or plane is None:
        return None
    delta = (point[0] - center[0], point[1] - center[1], point[2] - center[2])
    denom = _dot(normal, plane)
    along_normal = _dot(delta, normal)
    value = along_normal if abs(denom) <= 1.0e-9 else _dot(delta, plane) / denom
    return round(value, 6)


def _angle_between(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> float | None:
    left_unit = _unit(left)
    right_unit = _unit(right)
    if left_unit is None or right_unit is None:
        return None
    cosine = max(-1.0, min(1.0, _dot(left_unit, right_unit)))
    return round(math.degrees(math.acos(cosine)), 6)


def _annotated_support(
    datum: object, support: list[dict[str, object]]
) -> tuple[list[dict[str, object]], float | None, float | None]:
    rows: list[dict[str, object]] = []
    distance: float | None = None
    angle: float | None = None
    datum_point, datum_normal = _datum_pose(datum)
    for entry in support:
        row: dict[str, object] = {
            "object": str(entry.get("object", "")),
            "sub": str(entry.get("sub", "")),
        }
        obj = _support_object(datum, entry)
        frame = _local_frame(obj, str(entry.get("sub", ""))) if obj is not None else None
        if frame is not None:
            center, normal = frame
            if center is not None:
                row["center"] = _point_dict(center)
            if normal is not None:
                row["normal"] = _point_dict(normal)
            if (
                distance is None
                and center is not None
                and normal is not None
                and datum_point is not None
                and datum_normal is not None
            ):
                distance = _signed_distance(center, normal, datum_point, datum_normal)
                angle = _angle_between(normal, datum_normal)
        rows.append(row)
    return rows, distance, angle


def _placement_separation(datum: object, support_obj: object) -> float | None:
    support_placement = getattr(support_obj, "Placement", None)
    datum_placement = getattr(datum, "Placement", None)
    support_base = (
        getattr(support_placement, "Base", None) if support_placement is not None else None
    )
    datum_base = (
        getattr(datum_placement, "Base", None) if datum_placement is not None else None
    )
    if support_base is None or datum_base is None:
        return None
    try:
        delta = datum_base - support_base
        return round(float(getattr(delta, "Length", 0.0)), 6)
    except Exception:
        return None


def _attachment_diagnostics(datum: object) -> dict[str, object]:
    support = _support_entries(datum)
    placement = _placement_dict(getattr(datum, "Placement", None))
    public_support, distance, normal_angle_deg = _annotated_support(datum, support)
    source_body_placement_dropped = False
    if support:
        first = support[0]
        support_obj_name = str(first.get("object", ""))
        getter = getattr(datum, "getDocument", None)
        doc = getter() if callable(getter) else None
        live_support = first.get("item")
        support_obj = live_support if live_support is not None and not isinstance(live_support, str) else None
        if support_obj is None and doc is not None and hasattr(doc, "getObject") and support_obj_name:
            support_obj = doc.getObject(support_obj_name)
        if support_obj is not None:
            if distance is None:
                distance = _placement_separation(datum, support_obj)
            datum_body = _owning_body(datum)
            support_body = _owning_body(support_obj)
            datum_body_name = object_name(datum_body) if datum_body is not None else None
            support_body_name = object_name(support_body) if support_body is not None else None
            if (
                datum_body is not None
                and support_body is not None
                and datum_body is not support_body
                and not _placement_is_identity(getattr(support_body, "Placement", None))
            ):
                source_body_placement_dropped = True
            extras = {
                "datum": object_name(datum),
                "datum_body": datum_body_name,
                "support_body": support_body_name,
                "diff": {
                    "signed_distance_mm": distance,
                    "angle_deg": normal_angle_deg,
                },
            }
        else:
            extras = {
                "datum": object_name(datum),
                "datum_body": object_name(_owning_body(datum)),
                "support_body": None,
                "diff": {
                    "signed_distance_mm": distance,
                    "angle_deg": normal_angle_deg,
                },
            }
    else:
        extras = {
            "datum": object_name(datum),
            "datum_body": object_name(_owning_body(datum)),
            "support_body": None,
            "diff": {
                "signed_distance_mm": distance,
                "angle_deg": normal_angle_deg,
            },
        }
    return {
        "support": public_support,
        "placement": placement,
        "distance": distance,
        "normal_angle_deg": normal_angle_deg,
        "source_body_placement_dropped": source_body_placement_dropped,
        **extras,
    }


def apply_preview_attachment(doc: PreviewAttachmentDocument, request: PreviewAttachmentRequest) -> PreviewAttachmentReceipt:
    """Capture the datum identity; attachment is read after native recompute."""

    datum = require_object(doc, request.datum_name, missing_code="OBJECT_NOT_FOUND", error=PreviewAttachmentError)
    return PreviewAttachmentReceipt(name=object_name(datum) or request.datum_name, item=datum, skipped=False)


def read_preview_attachment_result(doc: PreviewAttachmentReadDocument, receipt: PreviewAttachmentReceipt) -> PreviewAttachmentInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise PreviewAttachmentError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise PreviewAttachmentError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    diagnostics = _attachment_diagnostics(located)
    return PreviewAttachmentInspection(
        name=PreviewAttachmentName(receipt.name),
        label=object_label(located),
        extra=diagnostics,
    )


def build_preview_attachment_request(doc_name: object, datum_name: object) -> PreviewAttachmentRequest | PreviewAttachmentFailure:
    doc_name_value = nonempty_string(doc_name, "doc_name")
    if doc_name_value is None:
        return _failure(PreviewAttachmentError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    datum_name_value = nonempty_string(datum_name, "datum_name")
    if datum_name_value is None:
        return _failure(PreviewAttachmentError("INVALID_ARGUMENT", "datum_name must be a nonempty string"))
    return PreviewAttachmentRequest(
        doc_name=DocumentName(doc_name_value),
        datum_name=datum_name_value,
    )


@dataclass(slots=True)
class _PreviewAttachmentExecution:
    collaborators: PreviewAttachmentCollaborators
    request: PreviewAttachmentRequest
    created: PreviewAttachmentReceipt | None = None
    inspected: PreviewAttachmentInspection | None = None

    def apply(self, doc: PreviewAttachmentDocument) -> None:
        self.created = apply_preview_attachment(doc, self.request)

    def inspect(self, doc: PreviewAttachmentReadDocument) -> None:
        if self.created is None:
            raise PreviewAttachmentError(
                "INVALID_PREVIEW_ATTACHMENT_RESULT",
                "preview_attachment did not return an identity receipt",
            )
        self.inspected = read_preview_attachment_result(doc, self.created)

    def run(self) -> NativeOutcome[PreviewAttachmentResult]:
        result = run_preview_attachment_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        def _finish_native_commit(
            result: Literal[True] | PreviewAttachmentFailure | PreviewAttachmentUncertain,
        ) -> PreviewAttachmentResult:
            if result is not True:
                return result
            if self.inspected is None:
                return make_preview_attachment_uncertain(
                    "PREVIEW_ATTACHMENT_COMMITTED_RESPONSE_INVALID",
                    "Native commit completed without an inspected result",
                    committed=True,
                )
            extra = self.inspected.extra if isinstance(self.inspected.extra, Mapping) else {}
            return make_preview_attachment_success(
                datum_name=self.inspected.name,
                support=extra.get("support"),
                placement=extra.get("placement"),
                distance=extra.get("distance"),
                normal_angle_deg=extra.get("normal_angle_deg"),
                source_body_placement_dropped=extra.get("source_body_placement_dropped"),
                datum=extra.get("datum"),
                datum_body=extra.get("datum_body"),
                support_body=extra.get("support_body"),
                diff=extra.get("diff"),
            )

        return settle_native_commit(result, _finish_native_commit)

def run_preview_attachment(
    collaborators: PreviewAttachmentCollaborators,
    doc_name: object, datum_name: object,
) -> NativeOutcome[PreviewAttachmentResult]:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_preview_attachment_request(doc_name, datum_name)
    if isinstance(request, dict):
        return request
    return _PreviewAttachmentExecution(collaborators, request).run()


class _PreviewAttachmentRpcFacade(Protocol):
    _cad_collaborators: PreviewAttachmentCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_preview_attachment(
    self: _PreviewAttachmentRpcFacade, doc_name: str, datum_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_preview_attachment(collaborators, doc_name, datum_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("preview_attachment", rpc_preview_attachment)


__all__ = [
    "PreviewAttachmentCollaborators",
    "PreviewAttachmentError",
    "PreviewAttachmentInspection",
    "PreviewAttachmentReceipt",
    "apply_preview_attachment",
    "build_preview_attachment_request",
    "read_preview_attachment_result",
    "rpc_preview_attachment",
    "run_preview_attachment",
    "TYPED_RPC_HANDLER",
]
