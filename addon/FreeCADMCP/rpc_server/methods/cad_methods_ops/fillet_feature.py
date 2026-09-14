"""Typed ``fillet_feature`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.fillet_feature_contract import (
    FilletFeatureCollaborators,
    FilletFeatureFailure,
    FilletFeatureRequest,
    FilletFeatureResult,
    FeatureDocument,
    FeatureName,
    FeatureObject,
    FeatureReadDocument,
    DocumentName,
    make_fillet_feature_failure,
    make_fillet_feature_success,
    make_fillet_feature_uncertain,
)
from .fillet_feature_mutation import FilletFeatureError, run_fillet_feature_native_mutation
from .feature_apply_support import (
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
    set_tip,
    string_list,
)


@dataclass(frozen=True, slots=True)
class FilletFeatureReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class FilletFeatureInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: FilletFeatureError, *, retry_safe: bool = True) -> FilletFeatureFailure:
    return make_fillet_feature_failure(error.code, str(error), retry_safe=retry_safe)


def apply_fillet_feature(doc: FeatureDocument, request: FilletFeatureRequest) -> FilletFeatureReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.fillet_name)
        base = require_object(
            doc, request.base_feature, missing="Base feature not found"
        )
        body = resolve_optional_body(doc, base, request.body_name)
        created = create_feature(doc, body, 'PartDesign::Fillet', request.fillet_name)
        edges = list(request.edge_refs)
        if edges:
            set_attr(created, "Base", (base, edges))
            set_attr(created, "UseAllEdges", False)
        else:
            set_attr(created, "UseAllEdges", True)
            set_attr(created, "Base", (base, [""]))
        set_attr(created, "Radius", request.radius)
        if body is not None:
            set_tip(body, created)
        return FilletFeatureReceipt(name=str(created.Name), feature=created)
    except FilletFeatureError:
        raise
    except FileExistsError as exc:
        raise FilletFeatureError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise FilletFeatureError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise FilletFeatureError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise FilletFeatureError(
            "FILLET_FEATURE_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_fillet_feature_result(doc: FeatureReadDocument, receipt: FilletFeatureReceipt) -> FilletFeatureInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise FilletFeatureError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise FilletFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'PartDesign::Fillet'):
        raise FilletFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::Fillet: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise FilletFeatureError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return FilletFeatureInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_fillet_feature_request(
    doc_name: str, base_feature: str, fillet_name: str, radius: float, edge_refs: list[str] | None = None, body_name: str | None = None
) -> FilletFeatureRequest | FilletFeatureFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        base = FeatureName(nonempty_string(base_feature, "base_feature"))
        created = FeatureName(nonempty_string(fillet_name, "fillet_name"))
        radius_value = number_value(radius, "radius", positive=True)
        edges = tuple(string_list(edge_refs or [], "edge_refs"))
        body = optional_name(body_name, "body_name")
    except ValueError as exc:
        return _failure(FilletFeatureError("INVALID_ARGUMENT", str(exc)))
    return FilletFeatureRequest(
        doc_name=doc,
        base_feature=base,
        fillet_name=created,
        radius=radius_value,
        edge_refs=edges,
        body_name=None if body is None else FeatureName(body),
    )


@dataclass(slots=True)
class _FilletFeatureExecution:
    collaborators: FilletFeatureCollaborators
    request: FilletFeatureRequest
    created: FilletFeatureReceipt | None = None
    inspected: FilletFeatureInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_fillet_feature(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise FilletFeatureError(
                "INVALID_FILLET_FEATURE_RESULT",
                "fillet_feature did not return an identity receipt",
            )
        self.inspected = read_fillet_feature_result(doc, self.created)

    def run(self) -> FilletFeatureResult:
        result = run_fillet_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_fillet_feature_uncertain(
                "FILLET_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected fillet_feature result",
                committed=True,
            )
        return make_fillet_feature_success(self.inspected.name, self.inspected.label)


def run_fillet_feature(
    collaborators: FilletFeatureCollaborators,
    doc_name: str, base_feature: str, fillet_name: str, radius: float, edge_refs: list[str] | None = None, body_name: str | None = None
) -> FilletFeatureResult:
    """Run fillet_feature through apply, recompute, inspection, and commit."""

    request = build_fillet_feature_request(doc_name, base_feature, fillet_name, radius, edge_refs, body_name)
    if isinstance(request, dict):
        return request
    return _FilletFeatureExecution(collaborators, request).run()


class _FilletFeatureRpcFacade(Protocol):
    _cad_collaborators: FilletFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_fillet_feature(
    self: _FilletFeatureRpcFacade,
    doc_name: str, base_feature: str, fillet_name: str, radius: float, edge_refs: list[str] | None = None, body_name: str | None = None
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_fillet_feature(collaborators, doc_name, base_feature, fillet_name, radius, edge_refs, body_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("fillet_feature", rpc_fillet_feature)


__all__ = [
    "FilletFeatureCollaborators",
    "FilletFeatureError",
    "FilletFeatureInspection",
    "FilletFeatureReceipt",
    "apply_fillet_feature",
    "build_fillet_feature_request",
    "read_fillet_feature_result",
    "rpc_fillet_feature",
    "run_fillet_feature",
    "TYPED_RPC_HANDLER",
]
