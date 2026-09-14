"""Typed ``snapshot`` mutation."""

from __future__ import annotations

import os
import tempfile
import time
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
    nonempty_string,
    snapshot_ring,
)


@dataclass(frozen=True, slots=True)
class SnapshotReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    snapshot_path: str | None = None
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


def _unlink_snapshot_path(path: object) -> None:
    if isinstance(path, str) and path:
        try:
            os.remove(path)
        except OSError:
            pass


def _undo_snapshot_receipt(doc: object | None, receipt: SnapshotReceipt) -> None:
    if doc is None:
        return
    store = snapshot_ring(doc)
    for index, row in enumerate(store):
        if isinstance(row, dict) and row.get("id") == receipt.name:
            store.pop(index)
            break
    _unlink_snapshot_path(receipt.snapshot_path)


def _undo_ring_appended_since(doc: object | None, length_before: int) -> None:
    if doc is None:
        return
    store = snapshot_ring(doc)
    while len(store) > length_before:
        evicted = store.pop()
        if isinstance(evicted, dict):
            _unlink_snapshot_path(evicted.get("path"))


def _trim_snapshot_ring(doc: object | None, max_size: int = 5) -> None:
    if doc is None:
        return
    store = snapshot_ring(doc)
    while len(store) > max_size:
        evicted = store.pop(0)
        if isinstance(evicted, dict):
            _unlink_snapshot_path(evicted.get("path"))


def apply_snapshot(doc: SnapshotDocument, request: SnapshotRequest) -> SnapshotReceipt:
    """Save a document copy without recomputing."""

    saver = getattr(doc, "saveCopy", None)
    if not callable(saver):
        raise SnapshotError("INVALID_DOCUMENT", "document cannot save a snapshot")
    handle, path = tempfile.mkstemp(suffix=".FCStd", prefix="mcp_snap_")
    os.close(handle)
    try:
        saver(path)
    except Exception as exc:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise SnapshotError("SNAPSHOT_FAILED", str(exc) or type(exc).__name__) from exc
    snapshot_id = "snap-" + str(int(time.time() * 1000))
    store = snapshot_ring(doc)
    store.append({"id": snapshot_id, "path": path, "doc": str(getattr(doc, "Name", "") or request.doc_name)})
    return SnapshotReceipt(
        name=snapshot_id,
        item=doc,
        snapshot_path=path,
        skipped=False,
        extra=len(store),
    )


def read_snapshot_result(doc: SnapshotReadDocument, receipt: SnapshotReceipt) -> SnapshotInspection:
    """Verify the snapshot ring entry and file exist after native recompute."""

    store = snapshot_ring(doc)
    found = False
    for row in store:
        if isinstance(row, dict) and row.get("id") == receipt.name:
            found = True
            path = row.get("path")
            if not isinstance(path, str) or not os.path.isfile(path):
                raise SnapshotError("SNAPSHOT_FILE_MISSING", f"Snapshot file is missing: {receipt.name!r}")
            break
    if not found:
        raise SnapshotError("SNAPSHOT_NOT_FOUND", f"Snapshot is missing from the ring: {receipt.name!r}")
    return SnapshotInspection(
        name=SnapshotName(receipt.name),
        label=receipt.name,
        extra=len(store),
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
        ring_len_before = len(snapshot_ring(doc))
        try:
            self.created = apply_snapshot(doc, self.request)
        except Exception:
            _undo_ring_appended_since(doc, ring_len_before)
            raise

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
            if self.created is not None:
                _undo_snapshot_receipt(self.created.item, self.created)
            return result
        if self.inspected is None:
            return make_snapshot_uncertain(
                "SNAPSHOT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        if self.created is not None:
            _trim_snapshot_ring(self.created.item, max_size=5)
        count = self.inspected.extra
        if not isinstance(count, int):
            count = 0
        return make_snapshot_success(
            snapshot_id=str(self.inspected.name),
            doc=str(self.request.doc_name),
            count=count,
        )


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
