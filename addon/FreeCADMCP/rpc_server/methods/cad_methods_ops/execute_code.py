"""CAD RPC execute_code handler (Phase 4 slice 4F)."""

from typing import Any

from .execute_code_context import build_execute_code_context
from .execute_code_gui_task import run_execute_code_gui_task
from .execute_code_policy import (
    boolean_audit_block_response,
    geometry_loop_block_response,
    gui_timeout_not_supported_response,
    invalid_execution_mode_response,
    worker_requires_read_only_response,
)
from .execute_code_response import finalize_gui_execute_response


class _GuiExecuteRollback(RuntimeError):
    """Abort the native transaction while retaining its public error envelope."""


def _resolve_primary_document(collaborators, options: dict[str, Any]) -> str | None:
    """Prefer explicit options['document']; else ActiveDocument (fail closed)."""

    declared = options.get("document")
    if isinstance(declared, str) and declared:
        return declared
    active = getattr(collaborators.freecad, "ActiveDocument", None)
    name = getattr(active, "Name", None)
    if isinstance(name, str) and name:
        return name
    return None


def _recompute_primary_document(collaborators, primary_document: str) -> None:
    """Recompute under the active structural grant before apply returns.

    DocumentCommitCoordinator opens the structural grant only around
    operation.apply(); its own post-apply recompute runs after the grant
    ends. Matching typed CAD mutations, force one recompute inside the
    callback so Assembly/joint side effects see the grant.
    """

    get_document = getattr(collaborators.freecad, "getDocument", None)
    if not callable(get_document):
        return
    try:
        document = get_document(primary_document)
    except Exception:
        return
    if document is None:
        return
    recompute = getattr(document, "recompute", None)
    if callable(recompute):
        recompute()


def _run_gui_execute_with_native_attribution(
    collaborators,
    run_gui_task,
    primary_document,
):
    if not isinstance(primary_document, str) or not primary_document:
        return run_gui_task()
    captured = {}

    def native_callback():
        captured["result"] = run_gui_task()
        if (
            isinstance(captured["result"], dict)
            and captured["result"].get("ok") is False
        ):
            raise _GuiExecuteRollback
        _recompute_primary_document(collaborators, primary_document)
        return captured["result"]

    try:
        # GUI execute_code can create/remove objects or trigger Assembly
        # structural side effects; always request the structural grant.
        native_result = collaborators.commit_compatibility_mutation(
            primary_document, native_callback, structural=True
        )
    except _GuiExecuteRollback:
        return captured["result"]
    native_status = (
        native_result.get("status") if isinstance(native_result, dict) else None
    )
    native_committed = (
        native_result.get("committed") if isinstance(native_result, dict) else False
    )
    if native_status == "Committed" and native_committed is True:
        return captured["result"]
    return {
        "ok": False,
        "error": (
            "Native compatibility mutation rejected execution"
            + (f" ({native_status})" if native_status else "")
        ),
        "traceback": None,
        "session": {},
        "stdout": "",
    }


def _gui_execute_policy_block(
    collaborators,
    annotate,
    code,
    options,
    execution_mode,
    read_only,
):
    if options.get("timeout_seconds") is not None:
        return gui_timeout_not_supported_response(annotate)
    blocked = geometry_loop_block_response(
        annotate,
        code=code,
        execution_mode=execution_mode,
        read_only=read_only,
        allow_gui_loop=bool(options.get("allow_gui_geometry_loop", False)),
        find_gui_geometry_loop_risk_fn=(
            collaborators.find_gui_geometry_loop_risk
        ),
    )
    if blocked is not None:
        return blocked
    return boolean_audit_block_response(
        annotate,
        code=code,
        read_only=read_only,
        find_gui_blocking_risk_fn=collaborators.find_gui_blocking_risk,
    )


def execute_code(
    self, code: str, options: dict[str, Any] | None = None
) -> dict[str, Any]:
    options = options or {}
    collaborators = self._execution_collaborators
    _category, _analysis, annotate = build_execute_code_context(
        code,
        options,
        analyze_execute_code_fn=collaborators.analyze_execute_code,
        typed_tool_warning_fn=collaborators.typed_tool_warning,
    )

    if not self.allow_execute_code:
        return annotate(
            {
                "success": False,
                "is_error": True,
                "error_code": "remote_execute_code_disabled",
                "error": "Arbitrary execute_code is disabled while remote RPC is enabled",
            }
        )

    execution_mode = options.get("execution_mode", "auto")
    if execution_mode not in ("gui", "worker", "auto"):
        return invalid_execution_mode_response(annotate, execution_mode)

    read_only_requested = bool(options.get("read_only", False))
    if execution_mode == "worker" or read_only_requested:
        if not read_only_requested:
            return worker_requires_read_only_response(annotate)
        return annotate(self._execute_code_worker(code, options))

    blocked = _gui_execute_policy_block(
        collaborators,
        annotate,
        code=code,
        options=options,
        execution_mode=execution_mode,
        read_only=read_only_requested,
    )
    if blocked is not None:
        return blocked

    def run_gui_task():
        return run_execute_code_gui_task(
            code,
            options,
            freecad=collaborators.freecad,
            collect_invalid_objects_fn=self._collect_invalid_objects,
        )

    primary_document = _resolve_primary_document(collaborators, options)
    if primary_document and options.get("document") != primary_document:
        # Stamp so session / optional target recompute see the same document
        # the native boundary attributes — omit no longer means "no document".
        options = {**options, "document": primary_document}

    def execute_code_gui_task():
        return _run_gui_execute_with_native_attribution(
            collaborators,
            run_gui_task,
            primary_document,
        )

    res = self._dispatch_gui(execute_code_gui_task, collaborators.execute_timeout)
    if isinstance(res, str):
        return annotate({"success": False, "error": res, "is_error": True})
    return finalize_gui_execute_response(annotate, res, options)
