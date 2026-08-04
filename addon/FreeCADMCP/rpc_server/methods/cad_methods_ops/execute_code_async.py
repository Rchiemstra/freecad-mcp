"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

import threading
from typing import Any

import FreeCADGui

from ...telemetry import emit as emit_telemetry


def execute_code_async(self, code: str) -> dict[str, Any]:
    """Start code execution in a background thread and return immediately.

    Use for long-running OCCT operations (fuse/cut/loft) that would otherwise
    exceed the MCP timeout. The caller should poll a document object for
    completion status (e.g. check SessionState.Label via get_object).
    """

    collaborators = self._execution_collaborators
    freecad = collaborators.freecad
    analysis = collaborators.analyze_execute_code(
        code, {"execution_mode": "async"}
    )
    emit_telemetry(
        "execute_code",
        "policy_rejected",
        status="warning",
        error_code="DEPRECATED_EXECUTE_CODE_ASYNC",
        payload={
            "execution_category": "deprecated_execute_code_async",
            "analysis": analysis,
            "deprecation": (
                "Use worker jobs or request-aware MCP tasks for long work"
            ),
        },
    )

    def _set_status(msg):
        self._dispatch_gui(
            lambda: FreeCADGui.getMainWindow().statusBar().showMessage(msg)
        )

    def _clear_status():
        self._dispatch_gui(
            lambda: FreeCADGui.getMainWindow().statusBar().clearMessage()
        )

    def worker() -> None:
        # NOTE: we do NOT redirect sys.stdout here. contextlib.redirect_stdout
        # swaps stdout process-wide, not per-thread, so it would race with the
        # GUI thread and other concurrent work. Background code should report
        # via FreeCAD.Console (which is thread-safe) instead.
        try:
            execution_globals = globals()
            execution_globals["FreeCAD"] = freecad
            exec(code, execution_globals)
            freecad.Console.PrintMessage("Async code execution completed.\n")
        except Exception as e:
            import traceback as _tb

            freecad.Console.PrintError(f"Async code error: {e}\n{_tb.format_exc()}")
        finally:
            _clear_status()

    _set_status("MCP: running background task…")
    threading.Thread(target=worker, daemon=True).start()
    return {
        "success": True,
        "message": "Code execution started in background.",
        "warnings": [
            {
                "code": "DEPRECATED_EXECUTE_CODE_ASYNC",
                "message": (
                    "Use worker jobs or request-aware MCP tasks; compatibility "
                    "is retained only in off/observe mode."
                ),
            }
        ],
        "execution_category": "deprecated_execute_code_async",
        "code_analysis": analysis,
    }
