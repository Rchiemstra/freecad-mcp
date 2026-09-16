"""Typed ``recompute_and_wait`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.recompute_and_wait_contract import (
    RecomputeAndWaitCollaborators,
    RecomputeAndWaitFailure,
    RecomputeAndWaitRequest,
    RecomputeAndWaitResult,
    DocumentName,
    make_recompute_and_wait_failure,
    make_recompute_and_wait_success,
    make_recompute_and_wait_uncertain,
)
from .recompute_and_wait_mutation import RecomputeAndWaitError, run_recompute_and_wait_native_mutation
from .typed_rpc_document import document_name


@dataclass(frozen=True, slots=True)
class RecomputeAndWaitReceipt:
    """Internal identity captured while applying the mutation."""

    name: str


@dataclass(frozen=True, slots=True)
class RecomputeAndWaitInspection:
    """Read-only data captured after the native-owned recompute."""

    name: DocumentName
    settled: bool


def _failure(error: RecomputeAndWaitError, *, retry_safe: bool = True) -> RecomputeAndWaitFailure:
    return make_recompute_and_wait_failure(
        error.code, str(error), retry_safe=retry_safe, diagnostics=error.diagnostics
    )


def apply_recompute_and_wait(doc: object, request: RecomputeAndWaitRequest) -> RecomputeAndWaitReceipt:
    """Apply recompute_and_wait without recomputing or managing a transaction."""

    return RecomputeAndWaitReceipt(name=document_name(doc))


def read_recompute_and_wait_result(doc: object, receipt: RecomputeAndWaitReceipt) -> RecomputeAndWaitInspection:
    """Build the public result after the shared mutation recompute."""

    if document_name(doc) != receipt.name:
        raise RecomputeAndWaitError(
            "DOCUMENT_IDENTITY_MISMATCH",
            "Inspected document name does not match the apply receipt",
        )
    return RecomputeAndWaitInspection(
        name=DocumentName(receipt.name),
        settled=True,
    )


def build_recompute_and_wait_request(doc_name: object) -> RecomputeAndWaitRequest | RecomputeAndWaitFailure:
    """Validate the untyped JSON arguments before constructing internal types."""

    if not isinstance(doc_name, str) or not doc_name.strip():
        return _failure(RecomputeAndWaitError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    return RecomputeAndWaitRequest(doc_name=DocumentName(doc_name))


@dataclass(slots=True)
class _RecomputeAndWaitExecution:
    collaborators: RecomputeAndWaitCollaborators
    request: RecomputeAndWaitRequest
    created: RecomputeAndWaitReceipt | None = None
    inspected: RecomputeAndWaitInspection | None = None

    def apply(self, doc: object) -> None:
        self.created = apply_recompute_and_wait(doc, self.request)

    def inspect(self, doc: object) -> None:
        if self.created is None:
            raise RecomputeAndWaitError(
                "INVALID_RECOMPUTE_AND_WAIT_RESULT",
                "recompute_and_wait did not return an identity receipt",
            )
        self.inspected = read_recompute_and_wait_result(doc, self.created)

    def run(self) -> RecomputeAndWaitResult:
        result = run_recompute_and_wait_native_mutation(
            self.collaborators,
            str(getattr(self.request, "doc_name", getattr(self.request, "name", ""))),
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_recompute_and_wait_uncertain(
                "RECOMPUTE_AND_WAIT_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected recompute_and_wait result",
                committed=True,
            )
        return make_recompute_and_wait_success(self.inspected.name, self.inspected.settled)


def run_recompute_and_wait(
    collaborators: RecomputeAndWaitCollaborators,
    doc_name: object,
) -> RecomputeAndWaitResult:
    """Run recompute_and_wait through apply, recompute, inspection, and commit."""

    request = build_recompute_and_wait_request(doc_name)
    if isinstance(request, dict):
        return request
    return _RecomputeAndWaitExecution(collaborators, request).run()


class _RecomputeAndWaitRpcFacade(Protocol):
    _cad_collaborators: RecomputeAndWaitCollaborators

    def _dispatch_gui(self, callback: Callable[[], object]) -> object: ...


def rpc_recompute_and_wait(
    self: _RecomputeAndWaitRpcFacade,
    doc_name: str,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_recompute_and_wait(collaborators, doc_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("recompute_and_wait", rpc_recompute_and_wait)


__all__ = [
    "RecomputeAndWaitCollaborators",
    "RecomputeAndWaitError",
    "RecomputeAndWaitInspection",
    "RecomputeAndWaitReceipt",
    "apply_recompute_and_wait",
    "build_recompute_and_wait_request",
    "read_recompute_and_wait_result",
    "rpc_recompute_and_wait",
    "run_recompute_and_wait",
    "TYPED_RPC_HANDLER",
]
