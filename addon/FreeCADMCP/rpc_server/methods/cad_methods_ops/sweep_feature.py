
"""Typed ``sweep_feature`` mutation."""
from __future__ import annotations

from .feature_lookup_support import (
    is_derived_from,
    require_absent,
    require_object,
    resolve_optional_body,
)
from .feature_mutate_support import (
    bool_value,
    create_feature,
    nonempty_string,
    optional_name,
    require_nonempty_shape,
    set_attr,
    set_feature_bool,
    set_tip,
)

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sweep_feature_contract import (
    SweepFeatureCollaborators,
    SweepFeatureFailure,
    SweepFeatureRequest,
    SweepFeatureResult,
    FeatureDocument,
    FeatureName,
    FeatureObject,
    FeatureReadDocument,
    DocumentName,
    make_sweep_feature_failure,
    make_sweep_feature_success,
    make_sweep_feature_uncertain,
)
from .sweep_feature_mutation import SweepFeatureError, run_sweep_feature_native_mutation



@dataclass(frozen=True, slots=True)
class SweepFeatureReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class SweepFeatureInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: SweepFeatureError, *, retry_safe: bool = True) -> SweepFeatureFailure:
    return make_sweep_feature_failure(error.code, str(error), retry_safe=retry_safe)


def apply_sweep_feature(doc: FeatureDocument, request: SweepFeatureRequest) -> SweepFeatureReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.sweep_name)
        profile = require_object(
            doc, request.profile_sketch, missing="Profile sketch not found"
        )
        path = require_object(doc, request.path_sketch, missing="Path sketch not found")
        body = resolve_optional_body(doc, profile, request.body_name)
        created = create_feature(doc, body, 'PartDesign::AdditivePipe', request.sweep_name)
        set_attr(created, "Profile", (profile, [""]))
        set_attr(created, "Spine", (path, [""]))
        set_feature_bool(created, ("Frenet",), request.frenet)
        if body is not None:
            set_tip(body, created)
        return SweepFeatureReceipt(name=str(created.Name), feature=created)
    except SweepFeatureError:
        raise
    except FileExistsError as exc:
        raise SweepFeatureError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise SweepFeatureError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise SweepFeatureError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise SweepFeatureError(
            "SWEEP_FEATURE_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_sweep_feature_result(doc: FeatureReadDocument, receipt: SweepFeatureReceipt) -> SweepFeatureInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise SweepFeatureError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise SweepFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'PartDesign::AdditivePipe'):
        raise SweepFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::AdditivePipe: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise SweepFeatureError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return SweepFeatureInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_sweep_feature_request(
    doc_name: str, profile_sketch: str, path_sketch: str, sweep_name: str, body_name: str | None = None, frenet: bool = False
) -> SweepFeatureRequest | SweepFeatureFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        profile = FeatureName(nonempty_string(profile_sketch, "profile_sketch"))
        path = FeatureName(nonempty_string(path_sketch, "path_sketch"))
        created = FeatureName(nonempty_string(sweep_name, "sweep_name"))
        body = optional_name(body_name, "body_name")
        frenet_value = bool_value(frenet, "frenet")
    except ValueError as exc:
        return _failure(SweepFeatureError("INVALID_ARGUMENT", str(exc)))
    return SweepFeatureRequest(
        doc_name=doc,
        profile_sketch=profile,
        path_sketch=path,
        sweep_name=created,
        body_name=None if body is None else FeatureName(body),
        frenet=frenet_value,
    )


@dataclass(slots=True)
class _SweepFeatureExecution:
    collaborators: SweepFeatureCollaborators
    request: SweepFeatureRequest
    created: SweepFeatureReceipt | None = None
    inspected: SweepFeatureInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_sweep_feature(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise SweepFeatureError(
                "INVALID_SWEEP_FEATURE_RESULT",
                "sweep_feature did not return an identity receipt",
            )
        self.inspected = read_sweep_feature_result(doc, self.created)

    def run(self) -> SweepFeatureResult:
        result = run_sweep_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sweep_feature_uncertain(
                "SWEEP_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected sweep_feature result",
                committed=True,
            )
        return make_sweep_feature_success(self.inspected.name, self.inspected.label)


def run_sweep_feature(
    collaborators: SweepFeatureCollaborators,
    doc_name: str, profile_sketch: str, path_sketch: str, sweep_name: str, body_name: str | None = None, frenet: bool = False
) -> SweepFeatureResult:
    """Run sweep_feature through apply, recompute, inspection, and commit."""

    request = build_sweep_feature_request(doc_name, profile_sketch, path_sketch, sweep_name, body_name, frenet)
    if isinstance(request, dict):
        return request
    return _SweepFeatureExecution(collaborators, request).run()


class _SweepFeatureRpcFacade(Protocol):
    _cad_collaborators: SweepFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_sweep_feature(
    self: _SweepFeatureRpcFacade,
    doc_name: str, profile_sketch: str, path_sketch: str, sweep_name: str, body_name: str | None = None, frenet: bool = False
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sweep_feature(collaborators, doc_name, profile_sketch, path_sketch, sweep_name, body_name, frenet)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sweep_feature", rpc_sweep_feature)


__all__ = [
    "SweepFeatureCollaborators",
    "SweepFeatureError",
    "SweepFeatureInspection",
    "SweepFeatureReceipt",
    "apply_sweep_feature",
    "build_sweep_feature_request",
    "read_sweep_feature_result",
    "rpc_sweep_feature",
    "run_sweep_feature",
    "TYPED_RPC_HANDLER",
]
