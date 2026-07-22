"""Bootstrap optional FreeCAD/Qt modules for mock-based unit tests.

The MCP unit-test CI job runs under plain CPython (no FreeCAD install). Addon
and test modules import FreeCAD-family modules at import time; install lightweight
stubs/shims before collection when the real modules are unavailable.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


def _vector_mock(*_args, **_kwargs):
    vec = MagicMock()
    vec.x = vec.y = vec.z = 0
    return vec


def ensure_freecad_stub() -> None:
    try:
        import FreeCAD  # noqa: F401
    except ModuleNotFoundError:
        fc = types.ModuleType("FreeCAD")
        # E2E tests use this explicit marker to distinguish the lightweight
        # collection-time shim from a real FreeCAD runtime.  A MagicMock may
        # otherwise satisfy ``pytest.importorskip`` and make a host lifecycle
        # test execute against recursive, non-serializable mock objects.
        fc.__mcp_test_stub__ = True
        console = MagicMock()
        console.PrintMessage = MagicMock()
        console.PrintWarning = MagicMock()
        console.PrintError = MagicMock()
        fc.Console = console
        fc.ActiveDocument = None
        fc.getUserAppDataDir = lambda: "/tmp"
        fc.listDocuments = lambda: {}
        fc.getDocument = MagicMock(side_effect=KeyError("document"))
        fc.setActiveDocument = MagicMock()
        fc.newDocument = MagicMock()
        fc.closeDocument = MagicMock()
        fc.openDocument = MagicMock()
        fc.Version = ("0", "21", "0", "stub")
        fc.Vector = MagicMock(side_effect=_vector_mock)
        fc.Placement = MagicMock()
        fc.Rotation = MagicMock()
        fc.ParamGet = MagicMock(return_value=MagicMock())
        fc.Units = MagicMock()
        fc.Document = MagicMock()
        fc.DocumentObject = MagicMock()
        sys.modules["FreeCAD"] = fc


def ensure_freecad_gui_stub() -> None:
    try:
        import FreeCADGui  # noqa: F401
    except ModuleNotFoundError:
        gui = types.ModuleType("FreeCADGui")
        gui.addCommand = lambda *_args, **_kwargs: None
        gui.Selection = MagicMock()
        gui.activeDocument = MagicMock(return_value=None)
        sys.modules["FreeCADGui"] = gui


def ensure_objects_fem_stub() -> None:
    try:
        import ObjectsFem  # noqa: F401
    except ModuleNotFoundError:
        sys.modules["ObjectsFem"] = types.ModuleType("ObjectsFem")


def ensure_pyside_shim() -> None:
    if "PySide" in sys.modules:
        return
    try:
        import PySide  # noqa: F401
    except ModuleNotFoundError:
        pass
    else:
        return

    try:
        import PySide6.QtCore as qt_core
    except ModuleNotFoundError:
        return

    pyside = types.ModuleType("PySide")
    pyside.QtCore = qt_core
    sys.modules["PySide"] = pyside
    sys.modules["PySide.QtCore"] = qt_core

    # Headless CI images often lack libGL; rpc_server only needs QtWidgets at runtime.
    qt_widgets = types.ModuleType("PySide.QtWidgets")
    qapp = MagicMock()
    qapp.instance = MagicMock(return_value=None)
    qt_widgets.QApplication = qapp
    qt_widgets.QInputDialog = MagicMock()
    qt_widgets.QLineEdit = MagicMock()
    qt_widgets.QMessageBox = MagicMock()
    qt_widgets.QAction = MagicMock()
    pyside.QtWidgets = qt_widgets
    sys.modules["PySide.QtWidgets"] = qt_widgets


def bootstrap_unit_test_runtime() -> None:
    ensure_freecad_stub()
    ensure_freecad_gui_stub()
    ensure_objects_fem_stub()
    ensure_pyside_shim()


bootstrap_unit_test_runtime()
