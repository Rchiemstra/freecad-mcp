"""Typed ``boolean_difference`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.boolean_difference_contract import (
    BooleanDifferenceCollaborators,
    BooleanDifferenceFailure,
    BooleanDifferenceRequest,
    BooleanDifferenceResult,
    FeatureDocument,
    FeatureName,
    FeatureObject,
    FeatureReadDocument,
    DocumentName,
    make_boolean_difference_failure,
    make_boolean_difference_success,
    make_boolean_difference_uncertain,
)
from .boolean_difference_mutation import BooleanDifferenceError, run_boolean_difference_native_mutation
from .feature_apply_support import (
    create_feature,
    is_derived_from,
    nonempty_string,
    require_absent,
    require_object,
    set_attr,
)


@dataclass(frozen=True, slots=True)
class BooleanDifferenceReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class BooleanDifferenceInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: BooleanDifferenceError, *, retry_safe: bool = True) -> BooleanDifferenceFailure:
    return make_boolean_difference_failure(error.code, str(error), retry_safe=retry_safe)


def apply_boolean_difference(doc: FeatureDocument, request: BooleanDifferenceRequest) -> BooleanDifferenceReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.result_name)
        first = require_object(doc, request.shape1, missing="Shape1 not found")
        second = require_object(doc, request.shape2, missing="Shape2 not found")
        created = create_feature(doc, None, 'Part::Cut', request.result_name)
        set_attr(created, "Base", first)
        set_attr(created, "Tool", second)
        set_attr(first, "Visibility", False)
        set_attr(second, "Visibility", False)
        return BooleanDifferenceReceipt(name=str(created.Name), feature=created)
    except BooleanDifferenceError:
        raise
    except FileExistsError as exc:
        raise BooleanDifferenceError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise BooleanDifferenceError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise BooleanDifferenceError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise BooleanDifferenceError(
            "BOOLEAN_DIFFERENCE_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_boolean_difference_result(doc: FeatureReadDocument, receipt: BooleanDifferenceReceipt) -> BooleanDifferenceInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise BooleanDifferenceError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise BooleanDifferenceError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'Part::Cut'):
        raise BooleanDifferenceError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not Part::Cut: {receipt.name!r}",
        )
    return BooleanDifferenceInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_boolean_difference_request(
    doc_name: str, shape1: str, shape2: str, result_name: str
) -> BooleanDifferenceRequest | BooleanDifferenceFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        first = FeatureName(nonempty_string(shape1, "shape1"))
        second = FeatureName(nonempty_string(shape2, "shape2"))
        result = FeatureName(nonempty_string(result_name, "result_name"))
    except ValueError as exc:
        return _failure(BooleanDifferenceError("INVALID_ARGUMENT", str(exc)))
    return BooleanDifferenceRequest(
        doc_name=doc, shape1=first, shape2=second, result_name=result
    )


@dataclass(slots=True)
class _BooleanDifferenceExecution:
    collaborators: BooleanDifferenceCollaborators
    request: BooleanDifferenceRequest
    created: BooleanDifferenceReceipt | None = None
    inspected: BooleanDifferenceInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_boolean_difference(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise BooleanDifferenceError(
                "INVALID_BOOLEAN_DIFFERENCE_RESULT",
                "boolean_difference did not return an identity receipt",
            )
        self.inspected = read_boolean_difference_result(doc, self.created)

    def run(self) -> BooleanDifferenceResult:
        result = run_boolean_difference_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_boolean_difference_uncertain(
                "BOOLEAN_DIFFERENCE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected boolean_difference result",
                committed=True,
            )
        return make_boolean_difference_success(self.inspected.name, self.inspected.label)


def run_boolean_difference(
    collaborators: BooleanDifferenceCollaborators,
    doc_name: str, shape1: str, shape2: str, result_name: str
) -> BooleanDifferenceResult:
    """Run boolean_difference through apply, recompute, inspection, and commit."""

    request = build_boolean_difference_request(doc_name, shape1, shape2, result_name)
    if isinstance(request, dict):
        return request
    return _BooleanDifferenceExecution(collaborators, request).run()


class _BooleanDifferenceRpcFacade(Protocol):
    _cad_collaborators: BooleanDifferenceCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_boolean_difference(
    self: _BooleanDifferenceRpcFacade,
    doc_name: str, shape1: str, shape2: str, result_name: str
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_boolean_difference(collaborators, doc_name, shape1, shape2, result_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("boolean_difference", rpc_boolean_difference)


__all__ = [
    "BooleanDifferenceCollaborators",
    "BooleanDifferenceError",
    "BooleanDifferenceInspection",
    "BooleanDifferenceReceipt",
    "apply_boolean_difference",
    "build_boolean_difference_request",
    "read_boolean_difference_result",
    "rpc_boolean_difference",
    "run_boolean_difference",
    "TYPED_RPC_HANDLER",
]
