"""Part 3 document lifecycle behavior against the native FreeCAD contract."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from addon.FreeCADMCP.rpc_server.methods.lifecycle_methods_ops import document_gui

pytestmark = pytest.mark.unit


class _FreeCADDocuments:
    def __init__(self, *names: str) -> None:
        self._documents = {name: object() for name in names}
        self.Console = SimpleNamespace(PrintMessage=MagicMock())

    def listDocuments(self):
        return dict(self._documents)

    def getDocument(self, name: str):
        try:
            return self._documents[name]
        except KeyError:
            raise NameError(f"Unknown document '{name}'") from None

    def closeDocument(self, name: str) -> None:
        self._documents.pop(name)


def test_close_open_document_reports_success_after_native_nameerror(monkeypatch) -> None:
    freecad = _FreeCADDocuments("Model")
    monkeypatch.setattr(document_gui, "FreeCAD", freecad)

    result = document_gui.close_document_gui(object(), "Model")

    assert result == {
        "success": True,
        "document_name": "Model",
        "result": True,
    }
    assert "Model" not in freecad.listDocuments()


def test_close_absent_document_reports_document_not_found(monkeypatch) -> None:
    freecad = _FreeCADDocuments()
    monkeypatch.setattr(document_gui, "FreeCAD", freecad)

    result = document_gui.close_document_gui(object(), "Missing")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
