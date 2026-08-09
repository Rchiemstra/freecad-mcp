"""Read FreeCAD Report view (Console dock) text for MCP diagnostics."""

from __future__ import annotations

from typing import Any

import FreeCADGui
from PySide import QtWidgets


def get_report_view(*, max_lines: int | None = 200, clear: bool = False) -> dict[str, Any]:
    """Return the Report view plain text, optionally truncated and cleared."""

    main_window = FreeCADGui.getMainWindow()
    if main_window is None:
        return {
            "ok": False,
            "error_code": "REPORT_VIEW_UNAVAILABLE",
            "error": "FreeCAD main window is not available",
        }

    report = main_window.findChild(QtWidgets.QTextEdit, "Report view")
    if report is None:
        return {
            "ok": False,
            "error_code": "REPORT_VIEW_UNAVAILABLE",
            "error": 'Report view widget not found (objectName "Report view")',
        }

    text = str(report.toPlainText() or "")
    if clear:
        clear_method = getattr(report, "clear", None)
        if callable(clear_method):
            clear_method()

    lines = text.splitlines()
    total_lines = len(lines)
    truncated = False
    if max_lines is not None and max_lines > 0 and total_lines > max_lines:
        lines = lines[-max_lines:]
        truncated = True

    return {
        "ok": True,
        "text": "\n".join(lines),
        "line_count": len(lines),
        "total_lines": total_lines,
        "truncated": truncated,
        "cleared": bool(clear),
    }


__all__ = ["get_report_view"]
