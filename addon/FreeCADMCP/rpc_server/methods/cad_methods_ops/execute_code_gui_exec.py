"""Python execution capture for GUI execute_code (Phase 4 slice 4F)."""

from __future__ import annotations

import contextlib
import io
import sys
import traceback

import FreeCAD


def run_python_on_gui_thread(code: str, output_buffer: io.StringIO) -> tuple[bool, dict | None]:
    try:
        with contextlib.redirect_stdout(output_buffer):
            exec(code, globals())
        FreeCAD.Console.PrintMessage("Python code executed successfully.\n")
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
        FreeCAD.Console.PrintError(f"Error executing Python code: {exc}\n")
        return False, tb_info
