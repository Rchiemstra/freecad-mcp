"""Typed ``set_expression`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.set_expression_contract import (
    SetExpressionCollaborators,
    SetExpressionDocument,
    SetExpressionFailure,
    SetExpressionName,
    SetExpressionReadDocument,
    SetExpressionRequest,
    SetExpressionResult,
    DocumentName,
    make_set_expression_failure,
    make_set_expression_success,
    make_set_expression_uncertain,
)
from .set_expression_mutation import SetExpressionError, run_set_expression_native_mutation
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
class SetExpressionReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    prop_path: str
    expression: str
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class SetExpressionInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SetExpressionName
    label: str
    extra: object = None


def _failure(error: SetExpressionError, *, retry_safe: bool = True) -> SetExpressionFailure:
    return make_set_expression_failure(error.code, str(error), retry_safe=retry_safe)


def apply_set_expression(doc: SetExpressionDocument, request: SetExpressionRequest) -> SetExpressionReceipt:
    """Bind an expression without recomputing."""

    item = require_object(doc, request.object_name, missing_code="OBJECT_NOT_FOUND", error=SetExpressionError)
    setter = getattr(item, "setExpression", None)
    if not callable(setter):
        raise SetExpressionError("INVALID_OBJECT", "object cannot set expressions")
    try:
        setter(request.prop_path, request.expression)
    except Exception as exc:
        raise SetExpressionError("EXPRESSION_ERROR", str(exc) or type(exc).__name__) from exc
    return SetExpressionReceipt(
        name=object_name(item) or request.object_name,
        item=item,
        prop_path=request.prop_path,
        expression=request.expression,
        skipped=False,
    )


def read_set_expression_result(doc: SetExpressionReadDocument, receipt: SetExpressionReceipt) -> SetExpressionInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise SetExpressionError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise SetExpressionError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")
    getter = getattr(located, "getExpression", None)
    if callable(getter):
        bound = getter(receipt.prop_path)
        if str(bound or "") != receipt.expression:
            raise SetExpressionError(
                "EXPRESSION_ERROR",
                f"Expression on {receipt.prop_path!r} does not match the requested value",
            )

    extra = receipt.extra

    return SetExpressionInspection(
        name=SetExpressionName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_set_expression_request(doc_name: object, object_name: object, prop_path: object, expression: object) -> SetExpressionRequest | SetExpressionFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(SetExpressionError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    object_name_value = nonempty_string(object_name, 'object_name')
    if object_name_value is None:
        return _failure(SetExpressionError("INVALID_ARGUMENT", "object_name must be a nonempty string"))
    prop_path_value = nonempty_string(prop_path, 'prop_path')
    if prop_path_value is None:
        return _failure(SetExpressionError("INVALID_ARGUMENT", "prop_path must be a nonempty string"))
    expression_value = nonempty_string(expression, 'expression')
    if expression_value is None:
        return _failure(SetExpressionError("INVALID_ARGUMENT", "expression must be a nonempty string"))
    return SetExpressionRequest(
        doc_name=DocumentName(doc_name_value),
        object_name=object_name_value,
        prop_path=prop_path_value,
        expression=expression_value,
    )


@dataclass(slots=True)
class _SetExpressionExecution:
    collaborators: SetExpressionCollaborators
    request: SetExpressionRequest
    created: SetExpressionReceipt | None = None
    inspected: SetExpressionInspection | None = None

    def apply(self, doc: SetExpressionDocument) -> None:
        self.created = apply_set_expression(doc, self.request)

    def inspect(self, doc: SetExpressionReadDocument) -> None:
        if self.created is None:
            raise SetExpressionError(
                "INVALID_SET_EXPRESSION_RESULT",
                "set_expression did not return an identity receipt",
            )
        self.inspected = read_set_expression_result(doc, self.created)

    def run(self) -> SetExpressionResult:
        result = run_set_expression_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_set_expression_uncertain(
                "SET_EXPRESSION_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_set_expression_success(object=self.inspected.name, prop_path=self.request.prop_path, expression=self.request.expression)


def run_set_expression(
    collaborators: SetExpressionCollaborators,
    doc_name: object, object_name: object, prop_path: object, expression: object,
) -> SetExpressionResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_set_expression_request(doc_name, object_name, prop_path, expression)
    if isinstance(request, dict):
        return request
    return _SetExpressionExecution(collaborators, request).run()


class _SetExpressionRpcFacade(Protocol):
    _cad_collaborators: SetExpressionCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_set_expression(
    self: _SetExpressionRpcFacade, doc_name: str, object_name: str, prop_path: str, expression: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_set_expression(collaborators, doc_name, object_name, prop_path, expression)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("set_expression", rpc_set_expression)


__all__ = [
    "SetExpressionCollaborators",
    "SetExpressionError",
    "SetExpressionInspection",
    "SetExpressionReceipt",
    "apply_set_expression",
    "build_set_expression_request",
    "read_set_expression_result",
    "rpc_set_expression",
    "run_set_expression",
    "TYPED_RPC_HANDLER",
]
