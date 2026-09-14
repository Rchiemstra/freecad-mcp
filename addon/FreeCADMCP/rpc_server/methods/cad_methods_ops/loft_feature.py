"""Typed ``loft_feature`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.loft_feature_contract import (
    LoftFeatureCollaborators,
    LoftFeatureFailure,
    LoftFeatureRequest,
    LoftFeatureResult,
    FeatureDocument,
    FeatureName,
    FeatureObject,
    FeatureReadDocument,
    DocumentName,
    make_loft_feature_failure,
    make_loft_feature_success,
    make_loft_feature_uncertain,
)
from .loft_feature_mutation import LoftFeatureError, run_loft_feature_native_mutation
from .feature_apply_support import (
    bool_value,
    create_feature,
    is_derived_from,
    nonempty_string,
    optional_name,
    require_absent,
    require_nonempty_shape,
    require_object,
    resolve_optional_body,
    set_attr,
    set_tip,
    string_list,
)


@dataclass(frozen=True, slots=True)
class LoftFeatureReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class LoftFeatureInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: LoftFeatureError, *, retry_safe: bool = True) -> LoftFeatureFailure:
    return make_loft_feature_failure(error.code, str(error), retry_safe=retry_safe)


def apply_loft_feature(doc: FeatureDocument, request: LoftFeatureRequest) -> LoftFeatureReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.loft_name)
        profiles = [
            require_object(doc, name, missing="One or more sketches not found")
            for name in request.sketch_names
        ]
        body = resolve_optional_body(doc, profiles[0], request.body_name)
        created = create_feature(doc, body, 'PartDesign::AdditiveLoft', request.loft_name)
        profile = profiles[0]
        sections = profiles[1:]
        set_attr(created, "Profile", profile)
        if sections:
            set_attr(created, "Sections", sections)
        set_attr(created, "Ruled", request.ruled)
        set_attr(created, "Closed", request.closed)
        if body is not None:
            set_tip(body, created)
        return LoftFeatureReceipt(name=str(created.Name), feature=created)
    except LoftFeatureError:
        raise
    except FileExistsError as exc:
        raise LoftFeatureError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise LoftFeatureError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise LoftFeatureError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise LoftFeatureError(
            "LOFT_FEATURE_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_loft_feature_result(doc: FeatureReadDocument, receipt: LoftFeatureReceipt) -> LoftFeatureInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise LoftFeatureError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise LoftFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'PartDesign::AdditiveLoft'):
        raise LoftFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::AdditiveLoft: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise LoftFeatureError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return LoftFeatureInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_loft_feature_request(
    doc_name: str, sketch_names: list[str], loft_name: str, body_name: str | None = None, ruled: bool = False, closed: bool = False
) -> LoftFeatureRequest | LoftFeatureFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        sketches = tuple(
            FeatureName(name) for name in string_list(sketch_names, "sketch_names", minimum=2)
        )
        created = FeatureName(nonempty_string(loft_name, "loft_name"))
        body = optional_name(body_name, "body_name")
        ruled_value = bool_value(ruled, "ruled")
        closed_value = bool_value(closed, "closed")
    except ValueError as exc:
        return _failure(LoftFeatureError("INVALID_ARGUMENT", str(exc)))
    return LoftFeatureRequest(
        doc_name=doc,
        sketch_names=sketches,
        loft_name=created,
        body_name=None if body is None else FeatureName(body),
        ruled=ruled_value,
        closed=closed_value,
    )


@dataclass(slots=True)
class _LoftFeatureExecution:
    collaborators: LoftFeatureCollaborators
    request: LoftFeatureRequest
    created: LoftFeatureReceipt | None = None
    inspected: LoftFeatureInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_loft_feature(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise LoftFeatureError(
                "INVALID_LOFT_FEATURE_RESULT",
                "loft_feature did not return an identity receipt",
            )
        self.inspected = read_loft_feature_result(doc, self.created)

    def run(self) -> LoftFeatureResult:
        result = run_loft_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_loft_feature_uncertain(
                "LOFT_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected loft_feature result",
                committed=True,
            )
        return make_loft_feature_success(self.inspected.name, self.inspected.label)


def run_loft_feature(
    collaborators: LoftFeatureCollaborators,
    doc_name: str, sketch_names: list[str], loft_name: str, body_name: str | None = None, ruled: bool = False, closed: bool = False
) -> LoftFeatureResult:
    """Run loft_feature through apply, recompute, inspection, and commit."""

    request = build_loft_feature_request(doc_name, sketch_names, loft_name, body_name, ruled, closed)
    if isinstance(request, dict):
        return request
    return _LoftFeatureExecution(collaborators, request).run()


class _LoftFeatureRpcFacade(Protocol):
    _cad_collaborators: LoftFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_loft_feature(
    self: _LoftFeatureRpcFacade,
    doc_name: str, sketch_names: list[str], loft_name: str, body_name: str | None = None, ruled: bool = False, closed: bool = False
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_loft_feature(collaborators, doc_name, sketch_names, loft_name, body_name, ruled, closed)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("loft_feature", rpc_loft_feature)


__all__ = [
    "LoftFeatureCollaborators",
    "LoftFeatureError",
    "LoftFeatureInspection",
    "LoftFeatureReceipt",
    "apply_loft_feature",
    "build_loft_feature_request",
    "read_loft_feature_result",
    "rpc_loft_feature",
    "run_loft_feature",
    "TYPED_RPC_HANDLER",
]
