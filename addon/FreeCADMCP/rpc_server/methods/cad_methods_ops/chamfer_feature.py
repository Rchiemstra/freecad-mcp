
"""Typed ``chamfer_feature`` mutation."""
from __future__ import annotations

from .feature_lookup_support import (
    is_derived_from,
    require_absent,
    require_object,
    resolve_optional_body,
)
from .feature_mutate_support import (
    create_feature,
    nonempty_string,
    number_value,
    optional_name,
    require_nonempty_shape,
    set_attr,
    set_tip,
    string_list,
)

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

try:
    from ...._shared.protocol.chamfer_feature_contract import (
        ChamferFeatureCollaborators,
        ChamferFeatureFailure,
        ChamferFeatureRequest,
        ChamferFeatureResult,
        FeatureDocument,
        FeatureName,
        FeatureObject,
        FeatureReadDocument,
        DocumentName,
        make_chamfer_feature_failure,
        make_chamfer_feature_success,
        make_chamfer_feature_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.chamfer_feature_contract import (
        ChamferFeatureCollaborators,
        ChamferFeatureFailure,
        ChamferFeatureRequest,
        ChamferFeatureResult,
        FeatureDocument,
        FeatureName,
        FeatureObject,
        FeatureReadDocument,
        DocumentName,
        make_chamfer_feature_failure,
        make_chamfer_feature_success,
        make_chamfer_feature_uncertain,
    )
from .chamfer_feature_mutation import ChamferFeatureError, run_chamfer_feature_native_mutation



@dataclass(frozen=True, slots=True)
class ChamferFeatureReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    feature: FeatureObject


@dataclass(frozen=True, slots=True)
class ChamferFeatureInspection:
    """Read-only data captured after the native-owned recompute."""

    name: FeatureName
    label: str


def _failure(error: ChamferFeatureError, *, retry_safe: bool = True) -> ChamferFeatureFailure:
    return make_chamfer_feature_failure(error.code, str(error), retry_safe=retry_safe)


def apply_chamfer_feature(doc: FeatureDocument, request: ChamferFeatureRequest) -> ChamferFeatureReceipt:
    """Apply the mutation without recomputing or managing a transaction."""

    try:
        require_absent(doc, request.chamfer_name)
        base = require_object(
            doc, request.base_feature, missing="Base feature not found"
        )
        body = resolve_optional_body(doc, base, request.body_name)
        created = create_feature(doc, body, 'PartDesign::Chamfer', request.chamfer_name)
        edges = list(request.edge_refs)
        if edges:
            set_attr(created, "Base", (base, edges))
            set_attr(created, "UseAllEdges", False)
        else:
            set_attr(created, "UseAllEdges", True)
            set_attr(created, "Base", (base, [""]))
        set_attr(created, "Size", request.size)
        if body is not None:
            set_tip(body, created)
        return ChamferFeatureReceipt(name=str(created.Name), feature=created)
    except ChamferFeatureError:
        raise
    except FileExistsError as exc:
        raise ChamferFeatureError(
            "OBJECT_ALREADY_EXISTS",
            f"Object already exists: {exc}",
        ) from exc
    except LookupError as exc:
        raise ChamferFeatureError("OBJECT_NOT_FOUND", str(exc)) from exc
    except ValueError as exc:
        raise ChamferFeatureError("INVALID_ARGUMENT", str(exc)) from exc
    except Exception as exc:
        raise ChamferFeatureError(
            "CHAMFER_FEATURE_FAILED",
            str(exc) or type(exc).__name__,
        ) from exc


def read_chamfer_feature_result(doc: FeatureReadDocument, receipt: ChamferFeatureReceipt) -> ChamferFeatureInspection:
    """Build the public result after the shared mutation recompute."""

    feature = doc.getObject(receipt.name)
    if feature is None:
        raise ChamferFeatureError(
            "CREATED_OBJECT_MISSING",
            f"Created feature is missing: {receipt.name!r}",
        )
    if feature is not receipt.feature:
        raise ChamferFeatureError(
            "CREATED_OBJECT_REPLACED",
            f"Created feature was replaced before commit: {receipt.name!r}",
        )
    if not is_derived_from(feature, 'PartDesign::Chamfer'):
        raise ChamferFeatureError(
            "CREATED_OBJECT_WRONG_TYPE",
            f"Created object is not PartDesign::Chamfer: {receipt.name!r}",
        )
    try:
        require_nonempty_shape(
            feature,
            missing=f"Created object has empty Shape: {receipt.name!r}",
        )
    except LookupError as exc:
        raise ChamferFeatureError("CREATED_OBJECT_INVALID", str(exc)) from exc
    return ChamferFeatureInspection(
        name=FeatureName(receipt.name),
        label=str(feature.Label),
    )


def build_chamfer_feature_request(
    doc_name: str, base_feature: str, chamfer_name: str, size: float, edge_refs: list[str] | None = None, body_name: str | None = None
) -> ChamferFeatureRequest | ChamferFeatureFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    try:
        doc = DocumentName(nonempty_string(doc_name, "doc_name"))
        base = FeatureName(nonempty_string(base_feature, "base_feature"))
        created = FeatureName(nonempty_string(chamfer_name, "chamfer_name"))
        size_value = number_value(size, "size", positive=True)
        edges = tuple(string_list(edge_refs or [], "edge_refs"))
        body = optional_name(body_name, "body_name")
    except ValueError as exc:
        return _failure(ChamferFeatureError("INVALID_ARGUMENT", str(exc)))
    return ChamferFeatureRequest(
        doc_name=doc,
        base_feature=base,
        chamfer_name=created,
        size=size_value,
        edge_refs=edges,
        body_name=None if body is None else FeatureName(body),
    )


@dataclass(slots=True)
class _ChamferFeatureExecution:
    collaborators: ChamferFeatureCollaborators
    request: ChamferFeatureRequest
    created: ChamferFeatureReceipt | None = None
    inspected: ChamferFeatureInspection | None = None

    def apply(self, doc: FeatureDocument) -> None:
        self.created = apply_chamfer_feature(doc, self.request)

    def inspect(self, doc: FeatureReadDocument) -> None:
        if self.created is None:
            raise ChamferFeatureError(
                "INVALID_CHAMFER_FEATURE_RESULT",
                "chamfer_feature did not return an identity receipt",
            )
        self.inspected = read_chamfer_feature_result(doc, self.created)

    def run(self) -> ChamferFeatureResult:
        result = run_chamfer_feature_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_chamfer_feature_uncertain(
                "CHAMFER_FEATURE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected chamfer_feature result",
                committed=True,
            )
        return make_chamfer_feature_success(self.inspected.name, self.inspected.label)


def run_chamfer_feature(
    collaborators: ChamferFeatureCollaborators,
    doc_name: str, base_feature: str, chamfer_name: str, size: float, edge_refs: list[str] | None = None, body_name: str | None = None
) -> ChamferFeatureResult:
    """Run chamfer_feature through apply, recompute, inspection, and commit."""

    request = build_chamfer_feature_request(doc_name, base_feature, chamfer_name, size, edge_refs, body_name)
    if isinstance(request, dict):
        return request
    return _ChamferFeatureExecution(collaborators, request).run()


class _ChamferFeatureRpcFacade(Protocol):
    _cad_collaborators: ChamferFeatureCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_chamfer_feature(
    self: _ChamferFeatureRpcFacade,
    doc_name: str, base_feature: str, chamfer_name: str, size: float, edge_refs: list[str] | None = None, body_name: str | None = None
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_chamfer_feature(collaborators, doc_name, base_feature, chamfer_name, size, edge_refs, body_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("chamfer_feature", rpc_chamfer_feature)


__all__ = [
    "ChamferFeatureCollaborators",
    "ChamferFeatureError",
    "ChamferFeatureInspection",
    "ChamferFeatureReceipt",
    "apply_chamfer_feature",
    "build_chamfer_feature_request",
    "read_chamfer_feature_result",
    "rpc_chamfer_feature",
    "run_chamfer_feature",
    "TYPED_RPC_HANDLER",
]
