
"""Typed ``clear_expression`` mutation."""
from __future__ import annotations

import re

from .native_commit_wait import NativeOutcome, settle_native_commit

from .typed_rpc_support import (
    call_named,
    nonempty_string,
    object_label,
    object_name,
    require_object,
)

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

try:
    from ...._shared.protocol.clear_expression_contract import (
        ClearExpressionCollaborators,
        ClearExpressionDocument,
        ClearExpressionFailure,
        ClearExpressionName,
        ClearExpressionReadDocument,
        ClearExpressionRequest,
        ClearExpressionResult,
        ClearExpressionUncertain,
        DocumentName,
        make_clear_expression_failure,
        make_clear_expression_success,
        make_clear_expression_uncertain,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.clear_expression_contract import (
        ClearExpressionCollaborators,
        ClearExpressionDocument,
        ClearExpressionFailure,
        ClearExpressionName,
        ClearExpressionReadDocument,
        ClearExpressionRequest,
        ClearExpressionResult,
        ClearExpressionUncertain,
        DocumentName,
        make_clear_expression_failure,
        make_clear_expression_success,
        make_clear_expression_uncertain,
    )
from .clear_expression_mutation import ClearExpressionError, run_clear_expression_native_mutation

try:
    from ....native_error_boundary import (
        NativeErrorBaseline, capture_native_error_baseline, native_error_validation_scope,
        existing_native_error_unchanged,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from native_error_boundary import (
        NativeErrorBaseline, capture_native_error_baseline, native_error_validation_scope,
        existing_native_error_unchanged,
    )



@dataclass(frozen=True, slots=True)
class ClearExpressionReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    prop_path: str
    skipped: bool = False


@dataclass(frozen=True, slots=True)
class ClearExpressionInspection:
    """Read-only data captured after the native-owned recompute."""

    name: ClearExpressionName
    label: str


def _failure(error: ClearExpressionError, *, retry_safe: bool = True) -> ClearExpressionFailure:
    return make_clear_expression_failure(error.code, str(error), retry_safe=retry_safe)


def _has_property(item: object, prop_path: str) -> bool:
    # Expression paths address a property or one of its components. Let
    # FreeCAD validate the component after checking that its root exists.
    root = re.split(r"[.\[]", prop_path.strip().lstrip("."), maxsplit=1)[0]
    props = getattr(item, "PropertiesList", None)
    if isinstance(props, (list, tuple)):
        return root in props
    return hasattr(item, root)


def _expression_remaining(item: object, prop_path: str) -> bool:
    path = prop_path.lstrip(".")
    keys = {path}
    indexed = re.fullmatch(r"Constraints\[(\d+)\]", path)
    constraints = getattr(item, "Constraints", ())
    if indexed and isinstance(constraints, (list, tuple)):
        index = int(indexed[1])
        if index < len(constraints):
            name = getattr(constraints[index], "Name", "")
            if name:
                keys.add(f"Constraints.{name}")
    getter = getattr(item, "getExpression", None)
    if callable(getter):
        for key in keys:
            if getter(key) not in (None, ""):
                return True
    # Native sketches expose canonical named paths through ExpressionEngine;
    # getExpression is unavailable on some FreeCAD object types.
    for key, expression in getattr(item, "ExpressionEngine", ()) or ():
        if key.lstrip(".") in keys and expression not in (None, ""):
            return True
    return False


def apply_clear_expression(doc: ClearExpressionDocument, request: ClearExpressionRequest) -> ClearExpressionReceipt:
    """Clear an expression without recomputing."""

    item = require_object(doc, request.object_name, missing_code="OBJECT_NOT_FOUND", error=ClearExpressionError)
    if not _has_property(item, request.prop_path):
        raise ClearExpressionError(
            "OBJECT_NOT_FOUND",
            f"Property not found: {request.prop_path!r}",
        )
    clearer = getattr(item, "clearExpression", None)
    setter = getattr(item, "setExpression", None)
    try:
        if callable(clearer):
            clearer(request.prop_path)
        elif callable(setter):
            setter(request.prop_path, None)
        else:
            raise ClearExpressionError("INVALID_OBJECT", "object cannot clear expressions")
    except ClearExpressionError:
        raise
    except Exception as exc:
        raise ClearExpressionError("EXPRESSION_ERROR", str(exc) or type(exc).__name__) from exc
    return ClearExpressionReceipt(
        name=object_name(item) or request.object_name,
        item=item,
        prop_path=request.prop_path,
        skipped=False,
    )


def read_clear_expression_result(doc: ClearExpressionReadDocument, receipt: ClearExpressionReceipt) -> ClearExpressionInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        raise ClearExpressionError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if receipt.item is not None and located is not receipt.item:
        raise ClearExpressionError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")
    if _expression_remaining(located, receipt.prop_path):
        raise ClearExpressionError(
            "EXPRESSION_ERROR",
            f"Expression was not cleared on {receipt.prop_path!r}",
        )
    return ClearExpressionInspection(
        name=ClearExpressionName(receipt.name),
        label=object_label(located),
    )


def build_clear_expression_request(doc_name: object, object_name: object, prop_path: object) -> ClearExpressionRequest | ClearExpressionFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(ClearExpressionError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    object_name_value = nonempty_string(object_name, 'object_name')
    if object_name_value is None:
        return _failure(ClearExpressionError("INVALID_ARGUMENT", "object_name must be a nonempty string"))
    prop_path_value = nonempty_string(prop_path, 'prop_path')
    if prop_path_value is None:
        return _failure(ClearExpressionError("INVALID_ARGUMENT", "prop_path must be a nonempty string"))
    return ClearExpressionRequest(
        doc_name=DocumentName(doc_name_value),
        object_name=object_name_value,
        prop_path=prop_path_value,
    )


@dataclass(slots=True)
class _ConstraintRepairCollaborators:
    original: ClearExpressionCollaborators
    baseline: NativeErrorBaseline

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        postcondition: Callable[[object], object],
        *,
        structural: bool = True,
        recompute: bool = True,
    ) -> object:
        return self.original.commit_native_mutation(
            document_name, callback, postcondition, structural=structural, recompute=recompute,
        )

    def validate_document_invariants(self, document: ClearExpressionReadDocument) -> object:
        # Only the exact pre-apply native errors may await deferred recompute.
        with native_error_validation_scope(document, self.baseline, deferred=True):
            return self.original.validate_document_invariants(document)


@dataclass(slots=True)
class _ClearExpressionExecution:
    collaborators: ClearExpressionCollaborators
    request: ClearExpressionRequest
    created: ClearExpressionReceipt | None = None
    inspected: ClearExpressionInspection | None = None
    document: ClearExpressionDocument | None = None
    baseline: NativeErrorBaseline = field(default_factory=dict)
    retained: tuple[tuple[str, str], ...] | None = None
    constraint_repair: bool = False
    original_objects: tuple[object, ...] = ()

    def apply(self, doc: ClearExpressionDocument) -> None:
        self.document = doc
        self.original_objects = tuple(getattr(doc, "Objects", ()))
        self.baseline.clear()
        self.baseline.update(capture_native_error_baseline(doc))
        item = doc.getObject(self.request.object_name)
        self.retained = None
        if (getattr(item, "TypeId", "") == "Sketcher::SketchObject"
                and not hasattr(item, "Proxy")
                and self.request.prop_path.lstrip(".").startswith("Constraints")):
            before = tuple(getattr(item, "ExpressionEngine", ()) or ())
            self.created = apply_clear_expression(doc, self.request)
            after = tuple(getattr(item, "ExpressionEngine", ()) or ())
            if (len(after) == len(before) - 1 and after
                    and all(binding in before for binding in after)):
                self.retained = after
        else:
            self.created = apply_clear_expression(doc, self.request)

    def inspect(self, doc: ClearExpressionReadDocument) -> None:
        if self.created is None:
            raise ClearExpressionError(
                "INVALID_CLEAR_EXPRESSION_RESULT",
                "clear_expression did not return an identity receipt",
            )
        self.inspected = read_clear_expression_result(doc, self.created)
        if self.constraint_repair and self.retained is not None:
            if tuple(getattr(self.created.item, "ExpressionEngine", ()) or ()) != self.retained:
                raise ClearExpressionError("EXPRESSION_ERROR", "Retained constraint bindings changed")

    def retain_blocked_native_errors(self) -> None:
        if self.document is None:
            return
        # A previously healthy downstream Pad/Body may now report that the
        # unchanged, already-failed sketch did not commit. Admit only that exact
        # native dependency diagnostic on objects present before apply.
        current = capture_native_error_baseline(self.document)
        original_ids = {id(obj) for obj in self.original_objects}
        with native_error_validation_scope(self.document, self.baseline, deferred=True):
            known = {key for key, (obj, _, _) in self.baseline.items()
                     if existing_native_error_unchanged(self.document, obj)}
            pending = {key: value for key, value in current.items()
                       if key in original_ids and key not in self.baseline}
            while pending:
                admitted = []
                for key, (obj, detail, state) in pending.items():
                    if any(id(source) in known
                           and detail == "dependency did not commit: " + str(getattr(source, "Name", ""))
                           for source in getattr(obj, "OutList", ())):
                        self.baseline[key] = (obj, detail, state)
                        known.add(key)
                        admitted.append(key)
                if not admitted:
                    break
                for key in admitted:
                    del pending[key]

    def _missing_constraint_source(self, result: ClearExpressionFailure | ClearExpressionUncertain) -> bool:
        if self.retained is None or self.created is None or result.get("native_status") != "RecomputeFailed":
            return False
        baseline = self.baseline.get(id(self.created.item))
        if baseline is None:
            return False
        detail = baseline[1]
        return ("Document '" in detail and "not found" in detail
                and ".Constraints'" in detail
                and detail in result.get("error", ""))

    def run(self, *, recompute: bool = True) -> NativeOutcome[ClearExpressionResult]:
        collaborators = (_ConstraintRepairCollaborators(self.collaborators, self.baseline)
                         if self.constraint_repair else self.collaborators)
        result = run_clear_expression_native_mutation(
            collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
            recompute=recompute,
        )
        def _finish_native_commit(
            result: Literal[True] | ClearExpressionFailure | ClearExpressionUncertain,
        ) -> ClearExpressionResult:
            if result is not True:
                if (
                    recompute
                    and result.get("committed") is False
                    and result.get("rollback_succeeded") is True
                    and result.get("rollback_failed") is not True
                    and ("generic recompute has an unresolved cross-document dependency" in result.get("error", "")
                         or self._missing_constraint_source(result))
                ):
                    # The coordinator cannot isolate the retained external
                    # dependencies. Only confirmed rollback permits reapply.
                    self.constraint_repair = self._missing_constraint_source(result)
                    fallback = self.run(recompute=False)
                    return fallback if isinstance(fallback, dict) else fallback.await_result()
                return result
            if self.inspected is None:
                return make_clear_expression_uncertain(
                    "CLEAR_EXPRESSION_COMMITTED_RESPONSE_INVALID",
                    "Native commit completed without an inspected result",
                    committed=True,
                )
            success = make_clear_expression_success(object=self.inspected.name, prop_path=self.request.prop_path)
            if not recompute:
                try:
                    if self.document is None or self.created is None:
                        raise RuntimeError("Missing expression target after commit")
                    call_named(self.document, "recompute")
                    if self.constraint_repair:
                        self.retain_blocked_native_errors()
                        # Native failed recomputes retain Touch as a retry hint.
                        # Consume it only for the exact errors known before clear.
                        with native_error_validation_scope(self.document, self.baseline, deferred=True):
                            for obj, _, _ in self.baseline.values():
                                if existing_native_error_unchanged(self.document, obj):
                                    purge = getattr(obj, "purgeTouched", None)
                                    if callable(purge):
                                        purge()
                    with native_error_validation_scope(
                        self.document, self.baseline if self.constraint_repair else {},
                    ):
                        self.collaborators.validate_document_invariants(self.document)
                    self.inspect(self.document)
                except Exception as exc:
                    return make_clear_expression_uncertain(
                        "EXPRESSION_RECOMPUTE_FAILED",
                        f"Expression is cleared; direct recompute failed: {exc}",
                        committed=True,
                    )
            return success

        return settle_native_commit(result, _finish_native_commit)

def run_clear_expression(
    collaborators: ClearExpressionCollaborators,
    doc_name: object, object_name: object, prop_path: object,
) -> NativeOutcome[ClearExpressionResult]:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_clear_expression_request(doc_name, object_name, prop_path)
    if isinstance(request, dict):
        return request
    return _ClearExpressionExecution(collaborators, request).run()


class _ClearExpressionRpcFacade(Protocol):
    _cad_collaborators: ClearExpressionCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_clear_expression(
    self: _ClearExpressionRpcFacade, doc_name: str, object_name: str, prop_path: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_clear_expression(collaborators, doc_name, object_name, prop_path)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("clear_expression", rpc_clear_expression)


__all__ = [
    "ClearExpressionCollaborators",
    "ClearExpressionError",
    "ClearExpressionInspection",
    "ClearExpressionReceipt",
    "apply_clear_expression",
    "build_clear_expression_request",
    "read_clear_expression_result",
    "rpc_clear_expression",
    "run_clear_expression",
    "TYPED_RPC_HANDLER",
]
