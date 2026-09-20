
"""Typed ``boolean_intersection`` mutation."""
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

try:
    from ...._shared.protocol.boolean_intersection_contract import (
        BooleanIntersectionCollaborators,
        BooleanIntersectionFailure,
        BooleanIntersectionRequest,
        BooleanIntersectionResult,
        FeatureDocument,
        FeatureName,
        FeatureObject,
        FeatureReadDocument,
        DocumentName,
        make_boolean_intersection_failure,
        make_boolean_intersection_success,
        make_boolean_intersection_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.boolean_intersection_contract import (
        BooleanIntersectionCollaborators,
        BooleanIntersectionFailure,
        BooleanIntersectionRequest,
        BooleanIntersectionResult,
        FeatureDocument,
        FeatureName,
        FeatureObject,
        FeatureReadDocument,
        DocumentName,
        make_boolean_intersection_failure,
        make_boolean_intersection_success,
        make_boolean_intersection_uncertain,
    )
from .boolean_intersection_mutation import BooleanIntersectionError, run_boolean_intersection_native_mutation



@dataclass(frozen=True, slots=True)
class BooleanIntersectionReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class BooleanIntersectionInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: BooleanIntersectionError, *, retry_safe: bool = True) -> BooleanIntersectionFailure:
    return make_boolean_intersection_failure(error.code, str(error), retry_safe=retry_safe)


def apply_boolean_intersection(doc: FeatureDocument, request: BooleanIntersectionRequest) -> BooleanIntersectionReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.result_name)
        first = require_object(doc, request.shape1, missing="Shape1 not found")
        second = require_object(doc, request.shape2, missing="Shape2 not found")
        created = create_feature(doc, None, 'Part::Common', request.result_name)
        set_attr(created, "Base", first)
        set_attr(created, "Tool", second)
        return BooleanIntersectionReceipt(name=str(created.Name), feature=created)
    except BooleanIntersectionError:
        raise
    except FileExistsError as exc:
        raise BooleanIntersectionError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise BooleanIntersectionError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise BooleanIntersectionError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise BooleanIntersectionError(
            "BOOLEAN_INTERSECTION_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_boolean_intersection_result(doc: FeatureReadDocument, receipt: BooleanIntersectionReceipt) -> BooleanIntersectionInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise BooleanIntersectionError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise BooleanIntersectionError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'Part::Common'):
        raise BooleanIntersectionError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not Part::Common: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise BooleanIntersectionError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return BooleanIntersectionInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_boolean_intersection_request(
    doc_name: str, shape1: str, shape2: str, result_name: str
) -> BooleanIntersectionRequest | BooleanIntersectionFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        first = FeatureName(nonempty_string(shape1, "shape1"))
        second = FeatureName(nonempty_string(shape2, "shape2"))
        result = FeatureName(nonempty_string(result_name, "result_name"))
    except ValueError as exc:
        return _failure(BooleanIntersectionError("INVALID_ARGUMENT", str(exc)))
    return BooleanIntersectionRequest(
        doc_name=doc, shape1=first, shape2=second, result_name=result
    )


@dataclass(slots=True)
class _BooleanIntersectionExecution:
    collaborators: BooleanIntersectionCollaborators
    request: BooleanIntersectionRequest
    created: BooleanIntersectionReceipt | None = None
    inspected: BooleanIntersectionInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_boolean_intersection(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise BooleanIntersectionError(
                "INVALID_BOOLEAN_INTERSECTION_RESULT",
                "boolean_intersection did not return an identity receipt",
            )
        self.inspected = read_boolean_intersection_result(doc, self.created)

    def run(self) -> BooleanIntersectionResult:
        result = run_boolean_intersection_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_boolean_intersection_uncertain(
                "BOOLEAN_INTERSECTION_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected boolean_intersection result",
                committed=True,
            )
        return make_boolean_intersection_success(self.inspected.name, self.inspected.label)


def run_boolean_intersection(
    collaborators: BooleanIntersectionCollaborators,
    doc_name: str, shape1: str, shape2: str, result_name: str
) -> BooleanIntersectionResult:
    """Run boolean_intersection through apply, recompute, inspection, and commit."""

    request = build_boolean_intersection_request(doc_name, shape1, shape2, result_name)
    if isinstance(request, dict):
        return request
    return _BooleanIntersectionExecution(collaborators, request).run()


class _BooleanIntersectionRpcFacade(Protocol):
    _cad_collaborators: BooleanIntersectionCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_boolean_intersection(
    self: _BooleanIntersectionRpcFacade,
    doc_name: str, shape1: str, shape2: str, result_name: str
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_boolean_intersection(collaborators, doc_name, shape1, shape2, result_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("boolean_intersection", rpc_boolean_intersection)


__all__ = [
    "BooleanIntersectionCollaborators",
    "BooleanIntersectionError",
    "BooleanIntersectionInspection",
    "BooleanIntersectionReceipt",
    "apply_boolean_intersection",
    "build_boolean_intersection_request",
    "read_boolean_intersection_result",
    "rpc_boolean_intersection",
    "run_boolean_intersection",
    "TYPED_RPC_HANDLER",
]
