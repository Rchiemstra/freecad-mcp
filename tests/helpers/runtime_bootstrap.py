"""Bootstrap optional FreeCAD/Qt modules for mock-based unit tests.

The MCP unit-test CI job runs under plain CPython (no FreeCAD install). A few
modules under test import ``PySide`` (FreeCAD's Qt binding alias) and some test
files import ``FreeCADGui`` only to provide ``addCommand``. Install lightweight
stubs/shims before those imports run.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


def ensure_freecad_gui_stub() -> None:
    try:
        import FreeCADGui  # noqa: F401
    except ModuleNotFoundError:
        gui = types.ModuleType("FreeCADGui")
        gui.addCommand = lambda *_args, **_kwargs: None
        gui.Selection = MagicMock()
        sys.modules["FreeCADGui"] = gui


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


def bootstrap_unit_test_runtime() -> None:
    ensure_freecad_gui_stub()
    ensure_pyside_shim()


bootstrap_unit_test_runtime()
