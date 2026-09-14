"""Typed ``sketch_create`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast

from ...._shared.protocol.sketch_create_contract import (
    DocumentName,
    SketchCreateCollaborators,
    SketchCreateDocument,
    SketchCreateFailure,
    SketchCreateObject,
    SketchCreateReadDocument,
    SketchCreateResult,
    SketchName,
    make_sketch_create_failure,
    make_sketch_create_success,
    make_sketch_create_uncertain,
)
from .sketch_create_mutation import SketchCreateError, run_sketch_create_native_mutation


@dataclass(frozen=True, slots=True)
class SketchCreateReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    sketch: SketchCreateObject


@dataclass(frozen=True, slots=True)
class SketchCreateInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SketchName
    label: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _SketchCreateRequest:
    doc_name: DocumentName
    sketch_name: SketchName
    body_name: str | None
    attach_to: str | None


def _failure(error: SketchCreateError, *, retry_safe: bool = True) -> SketchCreateFailure:
    return make_sketch_create_failure(error.code, str(error), retry_safe=retry_safe)


def _is_sketch(obj: SketchCreateObject) -> bool:
    try:
        return bool(obj.isDerivedFrom("Sketcher::SketchObject"))
    except (AttributeError, TypeError):
        return obj.TypeId == "Sketcher::SketchObject"


def _is_body(obj: object) -> bool:
    derived = getattr(obj, "isDerivedFrom", None)
    if callable(derived):
        try:
            return bool(derived("PartDesign::Body"))
        except (AttributeError, TypeError):
            pass
    return getattr(obj, "TypeId", None) == "PartDesign::Body"


def _attach_origin_plane(sketch: object, doc: object, plane_name: str, freecad: object) -> None:
    plane_obj = None
    objects = getattr(doc, "Objects", ())
    for obj in objects:
        if getattr(obj, "TypeId", None) == "App::Origin":
            for feat in getattr(obj, "OriginFeatures", []) or ():
                if getattr(feat, "Label", None) == plane_name:
                    plane_obj = feat
                    break
        if plane_obj is not None:
            break
    if plane_obj is not None:
        sketch.AttachmentSupport = [(plane_obj, "")]  # type: ignore[attr-defined]
        sketch.MapMode = "FlatFace"  # type: ignore[attr-defined]
        return
    if plane_name == "XY_Plane":
        return
    vector_type = getattr(freecad, "Vector")
    rotation_type = getattr(freecad, "Rotation")
    placement_type = getattr(freecad, "Placement")
    if plane_name == "XZ_Plane":
        sketch.Placement = placement_type(  # type: ignore[attr-defined]
            vector_type(0, 0, 0),
            rotation_type(vector_type(1, 0, 0), 90),
        )
        return
    if plane_name == "YZ_Plane":
        sketch.Placement = placement_type(  # type: ignore[attr-defined]
            vector_type(0, 0, 0),
            rotation_type(vector_type(0, 1, 0), -90),
        )
        return
    raise SketchCreateError("INVALID_ARGUMENT", f"Unsupported attach_to: {plane_name!r}")


def _apply_attach_to(sketch: object, doc: object, attach_to: str, freecad: object) -> None:
    if attach_to in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
        _attach_origin_plane(sketch, doc, attach_to, freecad)
        return
    if ":" not in attach_to:
        raise SketchCreateError("INVALID_ARGUMENT", f"Unsupported attach_to: {attach_to!r}")
    obj_name, face = attach_to.split(":", 1)
    ref_obj = cast(SketchCreateDocument, doc).getObject(obj_name)
    if ref_obj is None:
        raise SketchCreateError("SUPPORT_NOT_FOUND", f"Object {obj_name!r} not found for attach_to")
    sketch.AttachmentSupport = [(ref_obj, face)]  # type: ignore[attr-defined]
    sketch.MapMode = "FlatFace"  # type: ignore[attr-defined]


def apply_sketch_create(
    doc: SketchCreateDocument,
    sketch_name: SketchName,
    body_name: str | None,
    attach_to: str | None,
    freecad: object,
) -> SketchCreateReceipt:
    """Create a Sketch without recomputing or managing a transaction."""

    if not isinstance(sketch_name, str):
        raise SketchCreateError("INVALID_ARGUMENT", "sketch_name must be a string")
    if not sketch_name.strip():
        raise SketchCreateError("INVALID_ARGUMENT", "sketch_name must not be empty")
    if doc.getObject(sketch_name) is not None:
        raise SketchCreateError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {sketch_name!r}",
        )

    if body_name is not None:
        body = doc.getObject(body_name)
        if body is None:
            raise SketchCreateError("BODY_NOT_FOUND", f"Body {body_name!r} not found")
        if not _is_body(body):
            raise SketchCreateError(
                "BODY_WRONG_TYPE",
                f"Object is not a PartDesign::Body: {body_name!r}",
            )
        new_object = getattr(body, "newObject", None)
        if not callable(new_object):
            raise SketchCreateError("BODY_WRONG_TYPE", f"Body cannot own a sketch: {body_name!r}")
        sketch = new_object("Sketcher::SketchObject", sketch_name)
    else:
        sketch = doc.addObject("Sketcher::SketchObject", sketch_name)

    if attach_to:
        _apply_attach_to(sketch, doc, attach_to, freecad)
    return SketchCreateReceipt(name=sketch.Name, sketch=sketch)


def read_sketch_create_result(
    doc: SketchCreateReadDocument, receipt: SketchCreateReceipt
) -> SketchCreateInspection:
    """Build the public result after the shared mutation recompute."""

    sketch = doc.getObject(receipt.name)
    if sketch is None:
        raise SketchCreateError(
            "CREATED_OBJECT_MISSING",
            f"Created sketch is missing: {receipt.name!r}",
        )
    if sketch is not receipt.sketch:
        raise SketchCreateError(
            "CREATED_OBJECT_REPLACED",
            f"Created sketch was replaced before commit: {receipt.name!r}",
        )
    if not _is_sketch(sketch):
        raise SketchCreateError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not a Sketcher::SketchObject: {receipt.name!r}",
        )
    return SketchCreateInspection(name=SketchName(receipt.name), label=str(sketch.Label))


def build_sketch_create_request(
    doc_name: object,
    sketch_name: object,
    body_name: object,
    attach_to: object,
) -> _SketchCreateRequest | SketchCreateFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(SketchCreateError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(sketch_name, str) or not sketch_name.strip():
        return _failure(
            SketchCreateError("INVALID_ARGUMENT", "sketch_name must be a nonempty string")
        )
    if body_name is not None and (not isinstance(body_name, str) or not body_name.strip()):
        return _failure(
            SketchCreateError("INVALID_ARGUMENT", "body_name must be a nonempty string")
        )
    if attach_to is not None and (not isinstance(attach_to, str) or not attach_to.strip()):
        return _failure(
            SketchCreateError("INVALID_ARGUMENT", "attach_to must be a nonempty string")
        )
    return _SketchCreateRequest(
        doc_name=DocumentName(doc_name),
        sketch_name=SketchName(sketch_name),
        body_name=body_name,
        attach_to=attach_to,
    )


@dataclass(slots=True)
class _SketchCreateExecution:
    collaborators: SketchCreateCollaborators
    request: _SketchCreateRequest
    created: SketchCreateReceipt | None = None
    inspected: SketchCreateInspection | None = None

    def apply(self, doc: SketchCreateDocument) -> None:
        self.created = apply_sketch_create(
            doc,
            self.request.sketch_name,
            self.request.body_name,
            self.request.attach_to,
            self.collaborators.freecad,
        )

    def inspect(self, doc: SketchCreateReadDocument) -> None:
        if self.created is None:
            raise SketchCreateError(
                "INVALID_SKETCH_CREATE_RESULT",
                "Sketch creation did not return an identity receipt",
            )
        self.inspected = read_sketch_create_result(doc, self.created)

    def run(self) -> SketchCreateResult:
        result = run_sketch_create_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_create_uncertain(
                "SKETCH_CREATE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected Sketch result",
                committed=True,
            )
        return make_sketch_create_success(self.inspected.name, self.inspected.label)


def run_sketch_create(
    collaborators: SketchCreateCollaborators,
    doc_name: object,
    sketch_name: object,
    body_name: object = None,
    attach_to: object = None,
) -> SketchCreateResult:
    """Run Sketch creation through apply, recompute, inspection, and commit."""

    request = build_sketch_create_request(doc_name, sketch_name, body_name, attach_to)
    if isinstance(request, dict):
        return request
    return _SketchCreateExecution(collaborators, request).run()


class _SketchCreateRpcFacade(Protocol):
    _cad_collaborators: SketchCreateCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sketch_create(
    self: _SketchCreateRpcFacade,
    doc_name: str,
    sketch_name: str,
    body_name: str | None = None,
    attach_to: str | None = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_create(collaborators, doc_name, sketch_name, body_name, attach_to)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_create", rpc_sketch_create)


__all__ = [
    "SketchCreateCollaborators",
    "SketchCreateError",
    "SketchCreateInspection",
    "SketchCreateReceipt",
    "apply_sketch_create",
    "build_sketch_create_request",
    "read_sketch_create_result",
    "rpc_sketch_create",
    "run_sketch_create",
    "TYPED_RPC_HANDLER",
]
