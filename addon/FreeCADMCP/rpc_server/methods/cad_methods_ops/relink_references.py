"""Typed ``relink_references`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.relink_references_contract import (
    RelinkReferencesCollaborators,
    RelinkReferencesDocument,
    RelinkReferencesFailure,
    RelinkReferencesName,
    RelinkReferencesReadDocument,
    RelinkReferencesRequest,
    RelinkReferencesResult,
    DocumentName,
    make_relink_references_failure,
    make_relink_references_success,
    make_relink_references_uncertain,
)
from .relink_references_mutation import RelinkReferencesError, run_relink_references_native_mutation
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
class RelinkReferencesReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class RelinkReferencesInspection:
    """Read-only data captured after the native-owned recompute."""

    name: RelinkReferencesName
    label: str
    extra: object = None


def _failure(error: RelinkReferencesError, *, retry_safe: bool = True) -> RelinkReferencesFailure:
    return make_relink_references_failure(error.code, str(error), retry_safe=retry_safe)


def apply_relink_references(doc: RelinkReferencesDocument, request: RelinkReferencesRequest) -> RelinkReferencesReceipt:
    """Retarget link properties without recomputing."""

    source = require_object(doc, request.from_obj, missing_code="OBJECT_NOT_FOUND", error=RelinkReferencesError)
    target = require_object(doc, request.to_obj, missing_code="OBJECT_NOT_FOUND", error=RelinkReferencesError)
    objects = getattr(doc, "Objects", None)
    if not isinstance(objects, list):
        objects = []
    changed = 0
    for item in objects:
        props = getattr(item, "PropertiesList", None)
        if not isinstance(props, list):
            continue
        for prop in props:
            if not isinstance(prop, str):
                continue
            type_id = ""
            getter = getattr(item, "getTypeIdOfProperty", None)
            if callable(getter):
                try:
                    raw_type = getter(prop)
                except Exception:
                    raw_type = ""
                type_id = raw_type if isinstance(raw_type, str) else ""
            if "Link" not in type_id:
                continue
            try:
                current = getattr(item, prop)
            except Exception:
                continue
            if current is source:
                try:
                    setattr(item, prop, target)
                    changed += 1
                except Exception:
                    continue
    return RelinkReferencesReceipt(name=request.to_obj, item=target, skipped=False, extra=changed)


def read_relink_references_result(doc: RelinkReferencesReadDocument, receipt: RelinkReferencesReceipt) -> RelinkReferencesInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise RelinkReferencesError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise RelinkReferencesError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return RelinkReferencesInspection(
        name=RelinkReferencesName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_relink_references_request(doc_name: object, from_obj: object, to_obj: object) -> RelinkReferencesRequest | RelinkReferencesFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(RelinkReferencesError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    from_obj_value = nonempty_string(from_obj, 'from_obj')
    if from_obj_value is None:
        return _failure(RelinkReferencesError("INVALID_ARGUMENT", "from_obj must be a nonempty string"))
    to_obj_value = nonempty_string(to_obj, 'to_obj')
    if to_obj_value is None:
        return _failure(RelinkReferencesError("INVALID_ARGUMENT", "to_obj must be a nonempty string"))
    return RelinkReferencesRequest(
        doc_name=DocumentName(doc_name_value),
        from_obj=from_obj_value,
        to_obj=to_obj_value,
    )


@dataclass(slots=True)
class _RelinkReferencesExecution:
    collaborators: RelinkReferencesCollaborators
    request: RelinkReferencesRequest
    created: RelinkReferencesReceipt | None = None
    inspected: RelinkReferencesInspection | None = None

    def apply(self, doc: RelinkReferencesDocument) -> None:
        self.created = apply_relink_references(doc, self.request)

    def inspect(self, doc: RelinkReferencesReadDocument) -> None:
        if self.created is None:
            raise RelinkReferencesError(
                "INVALID_RELINK_REFERENCES_RESULT",
                "relink_references did not return an identity receipt",
            )
        self.inspected = read_relink_references_result(doc, self.created)

    def run(self) -> RelinkReferencesResult:
        result = run_relink_references_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_relink_references_uncertain(
                "RELINK_REFERENCES_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_relink_references_success(from_obj=self.request.from_obj, to_obj=self.request.to_obj)


def run_relink_references(
    collaborators: RelinkReferencesCollaborators,
    doc_name: object, from_obj: object, to_obj: object,
) -> RelinkReferencesResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_relink_references_request(doc_name, from_obj, to_obj)
    if isinstance(request, dict):
        return request
    return _RelinkReferencesExecution(collaborators, request).run()


class _RelinkReferencesRpcFacade(Protocol):
    _cad_collaborators: RelinkReferencesCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_relink_references(
    self: _RelinkReferencesRpcFacade, doc_name: str, from_obj: str, to_obj: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_relink_references(collaborators, doc_name, from_obj, to_obj)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("relink_references", rpc_relink_references)


__all__ = [
    "RelinkReferencesCollaborators",
    "RelinkReferencesError",
    "RelinkReferencesInspection",
    "RelinkReferencesReceipt",
    "apply_relink_references",
    "build_relink_references_request",
    "read_relink_references_result",
    "rpc_relink_references",
    "run_relink_references",
    "TYPED_RPC_HANDLER",
]
