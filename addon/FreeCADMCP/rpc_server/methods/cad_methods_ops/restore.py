"""Typed ``restore`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.restore_contract import (
    RestoreCollaborators,
    RestoreDocument,
    RestoreFailure,
    RestoreName,
    RestoreReadDocument,
    RestoreRequest,
    RestoreResult,
    DocumentName,
    make_restore_failure,
    make_restore_success,
    make_restore_uncertain,
)
from .restore_mutation import RestoreError, run_restore_native_mutation
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
class RestoreReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class RestoreInspection:
    """Read-only data captured after the native-owned recompute."""

    name: RestoreName
    label: str
    extra: object = None


def _failure(error: RestoreError, *, retry_safe: bool = True) -> RestoreFailure:
    return make_restore_failure(error.code, str(error), retry_safe=retry_safe)


def apply_restore(doc: RestoreDocument, request: RestoreRequest) -> RestoreReceipt:
    """Restore a snapshot identity without apply-time recompute."""

    store = snapshot_ring(doc)
    restored = ""
    rows = list(store)
    if request.snapshot_id is None:
        rows = list(reversed(rows))
    for row in rows:
        candidate: object | None = None
        if isinstance(row, dict):
            candidate = row.get("id")
        if not isinstance(candidate, str):
            continue
        if request.snapshot_id is None or candidate == request.snapshot_id:
            restored = candidate
            break
    if not restored:
        raise RestoreError("SNAPSHOT_NOT_FOUND", "snapshot not found")
    return RestoreReceipt(name=restored, item=doc, skipped=False)


def read_restore_result(doc: RestoreReadDocument, receipt: RestoreReceipt) -> RestoreInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise RestoreError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise RestoreError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return RestoreInspection(
        name=RestoreName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_restore_request(doc_name: object, snapshot_id: object) -> RestoreRequest | RestoreFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(RestoreError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if snapshot_id is None:
        snapshot_id_value: str | None = None
    else:
        snapshot_id_value = optional_string(snapshot_id)
        if snapshot_id_value is None:
            return _failure(RestoreError("INVALID_ARGUMENT", "snapshot_id must be a nonempty string or None"))
    return RestoreRequest(
        doc_name=DocumentName(doc_name_value),
        snapshot_id=snapshot_id_value,
    )


@dataclass(slots=True)
class _RestoreExecution:
    collaborators: RestoreCollaborators
    request: RestoreRequest
    created: RestoreReceipt | None = None
    inspected: RestoreInspection | None = None

    def apply(self, doc: RestoreDocument) -> None:
        self.created = apply_restore(doc, self.request)

    def inspect(self, doc: RestoreReadDocument) -> None:
        if self.created is None:
            raise RestoreError(
                "INVALID_RESTORE_RESULT",
                "restore did not return an identity receipt",
            )
        self.inspected = read_restore_result(doc, self.created)

    def run(self) -> RestoreResult:
        result = run_restore_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_restore_uncertain(
                "RESTORE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_restore_success(restored_id=self.inspected.name, doc=self.request.doc_name)


def run_restore(
    collaborators: RestoreCollaborators,
    doc_name: object, snapshot_id: object,
) -> RestoreResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_restore_request(doc_name, snapshot_id)
    if isinstance(request, dict):
        return request
    return _RestoreExecution(collaborators, request).run()


class _RestoreRpcFacade(Protocol):
    _cad_collaborators: RestoreCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_restore(
    self: _RestoreRpcFacade, doc_name: str, snapshot_id: str | None = None,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_restore(collaborators, doc_name, snapshot_id)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("restore", rpc_restore)


__all__ = [
    "RestoreCollaborators",
    "RestoreError",
    "RestoreInspection",
    "RestoreReceipt",
    "apply_restore",
    "build_restore_request",
    "read_restore_result",
    "rpc_restore",
    "run_restore",
    "TYPED_RPC_HANDLER",
]
