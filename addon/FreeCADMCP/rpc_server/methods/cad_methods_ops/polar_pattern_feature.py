
"""Typed ``polar_pattern_feature`` mutation."""
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
    from ...._shared.protocol.polar_pattern_feature_contract import (
        PolarPatternFeatureCollaborators,
        PolarPatternFeatureFailure,
        PolarPatternFeatureRequest,
        PolarPatternFeatureResult,
        FeatureDocument,
        FeatureName,
        FeatureObject,
        FeatureReadDocument,
        DocumentName,
        make_polar_pattern_feature_failure,
        make_polar_pattern_feature_success,
        make_polar_pattern_feature_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.polar_pattern_feature_contract import (
        PolarPatternFeatureCollaborators,
        PolarPatternFeatureFailure,
        PolarPatternFeatureRequest,
        PolarPatternFeatureResult,
        FeatureDocument,
        FeatureName,
        FeatureObject,
        FeatureReadDocument,
        DocumentName,
        make_polar_pattern_feature_failure,
        make_polar_pattern_feature_success,
        make_polar_pattern_feature_uncertain,
    )
from .polar_pattern_feature_mutation import PolarPatternFeatureError, run_polar_pattern_feature_native_mutation



@dataclass(frozen=True, slots=True)
class PolarPatternFeatureReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class PolarPatternFeatureInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: PolarPatternFeatureError, *, retry_safe: bool = True) -> PolarPatternFeatureFailure:
    return make_polar_pattern_feature_failure(error.code, str(error), retry_safe=retry_safe)


def apply_polar_pattern_feature(doc: FeatureDocument, request: PolarPatternFeatureRequest) -> PolarPatternFeatureReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.pattern_name)
        source = require_object(
            doc, request.feature_name, missing="Source feature not found"
        )
        body = require_body(doc, source, request.body_name)
        created = create_feature(doc, body, 'PartDesign::PolarPattern', request.pattern_name)
        set_originals(created, source)
        set_named_property(created, ("Angle",), request.angle)
        set_named_property(created, ("Occurrences",), request.occurrences)
        set_named_property(
            created, ("Axis",), resolve_linksub(doc, body, request.axis, sketch=None)
        )
        set_feature_bool(created, ("Reversed",), request.reversed_dir)
        set_tip(body, created)
        return PolarPatternFeatureReceipt(name=str(created.Name), feature=created)
    except PolarPatternFeatureError:
        raise
    except FileExistsError as exc:
        raise PolarPatternFeatureError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise PolarPatternFeatureError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise PolarPatternFeatureError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise PolarPatternFeatureError(
            "POLAR_PATTERN_FEATURE_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_polar_pattern_feature_result(doc: FeatureReadDocument, receipt: PolarPatternFeatureReceipt) -> PolarPatternFeatureInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise PolarPatternFeatureError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise PolarPatternFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'PartDesign::PolarPattern'):
        raise PolarPatternFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::PolarPattern: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise PolarPatternFeatureError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return PolarPatternFeatureInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_polar_pattern_feature_request(
    doc_name: str, feature_name: str, pattern_name: str, occurrences: int, angle: float = 360.0, axis: str = 'Z_Axis', body_name: str | None = None, reversed_dir: bool = False
) -> PolarPatternFeatureRequest | PolarPatternFeatureFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        source = FeatureName(nonempty_string(feature_name, "feature_name"))
        created = FeatureName(nonempty_string(pattern_name, "pattern_name"))
        count = count_value(occurrences, "occurrences", minimum=2)
        angle_value = number_value(angle, "angle", positive=True)
        axis_value = nonempty_string(axis, "axis")
        body = optional_name(body_name, "body_name")
        reversed_value = bool_value(reversed_dir, "reversed_dir")
    except ValueError as exc:
        return _failure(PolarPatternFeatureError("INVALID_ARGUMENT", str(exc)))
    return PolarPatternFeatureRequest(
        doc_name=doc,
        feature_name=source,
        pattern_name=created,
        occurrences=count,
        angle=angle_value,
        axis=axis_value,
        body_name=None if body is None else FeatureName(body),
        reversed_dir=reversed_value,
    )


@dataclass(slots=True)
class _PolarPatternFeatureExecution:
    collaborators: PolarPatternFeatureCollaborators
    request: PolarPatternFeatureRequest
    created: PolarPatternFeatureReceipt | None = None
    inspected: PolarPatternFeatureInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_polar_pattern_feature(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise PolarPatternFeatureError(
                "INVALID_POLAR_PATTERN_FEATURE_RESULT",
                "polar_pattern_feature did not return an identity receipt",
            )
        self.inspected = read_polar_pattern_feature_result(doc, self.created)

    def run(self) -> PolarPatternFeatureResult:
        result = run_polar_pattern_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_polar_pattern_feature_uncertain(
                "POLAR_PATTERN_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected polar_pattern_feature result",
                committed=True,
            )
        return make_polar_pattern_feature_success(self.inspected.name, self.inspected.label)


def run_polar_pattern_feature(
    collaborators: PolarPatternFeatureCollaborators,
    doc_name: str, feature_name: str, pattern_name: str, occurrences: int, angle: float = 360.0, axis: str = 'Z_Axis', body_name: str | None = None, reversed_dir: bool = False
) -> PolarPatternFeatureResult:
    """Run polar_pattern_feature through apply, recompute, inspection, and commit."""

    request = build_polar_pattern_feature_request(doc_name, feature_name, pattern_name, occurrences, angle, axis, body_name, reversed_dir)
    if isinstance(request, dict):
        return request
    return _PolarPatternFeatureExecution(collaborators, request).run()


class _PolarPatternFeatureRpcFacade(Protocol):
    _cad_collaborators: PolarPatternFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_polar_pattern_feature(
    self: _PolarPatternFeatureRpcFacade,
    doc_name: str, feature_name: str, pattern_name: str, occurrences: int, angle: float = 360.0, axis: str = 'Z_Axis', body_name: str | None = None, reversed_dir: bool = False
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_polar_pattern_feature(collaborators, doc_name, feature_name, pattern_name, occurrences, angle, axis, body_name, reversed_dir)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("polar_pattern_feature", rpc_polar_pattern_feature)


__all__ = [
    "PolarPatternFeatureCollaborators",
    "PolarPatternFeatureError",
    "PolarPatternFeatureInspection",
    "PolarPatternFeatureReceipt",
    "apply_polar_pattern_feature",
    "build_polar_pattern_feature_request",
    "read_polar_pattern_feature_result",
    "rpc_polar_pattern_feature",
    "run_polar_pattern_feature",
    "TYPED_RPC_HANDLER",
]
