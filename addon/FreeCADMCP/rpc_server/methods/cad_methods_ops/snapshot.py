"""Typed ``snapshot`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.snapshot_contract import (
    SnapshotCollaborators,
    SnapshotDocument,
    SnapshotFailure,
    SnapshotName,
    SnapshotReadDocument,
    SnapshotRequest,
    SnapshotResult,
    DocumentName,
    make_snapshot_failure,
    make_snapshot_success,
    make_snapshot_uncertain,
)
from .snapshot_mutation import SnapshotError, run_snapshot_native_mutation
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
class SnapshotReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class SnapshotInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SnapshotName
    label: str
    extra: object = None


def _failure(error: SnapshotError, *, retry_safe: bool = True) -> SnapshotFailure:
    return make_snapshot_failure(error.code, str(error), retry_safe=retry_safe)


def apply_snapshot(doc: SnapshotDocument, request: SnapshotRequest) -> SnapshotReceipt:
    """Save a document copy without recomputing."""

    import os
    import tempfile
    import time

    saver = getattr(doc, "saveCopy", None)
    if not callable(saver):
        raise SnapshotError("INVALID_DOCUMENT", "document cannot save a snapshot")
    handle, path = tempfile.mkstemp(suffix=".FCStd", prefix="mcp_snap_")
    os.close(handle)
    try:
        saver(path)
    except Exception as exc:
        raise SnapshotError("SNAPSHOT_FAILED", str(exc) or type(exc).__name__) from exc
    snapshot_id = "snap-" + str(int(time.time() * 1000))
    store = snapshot_ring(doc)
    store.append({"id": snapshot_id, "path": path, "doc": str(getattr(doc, "Name", "") or request.doc_name)})
    while len(store) > 5:
        store.pop(0)
    return SnapshotReceipt(name=snapshot_id, item=doc, skipped=False, extra=len(store))


def read_snapshot_result(doc: SnapshotReadDocument, receipt: SnapshotReceipt) -> SnapshotInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise SnapshotError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise SnapshotError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return SnapshotInspection(
        name=SnapshotName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_snapshot_request(doc_name: object) -> SnapshotRequest | SnapshotFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(SnapshotError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return SnapshotRequest(
        doc_name=DocumentName(doc_name_value),
    )


@dataclass(slots=True)
class _SnapshotExecution:
    collaborators: SnapshotCollaborators
    request: SnapshotRequest
    created: SnapshotReceipt | None = None
    inspected: SnapshotInspection | None = None

    def apply(self, doc: SnapshotDocument) -> None:
        self.created = apply_snapshot(doc, self.request)

    def inspect(self, doc: SnapshotReadDocument) -> None:
        if self.created is None:
            raise SnapshotError(
                "INVALID_SNAPSHOT_RESULT",
                "snapshot did not return an identity receipt",
            )
        self.inspected = read_snapshot_result(doc, self.created)

    def run(self) -> SnapshotResult:
        result = run_snapshot_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_snapshot_uncertain(
                "SNAPSHOT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_snapshot_success(snapshot_id=self.inspected.name, doc=self.request.doc_name)


def run_snapshot(
    collaborators: SnapshotCollaborators,
    doc_name: object,
) -> SnapshotResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_snapshot_request(doc_name)
    if isinstance(request, dict):
        return request
    return _SnapshotExecution(collaborators, request).run()


class _SnapshotRpcFacade(Protocol):
    _cad_collaborators: SnapshotCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_snapshot(
    self: _SnapshotRpcFacade, doc_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_snapshot(collaborators, doc_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("snapshot", rpc_snapshot)


__all__ = [
    "SnapshotCollaborators",
    "SnapshotError",
    "SnapshotInspection",
    "SnapshotReceipt",
    "apply_snapshot",
    "build_snapshot_request",
    "read_snapshot_result",
    "rpc_snapshot",
    "run_snapshot",
    "TYPED_RPC_HANDLER",
]
