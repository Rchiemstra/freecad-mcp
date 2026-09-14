"""Typed ``body_set_tip`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.body_set_tip_contract import (
    BodyName,
    BodySetTipCollaborators,
    BodySetTipFailure,
    BodySetTipRequest,
    BodySetTipResult,
    DocumentName,
    FeatureName,
    TipBodyDocument,
    TipBodyWriteObject,
    TipNamedObject,
    TipReadDocument,
    make_body_set_tip_failure,
    make_body_set_tip_success,
    make_body_set_tip_uncertain,
)
from .body_set_tip_mutation import BodySetTipError, run_body_set_tip_native_mutation


@dataclass(frozen=True, slots=True)
class BodySetTipReceipt:
    """Internal identity captured while applying the mutation."""

    body_name: str
    feature_name: str
    body: TipBodyWriteObject
    feature: TipNamedObject


@dataclass(frozen=True, slots=True)
class BodySetTipInspection:
    """Read-only data captured after the native-owned recompute."""

    body: BodyName
    tip: FeatureName
    feature: FeatureName


def _failure(error: BodySetTipError, *, retry_safe: bool = True) -> BodySetTipFailure:
    return make_body_set_tip_failure(error.code, str(error), retry_safe=retry_safe)


def _is_partdesign_body(body: TipNamedObject) -> bool:
    try:
        return bool(body.isDerivedFrom("PartDesign::Body"))
    except (AttributeError, TypeError):
        return body.TypeId == "PartDesign::Body"


def _is_partdesign_feature(feature: TipNamedObject) -> bool:
    try:
        return bool(feature.isDerivedFrom("PartDesign::Feature"))
    except (AttributeError, TypeError):
        return feature.TypeId.startswith("PartDesign::") and feature.TypeId != "PartDesign::Body"


def apply_body_set_tip(
    doc: TipBodyDocument,
    body_name: BodyName,
    feature_name: FeatureName,
) -> BodySetTipReceipt:
    """Assign Body.Tip without recomputing or managing a transaction."""

    if not isinstance(body_name, str):
        raise BodySetTipError("INVALID_ARGUMENT", "body_name must be a string")
    if not body_name.strip():
        raise BodySetTipError("INVALID_ARGUMENT", "body_name must not be empty")
    if not isinstance(feature_name, str):
        raise BodySetTipError("INVALID_ARGUMENT", "feature_name must be a string")
    if not feature_name.strip():
        raise BodySetTipError("INVALID_ARGUMENT", "feature_name must not be empty")

    body = doc.getObject(body_name)
    if body is None:
        raise BodySetTipError("BODY_NOT_FOUND", f"Body not found: {body_name!r}")
    if not _is_partdesign_body(body):
        raise BodySetTipError(
            "BODY_WRONG_TYPE",
            f"Object is not a PartDesign::Body: {body_name!r}",
        )

    feature = doc.getObject(feature_name)
    if feature is None:
        raise BodySetTipError("FEATURE_NOT_FOUND", f"Feature not found: {feature_name!r}")
    if not _is_partdesign_feature(feature):
        raise BodySetTipError(
            "FEATURE_WRONG_TYPE",
            f"Object is not a PartDesign feature: {feature_name!r}",
        )

    body.Tip = feature
    return BodySetTipReceipt(
        body_name=body.Name,
        feature_name=feature.Name,
        body=body,
        feature=feature,
    )


def read_body_set_tip_result(
    doc: TipReadDocument, receipt: BodySetTipReceipt
) -> BodySetTipInspection:
    """Build the public result after the shared mutation recompute."""

    body = doc.getObject(receipt.body_name)
    if body is None:
        raise BodySetTipError(
            "BODY_NOT_FOUND",
            f"Body is missing after recompute: {receipt.body_name!r}",
        )
    if body is not receipt.body:
        raise BodySetTipError(
            "BODY_REPLACED",
            f"Body was replaced before commit: {receipt.body_name!r}",
        )
    if not _is_partdesign_body(body):
        raise BodySetTipError(
            "BODY_WRONG_TYPE",
            f"Object is not a PartDesign::Body: {receipt.body_name!r}",
        )
    tip = body.Tip
    if tip is None:
        raise BodySetTipError(
            "TIP_NOT_UPDATED",
            f"Body Tip is empty after assignment: {receipt.body_name!r}",
        )
    if tip is not receipt.feature:
        raise BodySetTipError(
            "TIP_NOT_UPDATED",
            f"Body Tip was not set to {receipt.feature_name!r}",
        )
    return BodySetTipInspection(
        body=BodyName(receipt.body_name),
        tip=FeatureName(tip.Name),
        feature=FeatureName(receipt.feature_name),
    )


def build_body_set_tip_request(
    doc_name: object, body_name: object, feature_name: object
) -> BodySetTipRequest | BodySetTipFailure:
    """Validate the untyped JSON arguments before constructing internal name types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(BodySetTipError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    if not isinstance(body_name, str) or not body_name.strip():
        return _failure(BodySetTipError("INVALID_ARGUMENT", "body_name must be a nonempty string"))
    if not isinstance(feature_name, str) or not feature_name.strip():
        return _failure(
            BodySetTipError("INVALID_ARGUMENT", "feature_name must be a nonempty string")
        )
    return BodySetTipRequest(
        doc_name=DocumentName(doc_name),
        body_name=BodyName(body_name),
        feature_name=FeatureName(feature_name),
    )


@dataclass(slots=True)
class _BodySetTipExecution:
    collaborators: BodySetTipCollaborators
    request: BodySetTipRequest
    assigned: BodySetTipReceipt | None = None
    inspected: BodySetTipInspection | None = None

    def apply(self, doc: TipBodyDocument) -> None:
        self.assigned = apply_body_set_tip(
            doc, self.request.body_name, self.request.feature_name
        )

    def inspect(self, doc: TipReadDocument) -> None:
        if self.assigned is None:
            raise BodySetTipError(
                "INVALID_BODY_SET_TIP_RESULT",
                "Body Tip assignment did not return an identity receipt",
            )
        self.inspected = read_body_set_tip_result(doc, self.assigned)

    def run(self) -> BodySetTipResult:
        result = run_body_set_tip_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_body_set_tip_uncertain(
                "BODY_SET_TIP_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected Body Tip result",
                committed=True,
            )
        return make_body_set_tip_success(
            self.inspected.body, self.inspected.tip, self.inspected.feature
        )


def run_body_set_tip(
    collaborators: BodySetTipCollaborators,
    doc_name: object,
    body_name: object,
    feature_name: object,
) -> BodySetTipResult:
    """Run Body Tip assignment through apply, recompute, inspection, and commit."""

    request = build_body_set_tip_request(doc_name, body_name, feature_name)
    if isinstance(request, dict):
        return request
    return _BodySetTipExecution(collaborators, request).run()


class _BodySetTipRpcFacade(Protocol):
    _cad_collaborators: BodySetTipCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_body_set_tip(
    self: _BodySetTipRpcFacade,
    doc_name: str,
    body_name: str,
    feature_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_body_set_tip(collaborators, doc_name, body_name, feature_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("body_set_tip", rpc_body_set_tip)


__all__ = [
    "BodySetTipCollaborators",
    "BodySetTipError",
    "BodySetTipInspection",
    "BodySetTipReceipt",
    "apply_body_set_tip",
    "build_body_set_tip_request",
    "read_body_set_tip_result",
    "rpc_body_set_tip",
    "run_body_set_tip",
    "TYPED_RPC_HANDLER",
]
