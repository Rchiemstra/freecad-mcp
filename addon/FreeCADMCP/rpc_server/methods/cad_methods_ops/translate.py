"""Typed ``translate`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.translate_contract import (
        ObjectName,
        DocumentName,
        TranslateCollaborators,
        TranslateFailure,
        TranslateRequest,
        TranslateResult,
        MutationDocument,
        MutationObject,
        MutationReadDocument,
        make_translate_failure,
        make_translate_success,
        make_translate_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.translate_contract import (
        ObjectName,
        DocumentName,
        TranslateCollaborators,
        TranslateFailure,
        TranslateRequest,
        TranslateResult,
        MutationDocument,
        MutationObject,
        MutationReadDocument,
        make_translate_failure,
        make_translate_success,
        make_translate_uncertain,
    )
from .typed_runtime import as_float, as_int, as_str
from . import measure_io_actions
from .translate_mutation import TranslateError, run_translate_native_mutation


@dataclass(frozen=True, slots=True)
class TranslateReceipt:
    payload: dict[str, object]
    obj: MutationObject | None
    expected: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class TranslateInspection:
    payload: dict[str, object]


def _failure(error: TranslateError, *, retry_safe: bool = True) -> TranslateFailure:
    return make_translate_failure(error.code, str(error), retry_safe=retry_safe)


def build_translate_request(
    doc_name: object, obj_name: object, dx: object, dy: object, dz: object
) -> TranslateRequest | TranslateFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(TranslateError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(obj_name, str) or not obj_name.strip():
        return _failure(TranslateError("INVALID_ARGUMENT", "obj_name must be a nonempty string"))
    if isinstance(dx, bool) or not isinstance(dx, (int, float)):
        return _failure(TranslateError("INVALID_ARGUMENT", "dx must be a number"))
    if isinstance(dy, bool) or not isinstance(dy, (int, float)):
        return _failure(TranslateError("INVALID_ARGUMENT", "dy must be a number"))
    if isinstance(dz, bool) or not isinstance(dz, (int, float)):
        return _failure(TranslateError("INVALID_ARGUMENT", "dz must be a number"))
    request = TranslateRequest(
        doc_name=DocumentName(doc_name),
        obj_name=ObjectName(obj_name),
        dx=float(dx),
        dy=float(dy),
        dz=float(dz)
    )
    return request


@dataclass(slots=True)
class _TranslateExecution:
    collaborators: TranslateCollaborators
    request: TranslateRequest
    created: TranslateReceipt | None = None
    inspected: TranslateInspection | None = None

    def apply(self, doc: MutationDocument) -> None:
        self.created = apply_translate(doc, self.request)

    def inspect(self, doc: MutationReadDocument) -> None:
        if self.created is None:
            raise TranslateError(
                "INVALID_TRANSLATE_RESULT",
                "translate did not return an identity receipt",
            )
        self.inspected = read_translate_result(doc, self.created, self.request)

    def run(self) -> TranslateResult:
        result = run_translate_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_translate_uncertain(
                "TRANSLATE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected translate result",
                committed=True,
            )
        payload = self.inspected.payload
        return make_translate_success(
            object=as_str(payload["object"]), label=as_str(payload["label"])
        )


def _snapshot_placement_base(obj: object) -> dict[str, object]:
    placement = getattr(obj, "Placement", None)
    if placement is None:
        raise TranslateError("CREATED_OBJECT_INVALID", "Object has no Placement after apply")
    base = getattr(placement, "Base", None)
    if base is None:
        raise TranslateError("CREATED_OBJECT_INVALID", "Object Placement has no Base after apply")
    return {
        "x": as_float(getattr(base, "x", 0.0)),
        "y": as_float(getattr(base, "y", 0.0)),
        "z": as_float(getattr(base, "z", 0.0)),
    }


def _placement_base_matches(obj: object, expected: dict[str, object]) -> None:
    placement = getattr(obj, "Placement", None)
    if placement is None:
        raise TranslateError("CREATED_OBJECT_INVALID", "Object has no Placement after recompute")
    base = getattr(placement, "Base", None)
    if base is None:
        raise TranslateError("CREATED_OBJECT_INVALID", "Object Placement has no Base after recompute")
    for key in ("x", "y", "z"):
        actual = as_float(getattr(base, key, 0.0))
        target = as_float(expected[key])
        if abs(actual - target) > 1e-6:
            raise TranslateError(
                "CREATED_OBJECT_INVALID",
                f"Placement Base {key} mismatch after recompute",
            )


def apply_translate(doc: MutationDocument, request: TranslateRequest) -> TranslateReceipt:
    """Apply translate without recomputing or managing a transaction."""

    payload = measure_io_actions.translate(doc, request.obj_name, request.dx, request.dy, request.dz)
    target = payload.get("object")
    found = doc.getObject(str(target)) if isinstance(target, str) else None
    expected = _snapshot_placement_base(found) if found is not None else None
    return TranslateReceipt(payload=dict(payload), obj=found, expected=expected)



def read_translate_result(
    doc: MutationReadDocument, receipt: TranslateReceipt, request: TranslateRequest
) -> TranslateInspection:
    key = "object"
    name = receipt.payload.get(key)
    if not isinstance(name, str) or not name.strip():
        raise TranslateError("INVALID_TRANSLATE_RESULT", "missing created identity")
    obj = doc.getObject(name)
    if obj is None:
        raise TranslateError("CREATED_OBJECT_MISSING", f"Created object is missing: {name!r}")
    if receipt.obj is not None and obj is not receipt.obj:
        raise TranslateError("CREATED_OBJECT_REPLACED", f"Created object was replaced: {name!r}")
    if receipt.expected is None:
        raise TranslateError("CREATED_OBJECT_INVALID", "Missing post-apply Placement snapshot")
    _placement_base_matches(obj, receipt.expected)

    payload = dict(receipt.payload)
    if hasattr(obj, "Label") and "label" in payload:
        payload["label"] = str(obj.Label)
    return TranslateInspection(payload=payload)



def run_translate(
    collaborators: TranslateCollaborators,
    doc_name: str, obj_name: str, dx: float, dy: float, dz: float,
) -> TranslateResult:
    """Run translate through apply, recompute, inspection, and commit."""

    request = build_translate_request(doc_name, obj_name, dx, dy, dz)
    if isinstance(request, dict):
        return request
    return _TranslateExecution(collaborators, request).run()


class _TranslateRpcFacade(Protocol):
    _cad_collaborators: TranslateCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_translate(
    self: _TranslateRpcFacade,
    doc_name: str, obj_name: str, dx: float, dy: float, dz: float,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_translate(collaborators, doc_name, obj_name, dx, dy, dz)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("translate", rpc_translate)


__all__ = [
    "TranslateCollaborators",
    "TranslateError",
    "TranslateInspection",
    "TranslateReceipt",
    "apply_translate",
    "build_translate_request",
    "read_translate_result",
    "rpc_translate",
    "run_translate",
    "TYPED_RPC_HANDLER",
]
