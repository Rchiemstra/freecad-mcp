"""Typed ``run_fem_analysis`` mutation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ...._shared.protocol.run_fem_analysis_contract import (
    RunFemAnalysisCollaborators,
    RunFemAnalysisDocument,
    RunFemAnalysisFailure,
    RunFemAnalysisName,
    RunFemAnalysisReadDocument,
    RunFemAnalysisRequest,
    RunFemAnalysisResult,
    DocumentName,
    make_run_fem_analysis_failure,
    make_run_fem_analysis_success,
    make_run_fem_analysis_uncertain,
)
from .run_fem_analysis_mutation import RunFemAnalysisError, run_run_fem_analysis_native_mutation
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
class RunFemAnalysisReceipt:
    """Internal identity captured while applying the mutation."""

    name: str
    item: object | None
    skipped: bool = False
    extra: object = None


@dataclass(frozen=True, slots=True)
class RunFemAnalysisInspection:
    """Read-only data captured after the native-owned recompute."""

    name: RunFemAnalysisName
    label: str
    extra: object = None


def _failure(error: RunFemAnalysisError, *, retry_safe: bool = True) -> RunFemAnalysisFailure:
    return make_run_fem_analysis_failure(error.code, str(error), retry_safe=retry_safe)


def _is_gmsh_mesh(item: object) -> bool:
    """True for Gmsh mesh objects, including Fem Python wrappers.

    ``ObjectsFem.makeMeshGmsh`` creates ``Fem::FemMeshShapeBaseObjectPython``
    with ``Proxy.Type == "Fem::FemMeshGmsh"``. TypeId itself is not that string.
    """

    proxy = getattr(item, "Proxy", None)
    proxy_type = getattr(proxy, "Type", None) if proxy is not None else None
    if proxy_type == "Fem::FemMeshGmsh":
        return True
    type_id = str(getattr(item, "TypeId", ""))
    if "Fem::FemMeshGmsh" in type_id or type_id.endswith("FemMeshGmsh"):
        return True
    try:
        from femtools.femutils import is_derived_from  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        return bool(is_derived_from(item, "Fem::FemMeshGmsh"))
    except Exception:
        return False


def _analysis_members(analysis: object) -> tuple[object, ...]:
    group = getattr(analysis, "Group", None)
    if isinstance(group, (list, tuple)):
        return tuple(group)
    if group is None:
        return ()
    try:
        return tuple(group)
    except TypeError:
        return ()


def _ensure_fem_mesh(doc: object, analysis: object) -> None:
    members = list(_analysis_members(analysis))
    document_objects = getattr(doc, "Objects", ()) or ()
    for item in document_objects:
        parent = getattr(item, "getParentGroup", None)
        if callable(parent):
            try:
                if parent() is analysis:
                    members.append(item)
            except Exception:
                pass
    mesh = next((item for item in members if _is_gmsh_mesh(item)), None)
    if mesh is None:
        raise RunFemAnalysisError("GMSH_UNAVAILABLE", "analysis has no Gmsh mesh object")
    try:
        from femmesh.gmshtools import GmshTools  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RunFemAnalysisError("GMSH_UNAVAILABLE", "Gmsh tools are unavailable") from exc
    try:
        GmshTools(mesh).create_mesh()
    except Exception as exc:
        raise RunFemAnalysisError("GMSH_FAILED", str(exc) or type(exc).__name__) from exc


def apply_run_fem_analysis(doc: RunFemAnalysisDocument, request: RunFemAnalysisRequest) -> RunFemAnalysisReceipt:
    """Record the analysis object; the solver collaborator runs after identity checks."""

    analysis = require_object(doc, request.analysis_name, missing_code="OBJECT_NOT_FOUND", error=RunFemAnalysisError)
    return RunFemAnalysisReceipt(name=object_name(analysis) or request.analysis_name, item=analysis, skipped=False)


def read_run_fem_analysis_result(doc: RunFemAnalysisReadDocument, receipt: RunFemAnalysisReceipt) -> RunFemAnalysisInspection:
    """Build the public result after the shared mutation recompute."""

    located: object | None = doc.getObject(receipt.name)
    if located is None:
        located = receipt.item
    if located is None:
        raise RunFemAnalysisError("CREATED_OBJECT_MISSING", f"Target is missing: {receipt.name!r}")
    if (
        receipt.item is not None
        and located is not receipt.item
        and object_name(located) != receipt.name
    ):
        raise RunFemAnalysisError("CREATED_OBJECT_REPLACED", f"Target was replaced before commit: {receipt.name!r}")

    extra = receipt.extra

    return RunFemAnalysisInspection(
        name=RunFemAnalysisName(receipt.name),
        label=object_label(located),
        extra=extra,
    )


def build_run_fem_analysis_request(doc_name: object, analysis_name: object, timeout: object) -> RunFemAnalysisRequest | RunFemAnalysisFailure:
    doc_name_value = nonempty_string(doc_name, 'doc_name')
    if doc_name_value is None:
        return _failure(RunFemAnalysisError("INVALID_ARGUMENT", "doc_name must be a nonempty string"))
    analysis_name_value = nonempty_string(analysis_name, 'analysis_name')
    if analysis_name_value is None:
        return _failure(RunFemAnalysisError("INVALID_ARGUMENT", "analysis_name must be a nonempty string"))
    timeout_value = as_int(timeout, 600)
    if timeout_value is None:
        return _failure(RunFemAnalysisError("INVALID_ARGUMENT", "timeout must be an int"))
    return RunFemAnalysisRequest(
        doc_name=DocumentName(doc_name_value),
        analysis_name=analysis_name_value,
        timeout=timeout_value,
    )


@dataclass(slots=True)
class _RunFemAnalysisExecution:
    collaborators: RunFemAnalysisCollaborators
    request: RunFemAnalysisRequest
    created: RunFemAnalysisReceipt | None = None
    inspected: RunFemAnalysisInspection | None = None

    def apply(self, doc: RunFemAnalysisDocument) -> None:
        self.created = apply_run_fem_analysis(doc, self.request)
        analysis = require_object(
            doc,
            self.request.analysis_name,
            missing_code="OBJECT_NOT_FOUND",
            error=RunFemAnalysisError,
        )
        _ensure_fem_mesh(doc, analysis)
        runner = getattr(self.collaborators, "run_fem_analysis", None)
        if runner is None:
            raise RunFemAnalysisError("FEM_ANALYSIS_UNAVAILABLE", "run_fem_analysis collaborator is missing")
        executor_result = invoke(runner, str(self.request.doc_name), self.request.analysis_name)
        if not isinstance(executor_result, dict) or executor_result.get("success") is not True:
            code = "FEM_EXECUTION_FAILED"
            if isinstance(executor_result, dict):
                executor_code = executor_result.get("error_code")
                if isinstance(executor_code, str) and executor_code.strip():
                    code = executor_code.strip()
                message = executor_result.get("error")
                if not isinstance(message, str) or not message.strip():
                    message = "FEM analysis execution failed"
            else:
                message = "FEM analysis executor returned an invalid result"
            raise RunFemAnalysisError(code, message)

    def inspect(self, doc: RunFemAnalysisReadDocument) -> None:
        if self.created is None:
            raise RunFemAnalysisError(
                "INVALID_RUN_FEM_ANALYSIS_RESULT",
                "run_fem_analysis did not return an identity receipt",
            )
        self.inspected = read_run_fem_analysis_result(doc, self.created)

    def run(self) -> RunFemAnalysisResult:
        result = run_run_fem_analysis_native_mutation(
            self.collaborators,
            self.request.doc_name,
            self.apply,
            self.inspect,
        )
        if result is not True:
            return result
        if self.inspected is None:
            return make_run_fem_analysis_uncertain(
                "RUN_FEM_ANALYSIS_COMMITTED_RESPONSE_INVALID",
                "Native commit completed without an inspected result",
                committed=True,
            )
        return make_run_fem_analysis_success(analysis_name=self.inspected.name)


def run_run_fem_analysis(
    collaborators: RunFemAnalysisCollaborators,
    doc_name: object, analysis_name: object, timeout: object,
) -> RunFemAnalysisResult:
    """Run the mutation through apply, recompute, inspection, and commit."""

    request = build_run_fem_analysis_request(doc_name, analysis_name, timeout)
    if isinstance(request, dict):
        return request
    return _RunFemAnalysisExecution(collaborators, request).run()


class _RunFemAnalysisRpcFacade(Protocol):
    _cad_collaborators: RunFemAnalysisCollaborators

    def _dispatch_gui(self, callback: Callable[[], object], timeout: int | None = None) -> object: ...


def rpc_run_fem_analysis(
    self: _RunFemAnalysisRpcFacade, doc_name: str, analysis_name: str, timeout: int = 600,
) -> dict[str, object]:
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: run_run_fem_analysis(collaborators, doc_name, analysis_name, timeout)
    , timeout=timeout)
    return res if isinstance(res, dict) else {"success": False, "error": res}


TYPED_RPC_HANDLER = ("run_fem_analysis", rpc_run_fem_analysis)


__all__ = [
    "RunFemAnalysisCollaborators",
    "RunFemAnalysisError",
    "RunFemAnalysisInspection",
    "RunFemAnalysisReceipt",
    "apply_run_fem_analysis",
    "build_run_fem_analysis_request",
    "read_run_fem_analysis_result",
    "rpc_run_fem_analysis",
    "run_run_fem_analysis",
    "TYPED_RPC_HANDLER",
]
