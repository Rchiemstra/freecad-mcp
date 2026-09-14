"""Typed ``sweep_pipe`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.sweep_pipe_contract import (
    SweepPipeCollaborators,
    SweepPipeDocument,
    SweepPipeFailure,
    SweepPipeName,
    SweepPipeReadDocument,
    SweepPipeRequest,
    SweepPipeResult,
    DocumentName,
    make_sweep_pipe_failure,
    make_sweep_pipe_success,
    make_sweep_pipe_uncertain,
)
from .sweep_pipe_mutation import SweepPipeError, run_sweep_pipe_native_mutation
from .typed_rpc_support import (
    add_named_object,
    add_to_container,
    as_bool,
    as_float,
    as_int,
    assign_attr,
    call_named,
    invoke,
    nonempty_string,
    object_label,
    object_name,
    object_type_id,
    optional_string,
    parse_ref,
    remove_from_container,
    require_object,
    resolve_if_exists,
    snapshot_ring
)


@dataclass(frozen=True, slots=True)
class SweepPipeReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class SweepPipeInspection:
    """Read-only data captured after the native-owned recompute."""

    name: SweepPipeName
    label: str
    extra: object = None


def _failure(error: SweepPipeError, *, retry_safe: bool = True) -> SweepPipeFailure:
    return make_sweep_pipe_failure(error.code, str(error), retry_safe=retry_safe)


def apply_sweep_pipe(doc: SweepPipeDocument, request: SweepPipeRequest) -> SweepPipeReceipt:
    """Create a swept solid without recomputing."""

    skipped = resolve_if_exists(doc, request.solid_name, request.if_exists, error=SweepPipeError)
    if skipped is not None:
        return SweepPipeReceipt(name=object_name(skipped) or request.solid_name, item=skipped, skipped=True)
    require_object(doc, request.path_wire, missing_code="OBJECT_NOT_FOUND", error=SweepPipeError)
    created = add_named_object(doc, "Part::Feature", request.solid_name)
    if request.container:
        add_to_container(require_object(doc, request.container, missing_code="OBJECT_NOT_FOUND", error=SweepPipeError), created)
    return SweepPipeReceipt(name=object_name(created) or request.solid_name, item=created, skipped=False)


def read_sweep_pipe_result(doc: SweepPipeReadDocument, receipt: SweepPipeReceipt) -> SweepPipeInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise SweepPipeError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise SweepPipeError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return SweepPipeInspection(
        name=SweepPipeName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_sweep_pipe_request(doc_name: object, path_wire: object, diameter_mm: object, solid_name: object, profile_mode: object, color: object, container: object, if_exists: object) -> SweepPipeRequest | SweepPipeFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    path_wire_value = nonempty_string(path_wire, 'path_wire')
    if path_wire_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "path_wire must be a nonempty string"))
    diameter_mm_value = as_float(diameter_mm, None)
    if diameter_mm_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "diameter_mm must be a number"))
    solid_name_value = nonempty_string(solid_name, 'solid_name')
    if solid_name_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "solid_name must be a nonempty string"))
    profile_mode_value = nonempty_string(profile_mode, 'profile_mode')
    if profile_mode_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "profile_mode must be a nonempty string"))
    if container is None:
        container_value: str | None = None
    else:
        container_value = optional_string(container)
        if container_value is None:
            return _failure(SweepPipeError("INVALID_ARGUMENT", "container must be a nonempty string or None"))
    if_exists_value = nonempty_string(if_exists, 'if_exists')
    if if_exists_value is None:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "if_exists must be a nonempty string"))
    if if_exists not in {"error", "skip", "replace"}:
        return _failure(SweepPipeError("INVALID_ARGUMENT", "if_exists must be one of: error, skip, replace"))
    return SweepPipeRequest(
        doc_name=DocumentName(doc_name_value),
        path_wire=path_wire_value,
        diameter_mm=diameter_mm_value,
        solid_name=solid_name_value,
        profile_mode=profile_mode_value,
        color=color,
        container=container_value,
        if_exists=if_exists_value,
    )


@dataclass(slots=True)
class _SweepPipeExecution:
    collaborators: SweepPipeCollaborators
    request: SweepPipeRequest
    created: SweepPipeReceipt | None = None
    inspected: SweepPipeInspection | None = None

    def apply(self, doc: SweepPipeDocument) -> None:
        self.created = apply_sweep_pipe(doc, self.request)

    def inspect(self, doc: SweepPipeReadDocument) -> None:
        if self.created is None:
            raise SweepPipeError(
                "INVALID_SWEEP_PIPE_RESULT",
                "sweep_pipe did not return an identity receipt",
            )
        self.inspected = read_sweep_pipe_result(doc, self.created)

    def run(self) -> SweepPipeResult:
        result = run_sweep_pipe_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_sweep_pipe_uncertain(
                "SWEEP_PIPE_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_sweep_pipe_success(solid_name=self.inspected.name)


def run_sweep_pipe(
    collaborators: SweepPipeCollaborators,
    doc_name: object, path_wire: object, diameter_mm: object, solid_name: object, profile_mode: object, color: object, container: object, if_exists: object,
) -> SweepPipeResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_sweep_pipe_request(doc_name, path_wire, diameter_mm, solid_name, profile_mode, color, container, if_exists)
    if isinstance(request, dict):
        return request
    return _SweepPipeExecution(collaborators, request).run()


class _SweepPipeRpcFacade(Protocol):
    _cad_collaborators: SweepPipeCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_sweep_pipe(
    self: _SweepPipeRpcFacade, doc_name: str, path_wire: str, diameter_mm: float, solid_name: str, profile_mode: str = "frenet", color: object = None, container: str | None = None, if_exists: str = "error",
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_sweep_pipe(collaborators, doc_name, path_wire, diameter_mm, solid_name, profile_mode, color, container, if_exists)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("sweep_pipe", rpc_sweep_pipe)


__all__ = [
    "SweepPipeCollaborators",
    "SweepPipeError",
    "SweepPipeInspection",
    "SweepPipeReceipt",
    "apply_sweep_pipe",
    "build_sweep_pipe_request",
    "read_sweep_pipe_result",
    "rpc_sweep_pipe",
    "run_sweep_pipe",
    "TYPED_RPC_HANDLER",
]
