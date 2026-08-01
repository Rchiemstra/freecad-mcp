"""CAD RPC execute_code handler (Phase 4 slice 4F)."""

from typing import Any

from ._common import _rpc_mod
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


def execute_code(
    self, code: str, options: dict[str, Any] | None = None
) -> dict[str, Any]:
    options = options or {}
    _category, _analysis, annotate = build_execute_code_context(code, options)

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

    if options.get("timeout_seconds") is not None:
        return gui_timeout_not_supported_response(annotate)

    read_only = bool(options.get("read_only", False))
    blocked = geometry_loop_block_response(
        annotate,
        code=code,
        execution_mode=execution_mode,
        read_only=read_only,
        allow_gui_loop=bool(options.get("allow_gui_geometry_loop", False)),
    )
    if blocked is not None:
        return blocked

    blocked = boolean_audit_block_response(annotate, code=code, read_only=read_only)
    if blocked is not None:
        return blocked

    def execute_code_gui_task():
        return run_execute_code_gui_task(
            code,
            options,
            collect_invalid_objects_fn=self._collect_invalid_objects,
        )

    res = self._dispatch_gui(execute_code_gui_task, _rpc_mod().FreeCADRPC.EXECUTE_TIMEOUT)
    if isinstance(res, str):
        return annotate({"success": False, "error": res, "is_error": True})
    return finalize_gui_execute_response(annotate, res, options)
