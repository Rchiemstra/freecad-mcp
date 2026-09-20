
"""Typed ``linear_pattern_feature`` mutation."""
from __future__ import annotations

from .feature_lookup_support import (
    is_derived_from,
    require_absent,
    require_body,
    require_object,
    resolve_linksub,
)
from .feature_mutate_support import (
    bool_value,
    count_value,
    create_feature,
    nonempty_string,
    number_value,
    optional_name,
    require_nonempty_shape,
    set_feature_bool,
    set_named_property,
    set_originals,
    set_tip,
)

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.linear_pattern_feature_contract import (
        LinearPatternFeatureCollaborators,
        LinearPatternFeatureFailure,
        LinearPatternFeatureRequest,
        LinearPatternFeatureResult,
        FeatureDocument,
        FeatureName,
        FeatureObject,
        FeatureReadDocument,
        DocumentName,
        make_linear_pattern_feature_failure,
        make_linear_pattern_feature_success,
        make_linear_pattern_feature_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.linear_pattern_feature_contract import (
        LinearPatternFeatureCollaborators,
        LinearPatternFeatureFailure,
        LinearPatternFeatureRequest,
        LinearPatternFeatureResult,
        FeatureDocument,
        FeatureName,
        FeatureObject,
        FeatureReadDocument,
        DocumentName,
        make_linear_pattern_feature_failure,
        make_linear_pattern_feature_success,
        make_linear_pattern_feature_uncertain,
    )
from .linear_pattern_feature_mutation import LinearPatternFeatureError, run_linear_pattern_feature_native_mutation



@dataclass(frozen=True, slots=True)
class LinearPatternFeatureReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class LinearPatternFeatureInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: LinearPatternFeatureError, *, retry_safe: bool = True) -> LinearPatternFeatureFailure:
    return make_linear_pattern_feature_failure(error.code, str(error), retry_safe=retry_safe)


def apply_linear_pattern_feature(doc: FeatureDocument, request: LinearPatternFeatureRequest) -> LinearPatternFeatureReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.pattern_name)
        source = require_object(
            doc, request.feature_name, missing="Source feature not found"
        )
        body = require_body(doc, source, request.body_name)
        created = create_feature(doc, body, 'PartDesign::LinearPattern', request.pattern_name)
        set_originals(created, source)
        set_named_property(created, ("Length",), request.length)
        set_named_property(created, ("Occurrences",), request.occurrences)
        set_named_property(
            created, ("Direction",), resolve_linksub(doc, body, request.direction)
        )
        set_feature_bool(created, ("Reversed",), request.reversed_dir)
        set_tip(body, created)
        return LinearPatternFeatureReceipt(name=str(created.Name), feature=created)
    except LinearPatternFeatureError:
        raise
    except FileExistsError as exc:
        raise LinearPatternFeatureError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise LinearPatternFeatureError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise LinearPatternFeatureError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise LinearPatternFeatureError(
            "LINEAR_PATTERN_FEATURE_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_linear_pattern_feature_result(doc: FeatureReadDocument, receipt: LinearPatternFeatureReceipt) -> LinearPatternFeatureInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise LinearPatternFeatureError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise LinearPatternFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'PartDesign::LinearPattern'):
        raise LinearPatternFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::LinearPattern: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise LinearPatternFeatureError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return LinearPatternFeatureInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_linear_pattern_feature_request(
    doc_name: str, feature_name: str, pattern_name: str, length: float, occurrences: int, direction: str = 'X_Axis', body_name: str | None = None, reversed_dir: bool = False
) -> LinearPatternFeatureRequest | LinearPatternFeatureFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        source = FeatureName(nonempty_string(feature_name, "feature_name"))
        created = FeatureName(nonempty_string(pattern_name, "pattern_name"))
        length_value = number_value(length, "length", positive=True)
        count = count_value(occurrences, "occurrences", minimum=2)
        direction_value = nonempty_string(direction, "direction")
        body = optional_name(body_name, "body_name")
        reversed_value = bool_value(reversed_dir, "reversed_dir")
    except ValueError as exc:
        return _failure(LinearPatternFeatureError("INVALID_ARGUMENT", str(exc)))
    return LinearPatternFeatureRequest(
        doc_name=doc,
        feature_name=source,
        pattern_name=created,
        length=length_value,
        occurrences=count,
        direction=direction_value,
        body_name=None if body is None else FeatureName(body),
        reversed_dir=reversed_value,
    )


@dataclass(slots=True)
class _LinearPatternFeatureExecution:
    collaborators: LinearPatternFeatureCollaborators
    request: LinearPatternFeatureRequest
    created: LinearPatternFeatureReceipt | None = None
    inspected: LinearPatternFeatureInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_linear_pattern_feature(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise LinearPatternFeatureError(
                "INVALID_LINEAR_PATTERN_FEATURE_RESULT",
                "linear_pattern_feature did not return an identity receipt",
            )
        self.inspected = read_linear_pattern_feature_result(doc, self.created)

    def run(self) -> LinearPatternFeatureResult:
        result = run_linear_pattern_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_linear_pattern_feature_uncertain(
                "LINEAR_PATTERN_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected linear_pattern_feature result",
                committed=True,
            )
        return make_linear_pattern_feature_success(self.inspected.name, self.inspected.label)


def run_linear_pattern_feature(
    collaborators: LinearPatternFeatureCollaborators,
    doc_name: str, feature_name: str, pattern_name: str, length: float, occurrences: int, direction: str = 'X_Axis', body_name: str | None = None, reversed_dir: bool = False
) -> LinearPatternFeatureResult:
    """Run linear_pattern_feature through apply, recompute, inspection, and commit."""

    request = build_linear_pattern_feature_request(doc_name, feature_name, pattern_name, length, occurrences, direction, body_name, reversed_dir)
    if isinstance(request, dict):
        return request
    return _LinearPatternFeatureExecution(collaborators, request).run()


class _LinearPatternFeatureRpcFacade(Protocol):
    _cad_collaborators: LinearPatternFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_linear_pattern_feature(
    self: _LinearPatternFeatureRpcFacade,
    doc_name: str, feature_name: str, pattern_name: str, length: float, occurrences: int, direction: str = 'X_Axis', body_name: str | None = None, reversed_dir: bool = False
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_linear_pattern_feature(collaborators, doc_name, feature_name, pattern_name, length, occurrences, direction, body_name, reversed_dir)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("linear_pattern_feature", rpc_linear_pattern_feature)


__all__ = [
    "LinearPatternFeatureCollaborators",
    "LinearPatternFeatureError",
    "LinearPatternFeatureInspection",
    "LinearPatternFeatureReceipt",
    "apply_linear_pattern_feature",
    "build_linear_pattern_feature_request",
    "read_linear_pattern_feature_result",
    "rpc_linear_pattern_feature",
    "run_linear_pattern_feature",
    "TYPED_RPC_HANDLER",
]
