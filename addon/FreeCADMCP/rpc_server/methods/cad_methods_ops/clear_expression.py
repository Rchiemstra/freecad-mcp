
"""Typed ``clear_expression`` mutation."""
from __future__ import annotations

from .typed_rpc_support import (
    nonempty_string,
    object_label,
    object_name,
    require_object,
)

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.clear_expression_contract import (
        ClearExpressionCollaborators,
        ClearExpressionDocument,
        ClearExpressionFailure,
        ClearExpressionName,
        ClearExpressionReadDocument,
        ClearExpressionRequest,
        ClearExpressionResult,
        DocumentName,
        make_clear_expression_failure,
        make_clear_expression_success,
        make_clear_expression_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.clear_expression_contract import (
        ClearExpressionCollaborators,
        ClearExpressionDocument,
        ClearExpressionFailure,
        ClearExpressionName,
        ClearExpressionReadDocument,
        ClearExpressionRequest,
        ClearExpressionResult,
        DocumentName,
        make_clear_expression_failure,
        make_clear_expression_success,
        make_clear_expression_uncertain,
    )
from .clear_expression_mutation import ClearExpressionError, run_clear_expression_native_mutation



@dataclass(frozen=True, slots=True)
class ClearExpressionReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    prop_path: str
    skipped: bool = False


@dataclass(frozen=True, slots=True)
class ClearExpressionInspection:
    """Read-only data captured after the native-owned recompute."""

    name: ClearExpressionName
    label: str


def _failure(error: ClearExpressionError, *, retry_safe: bool = True) -> ClearExpressionFailure:
    return make_clear_expression_failure(error.code, str(error), retry_safe=retry_safe)


def _has_property(item: object, prop_path: str) -> bool:
    props = getattr(item, "PropertiesList", None)
    if isinstance(props, (list, tuple)) and prop_path in props:
        return True
    return hasattr(item, prop_path)


def apply_clear_expression(doc: ClearExpressionDocument, request: ClearExpressionRequest) -> ClearExpressionReceipt:
    """Clear an expression without recomputing."""

    item = require_object(doc, request.object_name, missing_code="OBJECT_NOT_FOUND", error=ClearExpressionError)
    if not _has_property(item, request.prop_path):
        raise ClearExpressionError(
            "OBJECT_NOT_FOUND",
            f"Property not found: {request.prop_path!r}",
        )
    clearer = getattr(item, "clearExpression", None)
    setter = getattr(item, "setExpression", None)
    try:
        if callable(clearer):
            clearer(request.prop_path)
        elif callable(setter):
            setter(request.prop_path, None)
        else:
            raise ClearExpressionError("INVALID_OBJECT", "object cannot clear expressions")
    except ClearExpressionError:
        raise
    except Exception as exc:
        raise ClearExpressionError("EXPRESSION_ERROR", str(exc) or type(exc).__name__) from exc
    return ClearExpressionReceipt(
        name=object_name(item) or request.object_name,
        item=item,
        prop_path=request.prop_path,
        skipped=False,
    )


def read_clear_expression_result(doc: ClearExpressionReadDocument, receipt: ClearExpressionReceipt) -> ClearExpressionInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise ClearExpressionError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise ClearExpressionError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")
    getter = getattr(located, "getExpression", None)
    if callable(getter):
        expression = getter(receipt.prop_path)
        if expression not in (None, ""):
            raise ClearExpressionError(
                "EXPRESSION_ERROR",
                f"Expression was not cleared on {receipt.prop_path!r}",
            )
    return ClearExpressionInspection(
        name=ClearExpressionName(receipt.name),
        label=object_label(located),
    )


def build_clear_expression_request(doc_name: object, object_name: object, prop_path: object) -> ClearExpressionRequest | ClearExpressionFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(ClearExpressionError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    object_name_value = nonempty_string(object_name, 'object_name')
    if object_name_value is None:
        return _failure(ClearExpressionError("INVALID_ARGUMENT", "object_name must be a nonempty string"))
    prop_path_value = nonempty_string(prop_path, 'prop_path')
    if prop_path_value is None:
        return _failure(ClearExpressionError("INVALID_ARGUMENT", "prop_path must be a nonempty string"))
    return ClearExpressionRequest(
        doc_name=DocumentName(doc_name_value),
        object_name=object_name_value,
        prop_path=prop_path_value,
    )


@dataclass(slots=True)
class _ClearExpressionExecution:
    collaborators: ClearExpressionCollaborators
    request: ClearExpressionRequest
    created: ClearExpressionReceipt | None = None
    inspected: ClearExpressionInspection | None = None

    def apply(self, doc: ClearExpressionDocument) -> None:
        self.created = apply_clear_expression(doc, self.request)

    def inspect(self, doc: ClearExpressionReadDocument) -> None:
        if self.created is None:
            raise ClearExpressionError(
                "INVALID_CLEAR_EXPRESSION_RESULT",
                "clear_expression did not return an identity receipt",
            )
        self.inspected = read_clear_expression_result(doc, self.created)

    def run(self) -> ClearExpressionResult:
        result = run_clear_expression_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_clear_expression_uncertain(
                "CLEAR_EXPRESSION_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_clear_expression_success(object=self.inspected.name, prop_path=self.request.prop_path)


def run_clear_expression(
    collaborators: ClearExpressionCollaborators,
    doc_name: object, object_name: object, prop_path: object,
) -> ClearExpressionResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_clear_expression_request(doc_name, object_name, prop_path)
    if isinstance(request, dict):
        return request
    return _ClearExpressionExecution(collaborators, request).run()


class _ClearExpressionRpcFacade(Protocol):
    _cad_collaborators: ClearExpressionCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_clear_expression(
    self: _ClearExpressionRpcFacade, doc_name: str, object_name: str, prop_path: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_clear_expression(collaborators, doc_name, object_name, prop_path)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("clear_expression", rpc_clear_expression)


__all__ = [
    "ClearExpressionCollaborators",
    "ClearExpressionError",
    "ClearExpressionInspection",
    "ClearExpressionReceipt",
    "apply_clear_expression",
    "build_clear_expression_request",
    "read_clear_expression_result",
    "rpc_clear_expression",
    "run_clear_expression",
    "TYPED_RPC_HANDLER",
]
