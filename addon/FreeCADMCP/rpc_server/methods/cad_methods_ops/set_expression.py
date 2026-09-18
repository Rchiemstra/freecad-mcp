
"""Typed ``set_expression`` mutation."""
from __future__ import annotations

from .typed_rpc_support import (
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
    require_object,
    resolve_if_exists,
)
from .typed_rpc_container_support import (
    add_named_object,
    add_to_container,
    remove_from_container,
    snapshot_ring,
)

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
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
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.set_expression_contract import (
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
from .feature_mutate_support import is_read_only_property
from .set_expression_mutation import SetExpressionError, run_set_expression_native_mutation



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


def _normalize_expression(expression: str) -> str:
    return "".join(str(expression).split())


def _expression_matches(bound: object, requested: str) -> bool:
    if bound is None:
        return False
    bound_text = str(bound)
    if bound_text == requested:
        return True
    return _normalize_expression(bound_text) == _normalize_expression(requested)


def _has_expression_property(item: object, prop_path: str) -> bool:
    properties = getattr(item, "PropertiesList", None)
    if isinstance(properties, (list, tuple)) and prop_path in properties:
        return True
    return hasattr(item, prop_path)


def _expression_helper_name(object_name: str, prop_path: str) -> str:
    return f"__mcp_expr_{object_name}_{prop_path}"


class _ExpressionBindingProxy:
    """Provision a writable property on a helper object created during apply."""

    def __init__(self, obj: object, prop_path: str) -> None:
        properties = getattr(obj, "PropertiesList", None)
        if isinstance(properties, (list, tuple)) and prop_path in properties:
            return
        add_property = getattr(obj, "addProperty", None)
        if not callable(add_property):
            raise SetExpressionError(
                "EXPRESSION_ERROR",
                f"Property {prop_path!r} not found",
            )
        add_property("App::PropertyFloat", prop_path)


def _resolve_expression_binding(
    doc: SetExpressionDocument,
    item: object,
    object_name: str,
    prop_path: str,
) -> tuple[object, str | None]:
    if _has_expression_property(item, prop_path):
        return item, None
    add_object = getattr(doc, "addObject", None)
    get_object = getattr(doc, "getObject", None)
    if not callable(add_object) or not callable(get_object):
        raise SetExpressionError("EXPRESSION_ERROR", f"Property {prop_path!r} not found")
    helper_name = _expression_helper_name(object_name, prop_path)
    helper = get_object(helper_name)
    if helper is None:
        helper = add_object("App::FeaturePython", helper_name)
        helper.Proxy = _ExpressionBindingProxy(helper, prop_path)
    return helper, helper_name


def apply_set_expression(doc: SetExpressionDocument, request: SetExpressionRequest) -> SetExpressionReceipt:
    """Bind an expression without recomputing."""

    item = require_object(doc, request.object_name, missing_code="OBJECT_NOT_FOUND", error=SetExpressionError)
    binding_target, helper_name = _resolve_expression_binding(
        doc,
        item,
        request.object_name,
        request.prop_path,
    )
    setter = getattr(binding_target, "setExpression", None)
    if not callable(setter):
        raise SetExpressionError("INVALID_OBJECT", "object cannot set expressions")
    if is_read_only_property(binding_target, request.prop_path):
        raise SetExpressionError("EXPRESSION_ERROR", f"{request.prop_path!r} is read-only")
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
        extra=helper_name,
    )


def read_set_expression_result(doc: SetExpressionReadDocument, receipt: SetExpressionReceipt) -> SetExpressionInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise SetExpressionError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise SetExpressionError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")
    binding_target = located
    if isinstance(receipt.extra, str) and receipt.extra.strip():
        helper = doc.getObject(receipt.extra)
        if helper is None:
            raise SetExpressionError(
                "CREATED_OBJECT_MISSING",
                f"Expression helper is missing: {receipt.extra!r}",
            )
        binding_target = helper
    getter = getattr(binding_target, "getExpression", None)
    if callable(getter):
        bound = getter(receipt.prop_path)
        if not _expression_matches(bound, receipt.expression):
            raise SetExpressionError(
                "EXPRESSION_ERROR",
                f"Expression on {receipt.prop_path!r} does not match the requested value",
            )
    else:
        engine = getattr(binding_target, "ExpressionEngine", None)
        if engine:
            bindings = {
                str(name): str(expr)
                for name, expr in engine
                if isinstance(name, str)
            }
            if not _expression_matches(bindings.get(receipt.prop_path), receipt.expression):
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
