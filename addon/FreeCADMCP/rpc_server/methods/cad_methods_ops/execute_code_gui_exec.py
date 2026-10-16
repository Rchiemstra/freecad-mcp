"""Python execution capture for GUI execute_code (Phase 4 slice 4F)."""

from __future__ import annotations

import contextlib
import io
import sys
import traceback

try:
    from ...._shared.protocol.execution_diagnostics import execution_diagnostics
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from _shared.protocol.execution_diagnostics import execution_diagnostics


@contextlib.contextmanager
def observe_recompute_calls():
    """Observe calls without replacing native Document methods or running them."""
    calls = []
    previous = sys.getprofile()

    def profile(frame, event, arg):
        name = getattr(arg, "__name__", None) if event == "c_call" else (
            frame.f_code.co_name if event == "call" else None
        )
        if name == "recompute" and not calls:
            calls.append("recompute")
        if previous is not None:
            previous(frame, event, arg)

    sys.setprofile(profile)
    try:
        yield calls
    finally:
        sys.setprofile(previous)


def run_python_on_gui_thread(
    code: str, output_buffer: io.StringIO, *, freecad
) -> tuple[bool, dict | None]:
    try:
        execution_globals = globals()
        execution_globals["FreeCAD"] = freecad
        with contextlib.redirect_stdout(output_buffer):
            exec(code, execution_globals)
        freecad.Console.PrintMessage("Python code executed successfully.\n")
        return True, None
    except Exception as exc:
        exc_type, exc_val, exc_tb = sys.exc_info()
        frames = traceback.extract_tb(exc_tb) if exc_tb else []
        last = frames[-1] if frames else None
        tb_info = {
            "exception_type": exc_type.__name__ if exc_type else "Exception",
            "message": str(exc_val),
            "traceback": traceback.format_exc(),
            "frames": [
                {
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": frame.name,
                    "code": frame.line,
                }
                for frame in frames
            ],
            "line_number": last.lineno if last else None,
            "line_code": last.line if last else None,
            "stdout": output_buffer.getvalue(),
        }
        diagnostic = execution_diagnostics({"message": str(exc), "traceback": tb_info})
        freecad.Console.PrintError(f"Error executing Python code: {diagnostic['message']}\n")
        return False, tb_info
