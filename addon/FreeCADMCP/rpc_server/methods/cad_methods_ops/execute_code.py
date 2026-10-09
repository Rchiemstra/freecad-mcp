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
from .execute_code_gui_hooks import restore_active_document
from .execute_code_gui_task import run_execute_code_gui_task
from .execute_code_policy import (
    boolean_audit_block_response,
    geometry_loop_block_response,
    gui_timeout_not_supported_response,
    invalid_execution_mode_response,
    modal_command_block_response,
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

    def native_exception_result(exc):
        if isinstance(exc, _GuiExecuteRollback):
            # The body already ran inside the commit. Raising rolls that
            # transaction back, so the caller must see committed false and
            # the body's error, not a successful commit.
            result = captured["result"]
            if document is not None:
                result = postflight_cad_mutation(
                    document,
                    result,
                    include_failure_readiness=True,
                )
            if isinstance(result, dict):
                result = dict(result)
                # Match other rolled-back rejections so the JSON-RPC client
                # returns this failure instead of an unstructured remote error.
                result["committed"] = False
                result["outcome"] = "rejected"
                # Arbitrary code may have acted outside the document.
                result["retry_safe"] = False
            return result
        if document is not None:
            rollback_failure = native_rollback_exception_result(document, exc)
            if rollback_failure is not None:
                return {
                    **rollback_failure,
                    "traceback": None,
                    "session": {},
                    "stdout": "",
                }
        raise exc

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
    except Exception as exc:
        return native_exception_result(exc)

    def finish_native_result(resolved):
        native_status = (
            resolved.get("status") if isinstance(resolved, dict) else None
        )
        native_committed = (
            resolved.get("committed") if isinstance(resolved, dict) else False
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
            return result
        if (
            native_status == "PostconditionFailed"
            and captured.get("postcondition_called")
            and isinstance(captured.get("result"), dict)
            and captured["result"].get("ok") is False
        ):
            # Preserve the continuation's precise failure after native rollback.
            result = captured["result"]
            if document is not None:
                result = postflight_cad_mutation(
                    document, result, include_failure_readiness=True
                )
            return result
        return {
            **native_mutation_rejection(
                resolved, document, operation_label="execution"
            ),
            "traceback": None,
            "session": {},
            "stdout": "",
        }

    wait = getattr(native_result, "await_result", None)
    if callable(wait):
        class _PendingExecute:
            def await_result(self, timeout: float = 60.0):
                # dispatch_gui invokes this on the RPC thread. Never interpret
                # an async handle as a terminal rejection before its callback
                # has finished, and classify callback rollback here too.
                try:
                    resolved = wait(timeout)
                except TimeoutError:
                    # A pending native transaction is expected while the
                    # callback is still running, and is not rollback evidence.
                    raise
                except Exception as exc:
                    return native_exception_result(exc)
                return finish_native_result(resolved)

        return _PendingExecute()
    return finish_native_result(native_result)


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
    blocked = modal_command_block_response(
        annotate,
        code=code,
        find_modal_command_risk_fn=collaborators.find_modal_command_risk,
    )
    if blocked is not None:
        return blocked
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


def _single_document_mutation_scope_failure(options, primary_document):
    """Keep the public GUI path aligned with the one-document native commit."""

    affected = options.get("affected_documents") or ()
    if not isinstance(affected, (list, tuple, set)):
        affected = ()
    documents = {
        str(name)
        for name in (primary_document, *affected)
        if isinstance(name, str) and name
    }
    if len(documents) <= 1:
        return None
    return {
        "success": False,
        "is_error": True,
        "error_code": "UNSUPPORTED_MULTI_DOCUMENT_MUTATION_SCOPE",
        "error": (
            "Live mutating execute_code supports one document per mutation. "
            "Run dependency-ordered single-document operations instead."
        ),
        "documents": sorted(documents),
        "retryable": False,
    }


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

    options, primary_document, native_recompute, recompute_failure = (
        _prepare_native_gui_execution(options, collaborators)
    )
    if recompute_failure is not None:
        return annotate(recompute_failure)
    scope_failure = _single_document_mutation_scope_failure(options, primary_document)
    if scope_failure is not None:
        return annotate(scope_failure)

    postcondition_sink: dict[str, Any] = {}

    def run_gui_task(active_before):
        return run_execute_code_gui_task(
            code,
            options,
            freecad=collaborators.freecad,
            collect_invalid_objects_fn=self._collect_invalid_objects,
            native_boundary=bool(primary_document),
            postcondition_sink=postcondition_sink if native_recompute else None,
            active_document_before=active_before,
            manage_active_document=False,
        )

    def finish_gui_execution(active_before, result):
        # Document activation and GUI delivery must remain on the GUI thread,
        # after the owner-thread commit has completed or rolled back.
        restore_active_document(
            active_before,
            bool(options.get("restore_active_document", True)),
            freecad=collaborators.freecad,
        )
        if isinstance(result, dict) and result.get("ok") is True:
            with suppress(Exception):
                _flush_gui_events()
        if isinstance(result, dict) and isinstance(result.get("session"), dict):
            active_after = getattr(collaborators.freecad, "ActiveDocument", None)
            result["session"]["active_document_after"] = (
                getattr(active_after, "Name", None) if active_after else None
            )
        return result

    def execute_code_gui_task():
        active = getattr(collaborators.freecad, "ActiveDocument", None)
        active_before = getattr(active, "Name", None) if active else None
        result = None
        pending = False
        try:
            if primary_document and options.get("activate_document"):
                try:
                    target = collaborators.freecad.getDocument(primary_document)
                except NameError:  # getDocument raises for unknown names
                    target = None
                if target is not None:
                    try:
                        collaborators.freecad.setActiveDocument(primary_document)
                    except Exception as exc:
                        result = {
                            "ok": False,
                            "error": (
                                f"Failed to activate document {primary_document!r}: {exc}"
                            ),
                            "traceback": None,
                            "session": {},
                            "stdout": "",
                        }
            if result is None:
                result = _run_gui_execute_with_native_attribution(
                    collaborators,
                    lambda: run_gui_task(active_before),
                    primary_document,
                    native_recompute=native_recompute,
                    postcondition_sink=postcondition_sink,
                )
            wait = getattr(result, "await_result", None)
            if callable(wait):
                pending = True

                class _PendingGuiCompletion:
                    def await_result(pending_self, timeout: float = 60.0):
                        try:
                            resolved = wait(timeout)
                        except TimeoutError:
                            # The native callback may still be running; changing
                            # document activation now would violate its scope.
                            raise
                        except Exception:
                            self._dispatch_gui(
                                lambda: finish_gui_execution(active_before, None),
                                timeout,
                            )
                            raise
                        return self._dispatch_gui(
                            lambda: finish_gui_execution(active_before, resolved),
                            timeout,
                        )

                return _PendingGuiCompletion()
        finally:
            if not pending:
                result = finish_gui_execution(active_before, result)
        return result

    def finalize_late_result(value):
        if isinstance(value, str):
            return annotate({"success": False, "error": value, "is_error": True})
        return finalize_gui_execute_response(annotate, value, options)

    res = self._dispatch_gui(
        execute_code_gui_task,
        collaborators.execute_timeout,
        late_result_transform=finalize_late_result,
    )
    if isinstance(res, str):
        return annotate({"success": False, "error": res, "is_error": True})
    return finalize_gui_execute_response(annotate, res, options)
