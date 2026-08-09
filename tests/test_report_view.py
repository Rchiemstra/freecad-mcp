"""Unit tests for Report view reader."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.helpers import runtime_bootstrap  # noqa: F401

pytestmark = pytest.mark.unit


class _TextEdit:
    def __init__(self, text: str):
        self._text = text
        self.cleared = False

    def toPlainText(self):
        return self._text

    def clear(self):
        self.cleared = True
        self._text = ""


def test_get_report_view_returns_tail_and_optional_clear(monkeypatch):
    from addon.FreeCADMCP.rpc_server.gui_tools_ops import report_view as module

    report = _TextEdit("\n".join(f"line-{i}" for i in range(5)))
    main = MagicMock()
    main.findChild.return_value = report
    freecad_gui = SimpleNamespace(getMainWindow=lambda: main)
    monkeypatch.setattr(module, "FreeCADGui", freecad_gui)
    monkeypatch.setattr(module, "QtWidgets", SimpleNamespace(QTextEdit=object))

    result = module.get_report_view(max_lines=2, clear=True)

    assert result["ok"] is True
    assert result["text"] == "line-3\nline-4"
    assert result["line_count"] == 2
    assert result["total_lines"] == 5
    assert result["truncated"] is True
    assert result["cleared"] is True
    assert report.cleared is True


def test_get_report_view_missing_widget(monkeypatch):
    from addon.FreeCADMCP.rpc_server.gui_tools_ops import report_view as module

    main = MagicMock()
    main.findChild.return_value = None
    freecad_gui = SimpleNamespace(getMainWindow=lambda: main)
    monkeypatch.setattr(module, "FreeCADGui", freecad_gui)
    monkeypatch.setattr(module, "QtWidgets", SimpleNamespace(QTextEdit=object))

    result = module.get_report_view()

    assert result["ok"] is False
    assert result["error_code"] == "REPORT_VIEW_UNAVAILABLE"
