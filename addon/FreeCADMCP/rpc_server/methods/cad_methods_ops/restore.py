
"""Typed ``restore`` mutation."""
from __future__ import annotations

from .typed_rpc_support import (
    nonempty_string,
    optional_string,
)
from .typed_rpc_container_support import snapshot_ring

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from ...._shared.protocol.restore_contract import (
    RestoreCollaborators,
    RestoreDocument,
    RestoreFailure,
    RestoreName,
    RestoreReadDocument,
    RestoreRequest,
    RestoreResult,
    RestoreUncertain,
    DocumentName,
    make_restore_failure,
    make_restore_success,
    make_restore_uncertain,
)
from .restore_mutation import RestoreError, run_restore_native_mutation



@dataclass(frozen=True, slots=True)
class RestoreReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    snapshot_path: str | None = None
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
    """Resolve a snapshot identity without apply-time recompute or document reload."""

    store = snapshot_ring(doc)
    restored_id = ""
    snapshot_path: str | None = None
    doc_name = str(getattr(doc, "Name", "") or request.doc_name)
    rows = list(store)
    if request.snapshot_id is None:
        rows = list(reversed(rows))
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = row.get("id")
        if not isinstance(candidate, str):
            continue
        row_doc = row.get("doc")
        if isinstance(row_doc, str) and row_doc.strip() and row_doc not in {doc_name, str(request.doc_name)}:
            continue
        if request.snapshot_id is None or candidate == request.snapshot_id:
            restored_id = candidate
            path_value = row.get("path")
            snapshot_path = path_value if isinstance(path_value, str) and path_value.strip() else None
            break
    if not restored_id:
        raise RestoreError("SNAPSHOT_NOT_FOUND", "snapshot not found")
    return RestoreReceipt(
        name=restored_id,
        item=doc,
        snapshot_path=snapshot_path,
        skipped=False,
    )


def read_restore_result(doc: RestoreReadDocument, receipt: RestoreReceipt) -> RestoreInspection:
    """Confirm the admitted document is still present before post-commit restore."""

    doc_name = getattr(doc, "Name", None)
    if not isinstance(doc_name, str) or not doc_name.strip():
        raise RestoreError("CREATED_OBJECT_MISSING", "Document is missing after restore apply")
    count = len(snapshot_ring(doc))
    return RestoreInspection(
        name=RestoreName(receipt.name),
        label=doc_name,
        extra=count,
    )


def _try_document_reload(method: object, snapshot_path: str) -> Literal[True] | RestoreUncertain:
    if not callable(method):
        return True
    try:
        method(snapshot_path)
    except TypeError:
        try:
            method()
        except Exception as exc:
            return make_restore_uncertain(
                "RESTORE_FAILED",
                str(exc) or type(exc).__name__,
                committed=True,
            )
    except Exception as exc:
        return make_restore_uncertain(
            "RESTORE_FAILED",
            str(exc) or type(exc).__name__,
            committed=True,
        )
    return True


def _load_snapshot_after_commit(
    collaborators: RestoreCollaborators,
    doc_name: str,
    snapshot_path: str,
    stub_doc: object | None,
) -> Literal[True] | RestoreUncertain:
    import os

    if not os.path.isfile(snapshot_path):
        return make_restore_uncertain(
            "RESTORE_FAILED",
            "snapshot file is missing or unreadable",
            committed=True,
        )
    app = getattr(collaborators, "freecad", None)
    if app is not None:
        closer = getattr(app, "closeDocument", None)
        opener = getattr(app, "openDocument", None)
        if callable(closer) and callable(opener):
            try:
                closer(doc_name)
            except NameError:
                pass
            except Exception as exc:
                return make_restore_uncertain(
                    "RESTORE_FAILED",
                    str(exc) or type(exc).__name__,
                    committed=True,
                )
            try:
                reopened = opener(snapshot_path)
            except Exception as exc:
                return make_restore_uncertain(
                    "RESTORE_FAILED",
                    str(exc) or type(exc).__name__,
                    committed=True,
                )
            if reopened is None:
                return make_restore_uncertain(
                    "RESTORE_FAILED",
                    f"FreeCAD did not reopen {snapshot_path!r}",
                    committed=True,
                )
            return True
    live_doc: object | None = None
    if app is not None:
        getter = getattr(app, "getDocument", None)
        if callable(getter):
            try:
                live_doc = getter(doc_name)
            except Exception:
                live_doc = None
    if live_doc is None:
        live_doc = stub_doc
    if live_doc is None:
        return True
    restorer = getattr(live_doc, "restore", None)
    load_result = _try_document_reload(restorer, snapshot_path)
    if load_result is not True:
        return load_result
    if callable(restorer):
        return True
    loader = getattr(live_doc, "load", None)
    return _try_document_reload(loader, snapshot_path)


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
        count = self.inspected.extra
        if not isinstance(count, int):
            count = 0
        success = make_restore_success(
            restored_id=str(self.inspected.name),
            doc=str(self.request.doc_name),
            count=count,
        )
        receipt = self.created
        if receipt is None or not isinstance(receipt.snapshot_path, str) or not receipt.snapshot_path:
            return success
        load_result = _load_snapshot_after_commit(
            self.collaborators,
            str(self.request.doc_name),
            receipt.snapshot_path,
            receipt.item,
        )
        if load_result is not True:
            return load_result
        return success


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
