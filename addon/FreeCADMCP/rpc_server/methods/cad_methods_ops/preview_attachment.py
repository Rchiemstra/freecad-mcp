
"""Typed ``preview_attachment`` mutation."""
from __future__ import annotations

from .typed_rpc_support import (
    nonempty_string,
    object_label,
    object_name,
    require_object,
)

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.preview_attachment_contract import (
    PreviewAttachmentCollaborators,
    PreviewAttachmentDocument,
    PreviewAttachmentFailure,
    PreviewAttachmentName,
    PreviewAttachmentReadDocument,
    PreviewAttachmentRequest,
    PreviewAttachmentResult,
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
            entries.append({"object": object_name(obj), "sub": str(sub)})
        else:
            entries.append({"object": object_name(item), "sub": ""})
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


def _owning_body(obj: object) -> object | None:
    getter = getattr(obj, "getParentGeoFeatureGroup", None)
    if callable(getter):
        try:
            owner: object | None = getter()
        except Exception:
            owner = None
        if owner is not None:
            located: object = owner
            return located
    for candidate in getattr(obj, "InList", ()) or ():
        if getattr(candidate, "TypeId", "") == "PartDesign::Body":
            if obj in getattr(candidate, "Group", ()):
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


def _attachment_diagnostics(datum: object) -> dict[str, object]:
    support = _support_entries(datum)
    placement = _placement_dict(getattr(datum, "Placement", None))
    distance = None
    normal_angle_deg = None
    source_body_placement_dropped = False
    if support:
        first = support[0]
        support_obj_name = str(first.get("object", ""))
        getter = getattr(datum, "getDocument", None)
        doc = getter() if callable(getter) else None
        support_obj = doc.getObject(support_obj_name) if doc is not None and hasattr(doc, "getObject") else None
        if support_obj is not None:
            support_placement = getattr(support_obj, "Placement", None)
            datum_placement = getattr(datum, "Placement", None)
            support_base = getattr(support_placement, "Base", None) if support_placement is not None else None
            datum_base = getattr(datum_placement, "Base", None) if datum_placement is not None else None
            if support_base is not None and datum_base is not None:
                try:
                    delta = datum_base - support_base
                    distance = round(float(getattr(delta, "Length", 0.0)), 6)
                except Exception:
                    distance = None
            shape = getattr(support_obj, "Shape", None)
            face_name = str(first.get("sub", ""))
            if shape is not None and face_name.startswith("Face"):
                try:
                    face_index = int(face_name[4:]) - 1
                    faces = list(getattr(shape, "Faces", None) or [])
                    if 0 <= face_index < len(faces):
                        face = faces[face_index]
                        normal = None
                        normal_at = getattr(face, "normalAt", None)
                        if callable(normal_at):
                            try:
                                u_min, u_max, _v_min, _v_max = face.ParameterRange
                                normal = normal_at(u_min, u_max)
                            except Exception:
                                normal = None
                        if normal is not None and datum_placement is not None:
                            rotation = getattr(datum_placement, "Rotation", None)
                            datum_axis = getattr(rotation, "Axis", None) if rotation is not None else None
                            if datum_axis is not None:
                                try:
                                    dot = abs(float(normal.dot(datum_axis)))
                                    normal_angle_deg = round(math.degrees(math.acos(min(1.0, dot))), 6)
                                except Exception:
                                    normal_angle_deg = None
                except Exception:
                    pass
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
        "support": support,
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

    def run(self) -> PreviewAttachmentResult:
        result = run_preview_attachment_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
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


def run_preview_attachment(
    collaborators: PreviewAttachmentCollaborators,
    doc_name: object, datum_name: object,
) -> PreviewAttachmentResult:
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
