
"""Typed ``mirror_feature`` mutation."""
from __future__ import annotations

from .feature_lookup_support import (
    is_derived_from,
    require_absent,
    require_body,
    require_object,
    resolve_linksub,
)
from .feature_mutate_support import (
    create_feature,
    nonempty_string,
    optional_name,
    require_nonempty_shape,
    set_named_property,
    set_originals,
    set_tip,
)

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.mirror_feature_contract import (
    MirrorFeatureCollaborators,
    MirrorFeatureFailure,
    MirrorFeatureRequest,
    MirrorFeatureResult,
    FeatureDocument,
    FeatureName,
    FeatureObject,
    FeatureReadDocument,
    DocumentName,
    make_mirror_feature_failure,
    make_mirror_feature_success,
    make_mirror_feature_uncertain,
)
from .mirror_feature_mutation import MirrorFeatureError, run_mirror_feature_native_mutation



@dataclass(frozen=True, slots=True)
class MirrorFeatureReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class MirrorFeatureInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: MirrorFeatureError, *, retry_safe: bool = True) -> MirrorFeatureFailure:
    return make_mirror_feature_failure(error.code, str(error), retry_safe=retry_safe)


def apply_mirror_feature(doc: FeatureDocument, request: MirrorFeatureRequest) -> MirrorFeatureReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.mirror_name)
        source = require_object(
            doc, request.feature_name, missing="Source feature not found"
        )
        body = require_body(doc, source, request.body_name)
        created = create_feature(doc, body, 'PartDesign::Mirrored', request.mirror_name)
        set_originals(created, source)
        set_named_property(
            created,
            ("MirrorPlane", "Plane"),
            resolve_linksub(doc, body, request.plane),
        )
        set_tip(body, created)
        return MirrorFeatureReceipt(name=str(created.Name), feature=created)
    except MirrorFeatureError:
        raise
    except FileExistsError as exc:
        raise MirrorFeatureError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise MirrorFeatureError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise MirrorFeatureError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise MirrorFeatureError(
            "MIRROR_FEATURE_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_mirror_feature_result(doc: FeatureReadDocument, receipt: MirrorFeatureReceipt) -> MirrorFeatureInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise MirrorFeatureError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise MirrorFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'PartDesign::Mirrored'):
        raise MirrorFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::Mirrored: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise MirrorFeatureError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return MirrorFeatureInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_mirror_feature_request(
    doc_name: str, feature_name: str, mirror_name: str, plane: str = 'YZ_Plane', body_name: str | None = None
) -> MirrorFeatureRequest | MirrorFeatureFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        source = FeatureName(nonempty_string(feature_name, "feature_name"))
        created = FeatureName(nonempty_string(mirror_name, "mirror_name"))
        plane_value = nonempty_string(plane, "plane")
        body = optional_name(body_name, "body_name")
    except ValueError as exc:
        return _failure(MirrorFeatureError("INVALID_ARGUMENT", str(exc)))
    return MirrorFeatureRequest(
        doc_name=doc,
        feature_name=source,
        mirror_name=created,
        plane=plane_value,
        body_name=None if body is None else FeatureName(body),
    )


@dataclass(slots=True)
class _MirrorFeatureExecution:
    collaborators: MirrorFeatureCollaborators
    request: MirrorFeatureRequest
    created: MirrorFeatureReceipt | None = None
    inspected: MirrorFeatureInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_mirror_feature(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise MirrorFeatureError(
                "INVALID_MIRROR_FEATURE_RESULT",
                "mirror_feature did not return an identity receipt",
            )
        self.inspected = read_mirror_feature_result(doc, self.created)

    def run(self) -> MirrorFeatureResult:
        result = run_mirror_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_mirror_feature_uncertain(
                "MIRROR_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected mirror_feature result",
                committed=True,
            )
        return make_mirror_feature_success(self.inspected.name, self.inspected.label)


def run_mirror_feature(
    collaborators: MirrorFeatureCollaborators,
    doc_name: str, feature_name: str, mirror_name: str, plane: str = 'YZ_Plane', body_name: str | None = None
) -> MirrorFeatureResult:
    """Run mirror_feature through apply, recompute, inspection, and commit."""

    request = build_mirror_feature_request(doc_name, feature_name, mirror_name, plane, body_name)
    if isinstance(request, dict):
        return request
    return _MirrorFeatureExecution(collaborators, request).run()


class _MirrorFeatureRpcFacade(Protocol):
    _cad_collaborators: MirrorFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_mirror_feature(
    self: _MirrorFeatureRpcFacade,
    doc_name: str, feature_name: str, mirror_name: str, plane: str = 'YZ_Plane', body_name: str | None = None
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_mirror_feature(collaborators, doc_name, feature_name, mirror_name, plane, body_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("mirror_feature", rpc_mirror_feature)


__all__ = [
    "MirrorFeatureCollaborators",
    "MirrorFeatureError",
    "MirrorFeatureInspection",
    "MirrorFeatureReceipt",
    "apply_mirror_feature",
    "build_mirror_feature_request",
    "read_mirror_feature_result",
    "rpc_mirror_feature",
    "run_mirror_feature",
    "TYPED_RPC_HANDLER",
]
