
"""Typed ``sketch_add_external_projection`` mutation."""
from __future__ import annotations

from .typed_rpc_support import (
    as_bool,
    invoke,
    nonempty_string,
    object_label,
    object_name,
    parse_ref,
    require_object,
)

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
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
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.sketch_add_external_projection_contract import (
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


_ALLOWED_PROJECTION_MODES = frozenset({"auto", "edge", "face", "point"})


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


def _external_geometry_count(sketch: object) -> int:
    geometry = getattr(sketch, "ExternalGeometry", None)
    if geometry is None:
        return 0
    try:
        return len(list(geometry))
    except Exception:
        return 0


def _call_add_external(adder: object, sketch: object, source_obj: object, sub: str, defining: bool) -> None:
    source_name = object_name(source_obj)
    try:
        invoke(adder, source_name, sub)
    except Exception as exc:
        raise SketchAddExternalProjectionError("SKETCH_ADD_EXTERNAL_PROJECTION_FAILED", str(exc))


def apply_sketch_add_external_projection(doc: SketchAddExternalProjectionDocument, request: SketchAddExternalProjectionRequest) -> SketchAddExternalProjectionReceipt:
    """Add external geometry to a sketch without recomputing."""

    sketch = require_object(doc, request.sketch_name, missing_code="OBJECT_NOT_FOUND", error=SketchAddExternalProjectionError)
    source_obj, sub = parse_ref(doc, request.source_ref, SketchAddExternalProjectionError)
    adder = getattr(sketch, "addExternal", None)
    if not callable(adder):
        raise SketchAddExternalProjectionError(
            "INVALID_OBJECT",
            f"Sketch does not support addExternal: {request.sketch_name!r}",
        )
    before_count = _external_geometry_count(sketch)
    _call_add_external(adder, sketch, source_obj, sub, request.defining)
    return SketchAddExternalProjectionReceipt(
        name=object_name(sketch) or request.sketch_name,
        item=sketch,
        skipped=False,
        extra={"external_before": before_count},
    )


def read_sketch_add_external_projection_result(doc: SketchAddExternalProjectionReadDocument, receipt: SketchAddExternalProjectionReceipt) -> SketchAddExternalProjectionInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise SketchAddExternalProjectionError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise SketchAddExternalProjectionError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra if isinstance(receipt.extra, dict) else {}
    after_count = _external_geometry_count(located)
    if after_count == 0:
        raise SketchAddExternalProjectionError(
            "SKETCH_ADD_EXTERNAL_FAILED",
            "External geometry is empty after recompute",
        )

    return SketchAddExternalProjectionInspection(
        name=SketchAddExternalProjectionName(receipt.name),
        label=object_label(located),
        extra={**extra, "external_after": after_count},
    )


def build_sketch_add_external_projection_request(doc_name: object, sketch_name: object, source_ref: object, projection_mode: object, defining: object, allow_gui_geometry_loop: object) -> SketchAddExternalProjectionRequest | SketchAddExternalProjectionFailure:
    doc_name_value = nonempty_string(doc_name, "doc_name")
    if doc_name_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    sketch_name_value = nonempty_string(sketch_name, "sketch_name")
    if sketch_name_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "sketch_name must be a nonempty string"))
    source_ref_value = nonempty_string(source_ref, "source_ref")
    if source_ref_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "source_ref must be a nonempty string"))
    projection_mode_value = nonempty_string(projection_mode, "projection_mode")
    if projection_mode_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "projection_mode must be a nonempty string"))
    if projection_mode_value not in _ALLOWED_PROJECTION_MODES:
        return _failure(
            SketchAddExternalProjectionError(
                "INVALID_ARGUMENT",
                "projection_mode must be one of: auto, edge, face, point",
            )
        )
    defining_value = as_bool(defining, False)
    if defining_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "defining must be a boolean"))
    allow_gui_geometry_loop_value = as_bool(allow_gui_geometry_loop, False)
    if allow_gui_geometry_loop_value is None:
        return _failure(SketchAddExternalProjectionError("INVALID_ARGUMENT", "allow_gui_geometry_loop must be a boolean"))
    if allow_gui_geometry_loop_value is not True:
        return _failure(
            SketchAddExternalProjectionError(
                "gui_geometry_loop_opt_in_required",
                "sketch_add_external_projection requires allow_gui_geometry_loop=true",
            )
        )
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
