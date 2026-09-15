
"""Typed ``boolean_union`` mutation."""
from __future__ import annotations

from .feature_lookup_support import (
    is_derived_from,
    require_absent,
    require_object,
)
from .feature_mutate_support import (
    create_feature,
    nonempty_string,
    require_nonempty_shape,
    set_attr,
)

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.boolean_union_contract import (
    BooleanUnionCollaborators,
    BooleanUnionFailure,
    BooleanUnionRequest,
    BooleanUnionResult,
    FeatureDocument,
    FeatureName,
    FeatureObject,
    FeatureReadDocument,
    DocumentName,
    make_boolean_union_failure,
    make_boolean_union_success,
    make_boolean_union_uncertain,
)
from .boolean_union_mutation import BooleanUnionError, run_boolean_union_native_mutation



@dataclass(frozen=True, slots=True)
class BooleanUnionReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class BooleanUnionInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: BooleanUnionError, *, retry_safe: bool = True) -> BooleanUnionFailure:
    return make_boolean_union_failure(error.code, str(error), retry_safe=retry_safe)


def apply_boolean_union(doc: FeatureDocument, request: BooleanUnionRequest) -> BooleanUnionReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.result_name)
        first = require_object(doc, request.shape1, missing="Shape1 not found")
        second = require_object(doc, request.shape2, missing="Shape2 not found")
        created = create_feature(doc, None, 'Part::Fuse', request.result_name)
        set_attr(created, "Base", first)
        set_attr(created, "Tool", second)
        set_attr(created, "Refine", False)
        return BooleanUnionReceipt(name=str(created.Name), feature=created)
    except BooleanUnionError:
        raise
    except FileExistsError as exc:
        raise BooleanUnionError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise BooleanUnionError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise BooleanUnionError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise BooleanUnionError(
            "BOOLEAN_UNION_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_boolean_union_result(doc: FeatureReadDocument, receipt: BooleanUnionReceipt) -> BooleanUnionInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise BooleanUnionError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise BooleanUnionError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'Part::Fuse'):
        raise BooleanUnionError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not Part::Fuse: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise BooleanUnionError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return BooleanUnionInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_boolean_union_request(
    doc_name: str, shape1: str, shape2: str, result_name: str
) -> BooleanUnionRequest | BooleanUnionFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        first = FeatureName(nonempty_string(shape1, "shape1"))
        second = FeatureName(nonempty_string(shape2, "shape2"))
        result = FeatureName(nonempty_string(result_name, "result_name"))
    except ValueError as exc:
        return _failure(BooleanUnionError("INVALID_ARGUMENT", str(exc)))
    return BooleanUnionRequest(
        doc_name=doc, shape1=first, shape2=second, result_name=result
    )


@dataclass(slots=True)
class _BooleanUnionExecution:
    collaborators: BooleanUnionCollaborators
    request: BooleanUnionRequest
    created: BooleanUnionReceipt | None = None
    inspected: BooleanUnionInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_boolean_union(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise BooleanUnionError(
                "INVALID_BOOLEAN_UNION_RESULT",
                "boolean_union did not return an identity receipt",
            )
        self.inspected = read_boolean_union_result(doc, self.created)

    def run(self) -> BooleanUnionResult:
        result = run_boolean_union_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_boolean_union_uncertain(
                "BOOLEAN_UNION_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected boolean_union result",
                committed=True,
            )
        return make_boolean_union_success(self.inspected.name, self.inspected.label)


def run_boolean_union(
    collaborators: BooleanUnionCollaborators,
    doc_name: str, shape1: str, shape2: str, result_name: str
) -> BooleanUnionResult:
    """Run boolean_union through apply, recompute, inspection, and commit."""

    request = build_boolean_union_request(doc_name, shape1, shape2, result_name)
    if isinstance(request, dict):
        return request
    return _BooleanUnionExecution(collaborators, request).run()


class _BooleanUnionRpcFacade(Protocol):
    _cad_collaborators: BooleanUnionCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_boolean_union(
    self: _BooleanUnionRpcFacade,
    doc_name: str, shape1: str, shape2: str, result_name: str
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_boolean_union(collaborators, doc_name, shape1, shape2, result_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("boolean_union", rpc_boolean_union)


__all__ = [
    "BooleanUnionCollaborators",
    "BooleanUnionError",
    "BooleanUnionInspection",
    "BooleanUnionReceipt",
    "apply_boolean_union",
    "build_boolean_union_request",
    "read_boolean_union_result",
    "rpc_boolean_union",
    "run_boolean_union",
    "TYPED_RPC_HANDLER",
]
