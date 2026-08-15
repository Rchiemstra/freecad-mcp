"""CAD RPC execute_code handler (Phase 4 slice 4F)."""

from contextlib import suppress
from typing import Any

from ...gui_dispatch import _flush_gui_events
from .cad_mutation import (
    admit_cad_mutation,
    current_cad_mutation_inflight,
    native_mutation_rejection,
    native_rollback_exception_result,
    postflight_cad_mutation,
)
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
from .mutation_readiness import document_readiness, mark_quarantined


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


def _run_gui_execute_with_native_attribution(  # noqa: C901
    collaborators,
    run_gui_task,
    primary_document,
    *,
    native_recompute: bool,
    postcondition_sink: dict[str, Any],
):
    if not isinstance(primary_document, str) or not primary_document:
        return run_gui_task()
    document = None
    get_document = getattr(collaborators.freecad, "getDocument", None)
    if callable(get_document):
        try:
            document = get_document(primary_document)
        except Exception:
            # Preserve the native boundary's historical stale/missing-document
            # result instead of inventing a second lookup error contract here.
            document = None
    if document is not None:
        admission_failure = admit_cad_mutation(
            document,
            inflight=current_cad_mutation_inflight(),
        )
        if admission_failure is not None:
            return {
                **admission_failure,
                "traceback": None,
                "session": {},
                "stdout": "",
            }
    captured = {}

    def native_callback():
        captured["result"] = run_gui_task()
        if (
            isinstance(captured["result"], dict)
            and captured["result"].get("ok") is False
        ):
            raise _GuiExecuteRollback
        return captured["result"]

    def native_postcondition():
        captured["postcondition_called"] = True
        finalize = postcondition_sink.get("finalize")
        if callable(finalize):
            captured["result"] = finalize()
        return not (
            isinstance(captured.get("result"), dict)
            and captured["result"].get("ok") is False
        )

    try:
        # GUI execute_code can create/remove objects or trigger Assembly
        # structural side effects; always request the structural grant.
        if native_recompute:
            native_result = collaborators.commit_compatibility_mutation(
                primary_document,
                native_callback,
                structural=True,
                postcondition=native_postcondition,
            )
        else:
            native_result = collaborators.commit_compatibility_mutation(
                primary_document,
                native_callback,
                structural=True,
                recompute=False,
            )
    except _GuiExecuteRollback:
        if document is None:
            return captured["result"]
        return postflight_cad_mutation(
            document,
            captured["result"],
            include_failure_readiness=True,
        )
    except Exception as exc:
        if document is not None:
            rollback_failure = native_rollback_exception_result(document, exc)
            if rollback_failure is not None:
                return {
                    **rollback_failure,
                    "traceback": None,
                    "session": {},
                    "stdout": "",
                }
        raise
    native_status = (
        native_result.get("status") if isinstance(native_result, dict) else None
    )
    native_committed = (
        native_result.get("committed") if isinstance(native_result, dict) else False
    )
    if native_status == "Committed" and native_committed is True:
        if native_recompute and not captured.get("postcondition_called"):
            diagnostic = (
                "native compatibility mutation committed execute_code without "
                "its requested postcondition"
            )
            if document is not None:
                mark_quarantined(document, diagnostic)
            return {
                "ok": False,
                "success": False,
                "is_error": True,
                "error_code": "NATIVE_POSTCONDITION_NOT_RUN",
                "error": diagnostic,
                "mutation_readiness": (
                    [document_readiness(document)] if document is not None else []
                ),
                "retryable": False,
                "traceback": None,
                "session": {},
                "stdout": "",
            }
        result = captured["result"]
        if document is not None:
            result = postflight_cad_mutation(document, result)
        if isinstance(result, dict) and result.get("ok") is True:
            with suppress(Exception):
                _flush_gui_events()
        return result
    if (
        native_status == "PostconditionFailed"
        and captured.get("postcondition_called")
        and isinstance(captured.get("result"), dict)
        and captured["result"].get("ok") is False
    ):
        # A signed generated continuation may perform read-only shape checks
        # after the native recompute. Preserve its precise failure after the
        # coordinator has rolled the apply transaction back.
        result = captured["result"]
        if document is not None:
            result = postflight_cad_mutation(
                document,
                result,
                include_failure_readiness=True,
            )
        return result
    return {
        **native_mutation_rejection(
            native_result,
            document,
            operation_label="execution",
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


def _native_recompute_policy(
    options: dict[str, Any], primary_document: str | None
) -> tuple[bool, dict[str, Any] | None]:
    mode = options.get("recompute", "none")
    if mode == "none":
        return False, None
    if mode == "target" and primary_document:
        declared = options.get("recompute_documents")
        documents = list(declared) if declared else [primary_document]
        if documents and all(name == primary_document for name in documents):
            return True, None
    return False, {
        "success": False,
        "is_error": True,
        "error_code": "UNSUPPORTED_NATIVE_RECOMPUTE_SCOPE",
        "error": (
            "Live mutating execute_code can recompute only its one attributed "
            "document through the native coordinator; use a typed tool or split "
            "the operation"
        ),
        "retryable": False,
    }


def _prepare_native_gui_execution(options, collaborators):
    primary_document = _resolve_primary_document(collaborators, options)
    if primary_document and options.get("document") != primary_document:
        # Stamp so session and native recompute attribution resolve the same
        # document; omission no longer means "no document".
        options = {**options, "document": primary_document}
    native_recompute, failure = _native_recompute_policy(options, primary_document)
    return options, primary_document, native_recompute, failure


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

    postcondition_sink: dict[str, Any] = {}

    def run_gui_task():
        return run_execute_code_gui_task(
            code,
            options,
            freecad=collaborators.freecad,
            collect_invalid_objects_fn=self._collect_invalid_objects,
            native_boundary=bool(primary_document),
            postcondition_sink=postcondition_sink if native_recompute else None,
        )

    options, primary_document, native_recompute, recompute_failure = (
        _prepare_native_gui_execution(options, collaborators)
    )
    if recompute_failure is not None:
        return annotate(recompute_failure)

    def execute_code_gui_task():
        return _run_gui_execute_with_native_attribution(
            collaborators,
            run_gui_task,
            primary_document,
            native_recompute=native_recompute,
            postcondition_sink=postcondition_sink,
        )

    res = self._dispatch_gui(execute_code_gui_task, collaborators.execute_timeout)
    if isinstance(res, str):
        return annotate({"success": False, "error": res, "is_error": True})
    return finalize_gui_execute_response(annotate, res, options)
