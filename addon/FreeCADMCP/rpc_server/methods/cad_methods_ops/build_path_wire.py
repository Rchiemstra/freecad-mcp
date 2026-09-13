"""Typed ``build_path_wire`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.build_path_wire_contract import (
    BuildPathWireCollaborators,
    BuildPathWireDocument,
    BuildPathWireFailure,
    BuildPathWireName,
    BuildPathWireReadDocument,
    BuildPathWireRequest,
    BuildPathWireResult,
    DocumentName,
    make_build_path_wire_failure,
    make_build_path_wire_success,
    make_build_path_wire_uncertain,
)
from .build_path_wire_mutation import BuildPathWireError, run_build_path_wire_native_mutation
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
class BuildPathWireReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class BuildPathWireInspection:
    """Read-only data captured after the native-owned recompute."""

    name: BuildPathWireName
    label: str
    extra: object = None


def _failure(error: BuildPathWireError, *, retry_safe: bool = True) -> BuildPathWireFailure:
    return make_build_path_wire_failure(error.code, str(error), retry_safe=retry_safe)


def apply_build_path_wire(doc: BuildPathWireDocument, request: BuildPathWireRequest) -> BuildPathWireReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    if not request.segments:
        raise BuildPathWireError("INVALID_ARGUMENT", "No path segments supplied")

    skipped = resolve_if_exists(doc, request.wire_name, request.if_exists, error=BuildPathWireError)
    if skipped is not None:
        return BuildPathWireReceipt(name=object_name(skipped) or request.wire_name, item=skipped, skipped=True)
    created = add_named_object(doc, 'Part::Feature', request.wire_name)
    return BuildPathWireReceipt(name=object_name(created) or request.wire_name, item=created, skipped=False)


def read_build_path_wire_result(doc: BuildPathWireReadDocument, receipt: BuildPathWireReceipt) -> BuildPathWireInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise BuildPathWireError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise BuildPathWireError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    type_id = object_type_id(located)
    if 'Part::Feature' not in type_id and type_id:
        raise BuildPathWireError("CREATED_OBJECT_WRONG_TYPE", f"Created object is not Part::Feature: {receipt.name!r}")

    extra = receipt.extra

    return BuildPathWireInspection(
        name=BuildPathWireName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_build_path_wire_request(doc_name: object, wire_name: object, segments: object, tolerance_mm: object, container: object, if_exists: object) -> BuildPathWireRequest | BuildPathWireFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(BuildPathWireError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    wire_name_value = nonempty_string(wire_name, 'wire_name')
    if wire_name_value is None:
        return _failure(BuildPathWireError("INVALID_ARGUMENT", "wire_name must be a nonempty string"))
    if not isinstance(segments, list):
        return _failure(BuildPathWireError("INVALID_ARGUMENT", "segments must be a list"))
    tolerance_mm_value = as_float(tolerance_mm, 0.5)
    if tolerance_mm_value is None:
        return _failure(BuildPathWireError("INVALID_ARGUMENT", "tolerance_mm must be a number"))
    if container is None:
        container_value: str | None = None
    else:
        container_value = optional_string(container)
        if container_value is None:
            return _failure(BuildPathWireError("INVALID_ARGUMENT", "container must be a nonempty string or None"))
    if_exists_value = nonempty_string(if_exists, 'if_exists')
    if if_exists_value is None:
        return _failure(BuildPathWireError("INVALID_ARGUMENT", "if_exists must be a nonempty string"))
    if if_exists not in {"error", "skip", "replace"}:
        return _failure(BuildPathWireError("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace"))
    return BuildPathWireRequest(
        doc_name=DocumentName(doc_name_value),
        wire_name=wire_name_value,
        segments=segments,
        tolerance_mm=tolerance_mm_value,
        container=container_value,
        if_exists=if_exists_value,
    )


@dataclass(slots=True)
class _BuildPathWireExecution:
    collaborators: BuildPathWireCollaborators
    request: BuildPathWireRequest
    created: BuildPathWireReceipt | None = None
    inspected: BuildPathWireInspection | None = None

    def apply(self, doc: BuildPathWireDocument) -> None:
        self.created = apply_build_path_wire(doc, self.request)

    def inspect(self, doc: BuildPathWireReadDocument) -> None:
        if self.created is None:
            raise BuildPathWireError(
                "INVALID_BUILD_PATH_WIRE_RESULT",
                "build_path_wire did not return an identity receipt",
            )
        self.inspected = read_build_path_wire_result(doc, self.created)

    def run(self) -> BuildPathWireResult:
        result = run_build_path_wire_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_build_path_wire_uncertain(
                "BUILD_PATH_WIRE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_build_path_wire_success(wire_name=self.inspected.name)


def run_build_path_wire(
    collaborators: BuildPathWireCollaborators,
    doc_name: object, wire_name: object, segments: object, tolerance_mm: object, container: object, if_exists: object,
) -> BuildPathWireResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_build_path_wire_request(doc_name, wire_name, segments, tolerance_mm, container, if_exists)
    if isinstance(request, dict):
        return request
    return _BuildPathWireExecution(collaborators, request).run()


class _BuildPathWireRpcFacade(Protocol):
    _cad_collaborators: BuildPathWireCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_build_path_wire(
    self: _BuildPathWireRpcFacade, doc_name: str, wire_name: str, segments: object, tolerance_mm: float = 0.5, container: str | None = None, if_exists: str = "error",
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_build_path_wire(collaborators, doc_name, wire_name, segments, tolerance_mm, container, if_exists)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("build_path_wire", rpc_build_path_wire)


__all__ = [
    "BuildPathWireCollaborators",
    "BuildPathWireError",
    "BuildPathWireInspection",
    "BuildPathWireReceipt",
    "apply_build_path_wire",
    "build_build_path_wire_request",
    "read_build_path_wire_result",
    "rpc_build_path_wire",
    "run_build_path_wire",
    "TYPED_RPC_HANDLER",
]
