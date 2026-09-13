"""Typed ``capture_state`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.capture_state_contract import (
    CaptureStateCollaborators,
    CaptureStateDocument,
    CaptureStateFailure,
    CaptureStateName,
    CaptureStateReadDocument,
    CaptureStateRequest,
    CaptureStateResult,
    DocumentName,
    make_capture_state_failure,
    make_capture_state_success,
    make_capture_state_uncertain,
)
from .capture_state_mutation import CaptureStateError, run_capture_state_native_mutation
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
class CaptureStateReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class CaptureStateInspection:
    """Read-only data captured after the native-owned recompute."""

    name: CaptureStateName
    label: str
    extra: object = None


def _failure(error: CaptureStateError, *, retry_safe: bool = True) -> CaptureStateFailure:
    return make_capture_state_failure(error.code, str(error), retry_safe=retry_safe)


def apply_capture_state(doc: CaptureStateDocument, request: CaptureStateRequest) -> CaptureStateReceipt:
    """Record which objects will be inspected after native recompute."""

    extra: list[object] = []
    if isinstance(request.object_names, list):
        extra = list(request.object_names)
    return CaptureStateReceipt(name=str(getattr(doc, "Name", "") or request.doc_name), item=doc, skipped=False, extra=extra)


def read_capture_state_result(doc: CaptureStateReadDocument, receipt: CaptureStateReceipt) -> CaptureStateInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise CaptureStateError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise CaptureStateError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return CaptureStateInspection(
        name=CaptureStateName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_capture_state_request(doc_name: object, object_names: object) -> CaptureStateRequest | CaptureStateFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(CaptureStateError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return CaptureStateRequest(
        doc_name=DocumentName(doc_name_value),
        object_names=object_names,
    )


@dataclass(slots=True)
class _CaptureStateExecution:
    collaborators: CaptureStateCollaborators
    request: CaptureStateRequest
    created: CaptureStateReceipt | None = None
    inspected: CaptureStateInspection | None = None

    def apply(self, doc: CaptureStateDocument) -> None:
        self.created = apply_capture_state(doc, self.request)

    def inspect(self, doc: CaptureStateReadDocument) -> None:
        if self.created is None:
            raise CaptureStateError(
                "INVALID_CAPTURE_STATE_RESULT",
                "capture_state did not return an identity receipt",
            )
        self.inspected = read_capture_state_result(doc, self.created)

    def run(self) -> CaptureStateResult:
        result = run_capture_state_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_capture_state_uncertain(
                "CAPTURE_STATE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_capture_state_success(doc=self.request.doc_name)


def run_capture_state(
    collaborators: CaptureStateCollaborators,
    doc_name: object, object_names: object,
) -> CaptureStateResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_capture_state_request(doc_name, object_names)
    if isinstance(request, dict):
        return request
    return _CaptureStateExecution(collaborators, request).run()


class _CaptureStateRpcFacade(Protocol):
    _cad_collaborators: CaptureStateCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_capture_state(
    self: _CaptureStateRpcFacade, doc_name: str, object_names: object = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_capture_state(collaborators, doc_name, object_names)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("capture_state", rpc_capture_state)


__all__ = [
    "CaptureStateCollaborators",
    "CaptureStateError",
    "CaptureStateInspection",
    "CaptureStateReceipt",
    "apply_capture_state",
    "build_capture_state_request",
    "read_capture_state_result",
    "rpc_capture_state",
    "run_capture_state",
    "TYPED_RPC_HANDLER",
]
