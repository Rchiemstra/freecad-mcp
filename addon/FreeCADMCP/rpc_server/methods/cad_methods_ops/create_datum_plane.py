"""Typed ``create_datum_plane`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.create_datum_plane_contract import (
    CreateDatumPlaneCollaborators,
    CreateDatumPlaneDocument,
    CreateDatumPlaneFailure,
    CreateDatumPlaneName,
    CreateDatumPlaneReadDocument,
    CreateDatumPlaneRequest,
    CreateDatumPlaneResult,
    DocumentName,
    make_create_datum_plane_failure,
    make_create_datum_plane_success,
    make_create_datum_plane_uncertain,
)
from .create_datum_plane_mutation import CreateDatumPlaneError, run_create_datum_plane_native_mutation
from .typed_runtime import is_derived_from
from .typed_rpc_support import (
    assign_attr,
    nonempty_string,
    object_label,
    object_name,
    optional_string,
    parse_ref,
    require_object,
    resolve_if_exists,
)


@dataclass(frozen=True, slots=True)
class CreateDatumPlaneReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False


@dataclass(frozen=True, slots=True)
class CreateDatumPlaneInspection:
    """Read-only data captured after the native-owned recompute."""

    name: CreateDatumPlaneName
    label: str


def _failure(error: CreateDatumPlaneError, *, retry_safe: bool = True) -> CreateDatumPlaneFailure:
    return make_create_datum_plane_failure(error.code, str(error), retry_safe=retry_safe)


def _body_xy_plane(body: object) -> object | None:
    origin = getattr(body, "Origin", None)
    for feature in getattr(origin, "OriginFeatures", []) or []:
        label = str(getattr(feature, "Label", ""))
        name = str(getattr(feature, "Name", ""))
        if label == "XY_Plane" or name == "XY_Plane":
            return feature
    return None


def apply_create_datum_plane(doc: CreateDatumPlaneDocument, request: CreateDatumPlaneRequest) -> CreateDatumPlaneReceipt:
    """Create a PartDesign datum plane without recomputing."""

    body = require_object(doc, request.body_name, missing_code="OBJECT_NOT_FOUND", error=CreateDatumPlaneError)
    skipped = resolve_if_exists(doc, request.plane_name, request.if_exists, error=CreateDatumPlaneError)
    if skipped is not None:
        return CreateDatumPlaneReceipt(name=object_name(skipped) or request.plane_name, item=skipped, skipped=True)
    factory = getattr(body, "newObject", None)
    if not callable(factory):
        raise CreateDatumPlaneError("INVALID_BODY", "Body must provide newObject")
    plane = factory("PartDesign::Plane", request.plane_name)
    if plane is None:
        raise CreateDatumPlaneError(
            "CREATE_DATUM_PLANE_FAILED",
            f"Failed to create PartDesign::Plane: {request.plane_name!r}",
        )
    if request.mode not in {
        "midpoint_between_faces",
        "through_point",
        "offset_from_face",
        "between_parallel_planes",
        "plane_from_binder_face",
    }:
        raise CreateDatumPlaneError("INVALID_ARGUMENT", f"Unsupported datum plane mode: {request.mode}")
    if request.mode == "through_point":
        if request.source_ref:
            obj, sub = parse_ref(doc, request.source_ref, CreateDatumPlaneError)
            assign_attr(plane, "AttachmentSupport", [(obj, sub)])
            assign_attr(plane, "MapMode", request.map_mode)
        else:
            xy_plane = _body_xy_plane(body)
            if xy_plane is None:
                raise CreateDatumPlaneError("OBJECT_NOT_FOUND", "Body origin XY_Plane not found")
            assign_attr(plane, "AttachmentSupport", [(xy_plane, "")])
            assign_attr(plane, "MapMode", "FlatFace")
    else:
        support = request.source_ref or request.face_a
        if support:
            obj, sub = parse_ref(doc, support, CreateDatumPlaneError)
            assign_attr(plane, "AttachmentSupport", [(obj, sub)])
        assign_attr(plane, "MapMode", request.map_mode)
    return CreateDatumPlaneReceipt(name=object_name(plane) or request.plane_name, item=plane, skipped=False)


def read_create_datum_plane_result(doc: CreateDatumPlaneReadDocument, receipt: CreateDatumPlaneReceipt) -> CreateDatumPlaneInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise CreateDatumPlaneError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise CreateDatumPlaneError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")
    if not is_derived_from(located, "PartDesign::Plane"):
        raise CreateDatumPlaneError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::Plane: {receipt.name!r}",
        )
    return CreateDatumPlaneInspection(
        name=CreateDatumPlaneName(receipt.name),
        label=object_label(located),
    )


def build_create_datum_plane_request(doc_name: object, plane_name: object, body_name: object, mode: object, source_ref: object, face_a: object, face_b: object, offset_along_normal: object, map_mode: object, if_exists: object) -> CreateDatumPlaneRequest | CreateDatumPlaneFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(CreateDatumPlaneError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    plane_name_value = nonempty_string(plane_name, 'plane_name')
    if plane_name_value is None:
        return _failure(CreateDatumPlaneError("INVALID_ARGUMENT", "plane_name must be a nonempty string"))
    body_name_value = nonempty_string(body_name, 'body_name')
    if body_name_value is None:
        return _failure(CreateDatumPlaneError("INVALID_ARGUMENT", "body_name must be a nonempty string"))
    mode_value = nonempty_string(mode, 'mode')
    if mode_value is None:
        return _failure(CreateDatumPlaneError("INVALID_ARGUMENT", "mode must be a nonempty string"))
    if source_ref is None:
        source_ref_value: str | None = None
    else:
        source_ref_value = optional_string(source_ref)
        if source_ref_value is None:
            return _failure(CreateDatumPlaneError("INVALID_ARGUMENT", "source_ref must be a nonempty string or None"))
    if face_a is None:
        face_a_value: str | None = None
    else:
        face_a_value = optional_string(face_a)
        if face_a_value is None:
            return _failure(CreateDatumPlaneError("INVALID_ARGUMENT", "face_a must be a nonempty string or None"))
    if face_b is None:
        face_b_value: str | None = None
    else:
        face_b_value = optional_string(face_b)
        if face_b_value is None:
            return _failure(CreateDatumPlaneError("INVALID_ARGUMENT", "face_b must be a nonempty string or None"))
    map_mode_value = nonempty_string(map_mode, 'map_mode')
    if map_mode_value is None:
        return _failure(CreateDatumPlaneError("INVALID_ARGUMENT", "map_mode must be a nonempty string"))
    if_exists_value = nonempty_string(if_exists, 'if_exists')
    if if_exists_value is None:
        return _failure(CreateDatumPlaneError("INVALID_ARGUMENT", "if_exists must be a nonempty string"))
    if if_exists not in {"error", "skip", "replace"}:
        return _failure(CreateDatumPlaneError("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace"))
    return CreateDatumPlaneRequest(
        doc_name=DocumentName(doc_name_value),
        plane_name=plane_name_value,
        body_name=body_name_value,
        mode=mode_value,
        source_ref=source_ref_value,
        face_a=face_a_value,
        face_b=face_b_value,
        offset_along_normal=offset_along_normal,
        map_mode=map_mode_value,
        if_exists=if_exists_value,
    )


@dataclass(slots=True)
class _CreateDatumPlaneExecution:
    collaborators: CreateDatumPlaneCollaborators
    request: CreateDatumPlaneRequest
    created: CreateDatumPlaneReceipt | None = None
    inspected: CreateDatumPlaneInspection | None = None

    def apply(self, doc: CreateDatumPlaneDocument) -> None:
        self.created = apply_create_datum_plane(doc, self.request)

    def inspect(self, doc: CreateDatumPlaneReadDocument) -> None:
        if self.created is None:
            raise CreateDatumPlaneError(
                "INVALID_CREATE_DATUM_PLANE_RESULT",
                "create_datum_plane did not return an identity receipt",
            )
        self.inspected = read_create_datum_plane_result(doc, self.created)

    def run(self) -> CreateDatumPlaneResult:
        result = run_create_datum_plane_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_create_datum_plane_uncertain(
                "CREATE_DATUM_PLANE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_create_datum_plane_success(plane_name=self.inspected.name, body_name=self.request.body_name)


def run_create_datum_plane(
    collaborators: CreateDatumPlaneCollaborators,
    doc_name: object, plane_name: object, body_name: object, mode: object, source_ref: object, face_a: object, face_b: object, offset_along_normal: object, map_mode: object, if_exists: object,
) -> CreateDatumPlaneResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_create_datum_plane_request(doc_name, plane_name, body_name, mode, source_ref, face_a, face_b, offset_along_normal, map_mode, if_exists)
    if isinstance(request, dict):
        return request
    return _CreateDatumPlaneExecution(collaborators, request).run()


class _CreateDatumPlaneRpcFacade(Protocol):
    _cad_collaborators: CreateDatumPlaneCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_create_datum_plane(
    self: _CreateDatumPlaneRpcFacade, doc_name: str, plane_name: str, body_name: str, mode: str, source_ref: str | None = None, face_a: str | None = None, face_b: str | None = None, offset_along_normal: object = None, map_mode: str = "FlatFace", if_exists: str = "error",
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_create_datum_plane(collaborators, doc_name, plane_name, body_name, mode, source_ref, face_a, face_b, offset_along_normal, map_mode, if_exists)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("create_datum_plane", rpc_create_datum_plane)


__all__ = [
    "CreateDatumPlaneCollaborators",
    "CreateDatumPlaneError",
    "CreateDatumPlaneInspection",
    "CreateDatumPlaneReceipt",
    "apply_create_datum_plane",
    "build_create_datum_plane_request",
    "read_create_datum_plane_result",
    "rpc_create_datum_plane",
    "run_create_datum_plane",
    "TYPED_RPC_HANDLER",
]
