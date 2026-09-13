"""Typed ``sketch_attach`` mutation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_attach_contract import (
    DocumentName,
    SketchAttachCollaborators,
    SketchAttachDocument,
    SketchAttachFailure,
    SketchAttachObject,
    SketchAttachReadDocument,
    SketchAttachResult,
    SketchName,
    make_sketch_attach_failure,
    make_sketch_attach_success,
    make_sketch_attach_uncertain,
)
from .sketch_attach_mutation import SketchAttachError, run_sketch_attach_native_mutation


@dataclass(frozen=True, slots=True)
class SketchAttachReceipt:
    name: str
    sketch: SketchAttachObject
    attached_kind: str
    attached_object: str
    attached_subname: str


@dataclass(frozen=True, slots=True)
class SketchAttachInspection:
    name: SketchName
    attached_kind: str
    attached_object: str
    attached_subname: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _SketchAttachRequest:
    doc_name: DocumentName
    sketch_name: SketchName
    support: object
    attachment_offset: Mapping[str, object] | None


def _failure(error: SketchAttachError, *, retry_safe: bool = True) -> SketchAttachFailure:
    return make_sketch_attach_failure(error.code, str(error), retry_safe=retry_safe)


def _find_origin_plane(doc: SketchAttachDocument, sketch: object, plane_name: str) -> object | None:
    body = None
    for obj in getattr(doc, "Objects", ()):
        if getattr(obj, "TypeId", "") == "PartDesign::Body" and sketch in getattr(obj, "Group", []):
            body = obj
            break
    origins = []
    if body is not None and getattr(body, "Origin", None) is not None:
        origins.append(body.Origin)
    for origin in getattr(doc, "Objects", ()):
        if getattr(origin, "TypeId", "") == "App::Origin" and origin not in origins:
            origins.append(origin)
    for origin in origins:
        for feat in getattr(origin, "OriginFeatures", []) or []:
            if getattr(feat, "Label", "") == plane_name or getattr(feat, "Name", "") == plane_name:
                found: object = feat
                return found
        if hasattr(origin, plane_name):
            named: object = getattr(origin, plane_name)
            return named
    return None


def _resolve_support(sketch: object, doc: SketchAttachDocument, support: object) -> tuple[str, str, str]:
    if isinstance(support, str):
        if support in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
            plane = _find_origin_plane(doc, sketch, support)
            if plane is None:
                raise SketchAttachError("SUPPORT_NOT_FOUND", f"Origin plane not found: {support}")
            sketch.AttachmentSupport = [(plane, "")]  # type: ignore[attr-defined]
            sketch.MapMode = "FlatFace"  # type: ignore[attr-defined]
            return "origin_plane", str(getattr(plane, "Name", support)), ""
        if ":" not in support:
            raise SketchAttachError("INVALID_ARGUMENT", f"Unsupported support string: {support}")
        obj_name, sub = support.split(":", 1)
        ref = doc.getObject(obj_name)
        if ref is None:
            raise SketchAttachError("SUPPORT_NOT_FOUND", f"Support object not found: {obj_name}")
        sketch.AttachmentSupport = [(ref, sub)]  # type: ignore[attr-defined]
        sketch.MapMode = "FlatFace"  # type: ignore[attr-defined]
        return "face_ref", ref.Name, sub
    if isinstance(support, Mapping):
        obj_name_obj = support.get("object") or support.get("object_name")
        sub_obj = support.get("subname") or support.get("sub") or ""
        if not isinstance(obj_name_obj, str) or not obj_name_obj.strip():
            raise SketchAttachError("INVALID_ARGUMENT", "support.object must be a nonempty string")
        if not isinstance(sub_obj, str):
            raise SketchAttachError("INVALID_ARGUMENT", "support.subname must be a string")
        ref = doc.getObject(obj_name_obj)
        if ref is None:
            raise SketchAttachError("SUPPORT_NOT_FOUND", f"Support object not found: {obj_name_obj}")
        sketch.AttachmentSupport = [(ref, sub_obj)]  # type: ignore[attr-defined]
        sketch.MapMode = "FlatFace"  # type: ignore[attr-defined]
        return "dict_ref", ref.Name, sub_obj
    raise SketchAttachError("INVALID_ARGUMENT", "support must be str or dict")


def apply_sketch_attach(
    doc: SketchAttachDocument,
    sketch_name: SketchName,
    support: object,
    attachment_offset: Mapping[str, object] | None,
    collaborators: SketchAttachCollaborators,
) -> SketchAttachReceipt:
    """Attach a sketch without recomputing or managing a transaction."""

    sketch = doc.getObject(sketch_name)
    if sketch is None:
        raise SketchAttachError("SKETCH_NOT_FOUND", f"Sketch {sketch_name!r} not found")
    if not hasattr(sketch, "AttachmentSupport") and getattr(sketch, "TypeId", None) != "Sketcher::SketchObject":
        raise SketchAttachError("NOT_A_SKETCH", f"Object {sketch_name!r} is not a sketch")
    kind, attached_object, subname = _resolve_support(sketch, doc, support)
    if attachment_offset is not None:
        if not hasattr(sketch, "AttachmentOffset"):
            raise SketchAttachError(
                "INVALID_ARGUMENT",
                f"Sketch {sketch_name!r} has no AttachmentOffset property",
            )
        sketch.AttachmentOffset = collaborators.dict_to_placement(attachment_offset)
    return SketchAttachReceipt(
        name=sketch.Name,
        sketch=sketch,
        attached_kind=kind,
        attached_object=attached_object,
        attached_subname=subname,
    )


def read_sketch_attach_result(
    doc: SketchAttachReadDocument, receipt: SketchAttachReceipt
) -> SketchAttachInspection:
    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchAttachError("CREATED_OBJECT_MISSING", f"Sketch is missing: {receipt.name!r}")
    if sketch is not receipt.sketch:
        raise SketchAttachError(
            "CREATED_OBJECT_REPLACED",
            f"Sketch was replaced before commit: {receipt.name!r}",
        )
    return SketchAttachInspection(
        name=SketchName(receipt.name),
        attached_kind=receipt.attached_kind,
        attached_object=receipt.attached_object,
        attached_subname=receipt.attached_subname,
    )


def build_sketch_attach_request(
    doc_name: object,
    sketch_name: object,
    support: object,
    attachment_offset: object,
) -> _SketchAttachRequest | SketchAttachFailure:
    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(SketchAttachError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure(SketchAttachError("INVALID_ARGUMENT", "sketch_name must be a nonempty string"))
    if not isinstance(support, (str, Mapping)):
        return _failure(SketchAttachError("INVALID_ARGUMENT", "support must be a string or object"))
    offset: Mapping[str, object] | None
    if attachment_offset is None:
        offset = None
    elif isinstance(attachment_offset, Mapping) and all(isinstance(key, str) for key in attachment_offset):
        offset = {str(key): attachment_offset[key] for key in attachment_offset}
    else:
        return _failure(SketchAttachError("INVALID_ARGUMENT", "attachment_offset must be an object"))
    return _SketchAttachRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        support=support,
        attachment_offset=offset,
    )


@dataclass(slots=True)
class _SketchAttachExecution:
    collaborators: SketchAttachCollaborators
    request: _SketchAttachRequest
    created: SketchAttachReceipt | None = None
    inspected: SketchAttachInspection | None = None

    def apply(self, doc: SketchAttachDocument) -> None:
        self.created = apply_sketch_attach(
            doc,
            self.request.sketch_name,
            self.request.support,
            self.request.attachment_offset,
            self.collaborators,
        )

    def inspect(self, doc: SketchAttachReadDocument) -> None:
        if self.created is None:
            raise SketchAttachError(
                "INVALID_SKETCH_ATTACH_RESULT",
                "Sketch attach did not return an identity receipt",
            )
        self.inspected = read_sketch_attach_result(doc, self.created)

    def run(self) -> SketchAttachResult:
        result = run_sketch_attach_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_attach_uncertain(
                "SKETCH_ATTACH_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected attach result",
                committed=True,
            )
        return make_sketch_attach_success(
            self.inspected.name,
            self.inspected.attached_kind,
            self.inspected.attached_object,
            self.inspected.attached_subname,
        )


def run_sketch_attach(
    collaborators: SketchAttachCollaborators,
    doc_name: object,
    sketch_name: object,
    support: object,
    attachment_offset: object = None,
) -> SketchAttachResult:
    request = build_sketch_attach_request(doc_name, sketch_name, support, attachment_offset)
    if isinstance(request, dict):
        return request
    return _SketchAttachExecution(collaborators, request).run()


class _SketchAttachRpcFacade(Protocol):
    _cad_collaborators: SketchAttachCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_attach(
    self: _SketchAttachRpcFacade,
    doc_name: str,
    sketch_name: str,
    support: object,
    attachment_offset: object = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_attach(collaborators, doc_name, sketch_name, support, attachment_offset)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_attach", rpc_sketch_attach)


__all__ = [
    "SketchAttachCollaborators",
    "SketchAttachError",
    "SketchAttachInspection",
    "SketchAttachReceipt",
    "apply_sketch_attach",
    "build_sketch_attach_request",
    "read_sketch_attach_result",
    "rpc_sketch_attach",
    "run_sketch_attach",
    "TYPED_RPC_HANDLER",
]
