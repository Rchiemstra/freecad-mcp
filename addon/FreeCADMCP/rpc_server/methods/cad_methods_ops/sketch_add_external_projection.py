"""Typed ``sketch_add_external_projection`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sketch_add_external_projection_contract import (
    SketchAddExternalProjectionCollaborators,
    SketchAddExternalProjectionDocument,
    SketchAddExternalProjectionFailure,
    SketchAddExternalProjectionName,
    SketchAddExternalProjectionReadDocument,
    SketchAddExternalProjectionRequest,
    SketchAddExternalProjectionResult,
    DocumentName,
    make_sketch_add_external_projection_failure,
    make_sketch_add_external_projection_success,
    make_sketch_add_external_projection_uncertain,
)
from .sketch_add_external_projection_mutation import SketchAddExternalProjectionError, run_sketch_add_external_projection_native_mutation
from .typed_rpc_support import (
    add_named_object,
    add_to_container,
    as_bool,
    as_float,
    as_int,
    assign_attr,
    call_named,
    invoke,
    nonempty_string,
    object_label,
    object_name,
    object_type_id,
    optional_string,
    parse_ref,
    remove_from_container,
    require_object,
    resolve_if_exists,
    snapshot_ring
)


@dataclass(frozen=True, slots=True)
class SketchAddExternalProjectionReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class SketchAddExternalProjectionInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SketchAddExternalProjectionName
    label: str
    extra: object = None


def _failure(error: SketchAddExternalProjectionError, *, retry_safe: bool = True) -> SketchAddExternalProjectionFailure:
    return make_sketch_add_external_projection_failure(error.code, str(error), retry_safe=retry_safe)


def apply_sketch_add_external_projection(doc: SketchAddExternalProjectionDocument, request: SketchAddExternalProjectionRequest) -> SketchAddExternalProjectionReceipt:
    """Add external geometry to a sketch without recomputing."""

    sketch = require_object(doc, request.sketch_name, missing_code="OBJECT_NOT_FOUND", error=SketchAddExternalProjectionError)
    obj, sub = parse_ref(doc, request.source_ref, SketchAddExternalProjectionError)
    adder = getattr(sketch, "addExternal", None)
    if callable(adder):
        adder(object_name(obj), sub)
    return SketchAddExternalProjectionReceipt(name=object_name(sketch) or request.sketch_name, item=sketch, skipped=False)


def read_sketch_add_external_projection_result(doc: SketchAddExternalProjectionReadDocument, receipt: SketchAddExternalProjectionReceipt) -> SketchAddExternalProjectionInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise SketchAddExternalProjectionError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise SketchAddExternalProjectionError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return SketchAddExternalProjectionInspection(
        name=SketchAddExternalProjectionName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_sketch_add_external_projection_request(doc_name: object, sketch_name: object, source_ref: object, projection_mode: object, defining: object, allow_gui_geometry_loop: object) -> SketchAddExternalProjectionRequest | SketchAddExternalProjectionFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    sketch_name_value = nonempty_string(sketch_name, 'sketch_name')
    if sketch_name_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "sketch_name must be a nonempty string"))
    source_ref_value = nonempty_string(source_ref, 'source_ref')
    if source_ref_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "source_ref must be a nonempty string"))
    projection_mode_value = nonempty_string(projection_mode, 'projection_mode')
    if projection_mode_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "projection_mode must be a nonempty string"))
    defining_value = as_bool(defining, False)
    if defining_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "defining must be a boolean"))
    allow_gui_geometry_loop_value = as_bool(allow_gui_geometry_loop, False)
    if allow_gui_geometry_loop_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "allow_gui_geometry_loop must be a boolean"))
    return SketchAddExternalProjectionRequest(
        doc_name=DocumentName(doc_name_value),
        sketch_name=sketch_name_value,
        source_ref=source_ref_value,
        projection_mode=projection_mode_value,
        defining=defining_value,
        allow_gui_geometry_loop=allow_gui_geometry_loop_value,
    )


@dataclass(slots=True)
class _SketchAddExternalProjectionExecution:
    collaborators: SketchAddExternalProjectionCollaborators
    request: SketchAddExternalProjectionRequest
    created: SketchAddExternalProjectionReceipt | None = None
    inspected: SketchAddExternalProjectionInspection | None = None

    def apply(self, doc: SketchAddExternalProjectionDocument) -> None:
        self.created = apply_sketch_add_external_projection(doc, self.request)

    def inspect(self, doc: SketchAddExternalProjectionReadDocument) -> None:
        if self.created is None:
            raise SketchAddExternalProjectionError(
                "INVALID_SKETCH_ADD_EXTERNAL_PROJECTION_RESULT",
                "sketch_add_external_projection did not return an identity receipt",
            )
        self.inspected = read_sketch_add_external_projection_result(doc, self.created)

    def run(self) -> SketchAddExternalProjectionResult:
        result = run_sketch_add_external_projection_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sketch_add_external_projection_uncertain(
                "SKETCH_ADD_EXTERNAL_PROJECTION_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_sketch_add_external_projection_success(sketch_name=self.inspected.name)


def run_sketch_add_external_projection(
    collaborators: SketchAddExternalProjectionCollaborators,
    doc_name: object, sketch_name: object, source_ref: object, projection_mode: object, defining: object, allow_gui_geometry_loop: object,
) -> SketchAddExternalProjectionResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_sketch_add_external_projection_request(doc_name, sketch_name, source_ref, projection_mode, defining, allow_gui_geometry_loop)
    if isinstance(request, dict):
        return request
    return _SketchAddExternalProjectionExecution(collaborators, request).run()


class _SketchAddExternalProjectionRpcFacade(Protocol):
    _cad_collaborators: SketchAddExternalProjectionCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_sketch_add_external_projection(
    self: _SketchAddExternalProjectionRpcFacade, doc_name: str, sketch_name: str, source_ref: str, projection_mode: str = "auto", defining: bool = False, allow_gui_geometry_loop: bool = False,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sketch_add_external_projection(collaborators, doc_name, sketch_name, source_ref, projection_mode, defining, allow_gui_geometry_loop)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sketch_add_external_projection", rpc_sketch_add_external_projection)


__all__ = [
    "SketchAddExternalProjectionCollaborators",
    "SketchAddExternalProjectionError",
    "SketchAddExternalProjectionInspection",
    "SketchAddExternalProjectionReceipt",
    "apply_sketch_add_external_projection",
    "build_sketch_add_external_projection_request",
    "read_sketch_add_external_projection_result",
    "rpc_sketch_add_external_projection",
    "run_sketch_add_external_projection",
    "TYPED_RPC_HANDLER",
]
