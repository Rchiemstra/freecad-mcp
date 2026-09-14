"""Typed ``helical_sweep_feature`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.helical_sweep_feature_contract import (
    HelicalSweepFeatureCollaborators,
    HelicalSweepFeatureFailure,
    HelicalSweepFeatureRequest,
    HelicalSweepFeatureResult,
    FeatureDocument,
    FeatureName,
    FeatureObject,
    FeatureReadDocument,
    DocumentName,
    make_helical_sweep_feature_failure,
    make_helical_sweep_feature_success,
    make_helical_sweep_feature_uncertain,
)
from .helical_sweep_feature_mutation import HelicalSweepFeatureError, run_helical_sweep_feature_native_mutation
from .feature_apply_support import (
    bool_value,
    create_feature,
    is_derived_from,
    nonempty_string,
    number_value,
    optional_name,
    require_absent,
    require_nonempty_shape,
    require_object,
    resolve_optional_body,
    set_attr,
    set_feature_bool,
    set_tip,
)


@dataclass(frozen=True, slots=True)
class HelicalSweepFeatureReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class HelicalSweepFeatureInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: HelicalSweepFeatureError, *, retry_safe: bool = True) -> HelicalSweepFeatureFailure:
    return make_helical_sweep_feature_failure(error.code, str(error), retry_safe=retry_safe)


def apply_helical_sweep_feature(doc: FeatureDocument, request: HelicalSweepFeatureRequest) -> HelicalSweepFeatureReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.helix_name)
        profile = require_object(
            doc, request.profile_sketch, missing="Profile sketch not found"
        )
        body = resolve_optional_body(doc, profile, request.body_name)
        created = create_feature(doc, body, 'PartDesign::AdditiveHelix', request.helix_name)
        set_attr(created, "Profile", (profile, [""]))
        set_attr(created, "ReferenceAxis", (profile, ["V_Axis"]))
        set_attr(created, "Mode", 0)
        set_attr(created, "Pitch", request.pitch)
        set_attr(created, "Height", request.height)
        properties = set(getattr(created, "PropertiesList", []))
        if not properties or "Radius" in properties:
            set_attr(created, "Radius", request.radius)
        set_attr(created, "Angle", 0)
        set_attr(created, "Growth", 0)
        set_feature_bool(created, ("LeftHanded",), request.left_handed)
        set_feature_bool(created, ("Reversed",), request.reversed_dir)
        if body is not None:
            set_tip(body, created)
        return HelicalSweepFeatureReceipt(name=str(created.Name), feature=created)
    except HelicalSweepFeatureError:
        raise
    except FileExistsError as exc:
        raise HelicalSweepFeatureError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise HelicalSweepFeatureError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise HelicalSweepFeatureError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise HelicalSweepFeatureError(
            "HELICAL_SWEEP_FEATURE_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_helical_sweep_feature_result(doc: FeatureReadDocument, receipt: HelicalSweepFeatureReceipt) -> HelicalSweepFeatureInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise HelicalSweepFeatureError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise HelicalSweepFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'PartDesign::AdditiveHelix'):
        raise HelicalSweepFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::AdditiveHelix: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise HelicalSweepFeatureError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return HelicalSweepFeatureInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_helical_sweep_feature_request(
    doc_name: str, profile_sketch: str, helix_name: str, pitch: float, height: float, radius: float, body_name: str | None = None, left_handed: bool = False, reversed_dir: bool = False
) -> HelicalSweepFeatureRequest | HelicalSweepFeatureFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        profile = FeatureName(nonempty_string(profile_sketch, "profile_sketch"))
        created = FeatureName(nonempty_string(helix_name, "helix_name"))
        pitch_value = number_value(pitch, "pitch", positive=True)
        height_value = number_value(height, "height", positive=True)
        radius_value = number_value(radius, "radius", positive=True)
        body = optional_name(body_name, "body_name")
        left = bool_value(left_handed, "left_handed")
        reversed_value = bool_value(reversed_dir, "reversed_dir")
    except ValueError as exc:
        return _failure(HelicalSweepFeatureError("INVALID_ARGUMENT", str(exc)))
    return HelicalSweepFeatureRequest(
        doc_name=doc,
        profile_sketch=profile,
        helix_name=created,
        pitch=pitch_value,
        height=height_value,
        radius=radius_value,
        body_name=None if body is None else FeatureName(body),
        left_handed=left,
        reversed_dir=reversed_value,
    )


@dataclass(slots=True)
class _HelicalSweepFeatureExecution:
    collaborators: HelicalSweepFeatureCollaborators
    request: HelicalSweepFeatureRequest
    created: HelicalSweepFeatureReceipt | None = None
    inspected: HelicalSweepFeatureInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_helical_sweep_feature(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise HelicalSweepFeatureError(
                "INVALID_HELICAL_SWEEP_FEATURE_RESULT",
                "helical_sweep_feature did not return an identity receipt",
            )
        self.inspected = read_helical_sweep_feature_result(doc, self.created)

    def run(self) -> HelicalSweepFeatureResult:
        result = run_helical_sweep_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_helical_sweep_feature_uncertain(
                "HELICAL_SWEEP_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected helical_sweep_feature result",
                committed=True,
            )
        return make_helical_sweep_feature_success(self.inspected.name, self.inspected.label)


def run_helical_sweep_feature(
    collaborators: HelicalSweepFeatureCollaborators,
    doc_name: str, profile_sketch: str, helix_name: str, pitch: float, height: float, radius: float, body_name: str | None = None, left_handed: bool = False, reversed_dir: bool = False
) -> HelicalSweepFeatureResult:
    """Run helical_sweep_feature through apply, recompute, inspection, and commit."""

    request = build_helical_sweep_feature_request(doc_name, profile_sketch, helix_name, pitch, height, radius, body_name, left_handed, reversed_dir)
    if isinstance(request, dict):
        return request
    return _HelicalSweepFeatureExecution(collaborators, request).run()


class _HelicalSweepFeatureRpcFacade(Protocol):
    _cad_collaborators: HelicalSweepFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_helical_sweep_feature(
    self: _HelicalSweepFeatureRpcFacade,
    doc_name: str, profile_sketch: str, helix_name: str, pitch: float, height: float, radius: float, body_name: str | None = None, left_handed: bool = False, reversed_dir: bool = False
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_helical_sweep_feature(collaborators, doc_name, profile_sketch, helix_name, pitch, height, radius, body_name, left_handed, reversed_dir)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("helical_sweep_feature", rpc_helical_sweep_feature)


__all__ = [
    "HelicalSweepFeatureCollaborators",
    "HelicalSweepFeatureError",
    "HelicalSweepFeatureInspection",
    "HelicalSweepFeatureReceipt",
    "apply_helical_sweep_feature",
    "build_helical_sweep_feature_request",
    "read_helical_sweep_feature_result",
    "rpc_helical_sweep_feature",
    "run_helical_sweep_feature",
    "TYPED_RPC_HANDLER",
]
