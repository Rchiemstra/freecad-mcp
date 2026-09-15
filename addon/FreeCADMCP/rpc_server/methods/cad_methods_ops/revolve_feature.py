
"""Typed ``revolve_feature`` mutation."""
from __future__ import annotations

from .feature_lookup_support import (
    is_derived_from,
    require_absent,
    require_object,
    resolve_optional_body,
    resolve_revolve_axis,
)
from .feature_mutate_support import (
    bool_value,
    create_feature,
    nonempty_string,
    number_value,
    optional_name,
    require_nonempty_shape,
    set_attr,
    set_feature_bool,
    set_named_property,
    set_tip,
)

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.revolve_feature_contract import (
    RevolveFeatureCollaborators,
    RevolveFeatureFailure,
    RevolveFeatureRequest,
    RevolveFeatureResult,
    FeatureDocument,
    FeatureName,
    FeatureObject,
    FeatureReadDocument,
    DocumentName,
    make_revolve_feature_failure,
    make_revolve_feature_success,
    make_revolve_feature_uncertain,
)
from .revolve_feature_mutation import RevolveFeatureError, run_revolve_feature_native_mutation



@dataclass(frozen=True, slots=True)
class RevolveFeatureReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class RevolveFeatureInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: RevolveFeatureError, *, retry_safe: bool = True) -> RevolveFeatureFailure:
    return make_revolve_feature_failure(error.code, str(error), retry_safe=retry_safe)


def apply_revolve_feature(doc: FeatureDocument, request: RevolveFeatureRequest) -> RevolveFeatureReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.revolve_name)
        sketch = require_object(doc, request.sketch_name, missing="Sketch not found")
        body = resolve_optional_body(doc, sketch, request.body_name)
        created = create_feature(doc, body, 'PartDesign::Revolution', request.revolve_name)
        set_attr(created, "Profile", (sketch, [""]))
        set_attr(created, "Angle", request.angle)
        set_named_property(
            created,
            ("ReferenceAxis", "Axis"),
            resolve_revolve_axis(doc, body, sketch, request.axis),
        )
        set_feature_bool(created, ("Symmetric",), request.symmetric)
        set_feature_bool(created, ("Reversed",), request.reversed_dir)
        if body is not None:
            set_tip(body, created)
        return RevolveFeatureReceipt(name=str(created.Name), feature=created)
    except RevolveFeatureError:
        raise
    except FileExistsError as exc:
        raise RevolveFeatureError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise RevolveFeatureError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise RevolveFeatureError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise RevolveFeatureError(
            "REVOLVE_FEATURE_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_revolve_feature_result(doc: FeatureReadDocument, receipt: RevolveFeatureReceipt) -> RevolveFeatureInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise RevolveFeatureError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise RevolveFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'PartDesign::Revolution'):
        raise RevolveFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::Revolution: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise RevolveFeatureError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return RevolveFeatureInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_revolve_feature_request(
    doc_name: str, sketch_name: str, revolve_name: str, angle: float = 360.0, axis: str = 'Z_Axis', body_name: str | None = None, symmetric: bool = False, reversed_dir: bool = False
) -> RevolveFeatureRequest | RevolveFeatureFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        sketch = FeatureName(nonempty_string(sketch_name, "sketch_name"))
        created = FeatureName(nonempty_string(revolve_name, "revolve_name"))
        angle_value = number_value(angle, "angle", positive=True)
        axis_value = nonempty_string(axis, "axis")
        body = optional_name(body_name, "body_name")
        symmetric_value = bool_value(symmetric, "symmetric")
        reversed_value = bool_value(reversed_dir, "reversed_dir")
    except ValueError as exc:
        return _failure(RevolveFeatureError("INVALID_ARGUMENT", str(exc)))
    return RevolveFeatureRequest(
        doc_name=doc,
        sketch_name=sketch,
        revolve_name=created,
        angle=angle_value,
        axis=axis_value,
        body_name=None if body is None else FeatureName(body),
        symmetric=symmetric_value,
        reversed_dir=reversed_value,
    )


@dataclass(slots=True)
class _RevolveFeatureExecution:
    collaborators: RevolveFeatureCollaborators
    request: RevolveFeatureRequest
    created: RevolveFeatureReceipt | None = None
    inspected: RevolveFeatureInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_revolve_feature(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise RevolveFeatureError(
                "INVALID_REVOLVE_FEATURE_RESULT",
                "revolve_feature did not return an identity receipt",
            )
        self.inspected = read_revolve_feature_result(doc, self.created)

    def run(self) -> RevolveFeatureResult:
        result = run_revolve_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_revolve_feature_uncertain(
                "REVOLVE_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected revolve_feature result",
                committed=True,
            )
        return make_revolve_feature_success(self.inspected.name, self.inspected.label)


def run_revolve_feature(
    collaborators: RevolveFeatureCollaborators,
    doc_name: str, sketch_name: str, revolve_name: str, angle: float = 360.0, axis: str = 'Z_Axis', body_name: str | None = None, symmetric: bool = False, reversed_dir: bool = False
) -> RevolveFeatureResult:
    """Run revolve_feature through apply, recompute, inspection, and commit."""

    request = build_revolve_feature_request(doc_name, sketch_name, revolve_name, angle, axis, body_name, symmetric, reversed_dir)
    if isinstance(request, dict):
        return request
    return _RevolveFeatureExecution(collaborators, request).run()


class _RevolveFeatureRpcFacade(Protocol):
    _cad_collaborators: RevolveFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_revolve_feature(
    self: _RevolveFeatureRpcFacade,
    doc_name: str, sketch_name: str, revolve_name: str, angle: float = 360.0, axis: str = 'Z_Axis', body_name: str | None = None, symmetric: bool = False, reversed_dir: bool = False
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_revolve_feature(collaborators, doc_name, sketch_name, revolve_name, angle, axis, body_name, symmetric, reversed_dir)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("revolve_feature", rpc_revolve_feature)


__all__ = [
    "RevolveFeatureCollaborators",
    "RevolveFeatureError",
    "RevolveFeatureInspection",
    "RevolveFeatureReceipt",
    "apply_revolve_feature",
    "build_revolve_feature_request",
    "read_revolve_feature_result",
    "rpc_revolve_feature",
    "run_revolve_feature",
    "TYPED_RPC_HANDLER",
]
