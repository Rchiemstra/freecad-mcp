"""GUI-thread detection must match the C++ ``DocumentWouldBlock`` rule.

FreeCAD refuses synchronous document calls only on the main thread of a
process whose GUI is up.  The Python side picks the async commit path from the
same question, so a bare ``QCoreApplication`` (FreeCADCmd, or an earlier test
in the same process) must not turn every main-thread caller into a "GUI
thread" that receives a pending waiter instead of a terminal result.
"""

from __future__ import annotations

import importlib
import sys
import threading
import types

import pytest

pytestmark = pytest.mark.unit

QtCore = pytest.importorskip("PySide6.QtCore")


def _detectors() -> tuple[object, object]:
    collaboration_api = importlib.import_module("addon.FreeCADMCP.collaboration_api")
    native_commit_wait = importlib.import_module(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.native_commit_wait"
    )
    return collaboration_api._is_freecad_gui_thread, native_commit_wait._on_gui_thread


@pytest.fixture
def qt_main_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run with a real QCoreApplication owned by this (main) thread."""

    QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    pyside = types.ModuleType("PySide")
    pyside.QtCore = QtCore
    monkeypatch.setitem(sys.modules, "PySide", pyside)
    monkeypatch.setitem(sys.modules, "PySide.QtCore", QtCore)
    monkeypatch.setitem(sys.modules, "PySide2", None)
    monkeypatch.setitem(sys.modules, "PySide2.QtCore", None)


def _install_freecad(monkeypatch: pytest.MonkeyPatch, gui_up: object) -> None:
    freecad = types.ModuleType("FreeCAD")
    freecad.GuiUp = gui_up
    monkeypatch.setitem(sys.modules, "FreeCAD", freecad)


def _off_main_thread(check) -> bool:
    seen: list[bool] = []
    worker = threading.Thread(target=lambda: seen.append(check()))
    worker.start()
    worker.join(10)
    return seen[0]


def test_main_thread_of_a_running_freecad_gui_is_the_gui_thread(
    qt_main_thread: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_freecad(monkeypatch, 1)

    for check in _detectors():
        assert check() is True
        assert _off_main_thread(check) is False


@pytest.mark.parametrize("gui_up", [0, False])
def test_bare_qcoreapplication_without_freecad_gui_is_not_the_gui_thread(
    qt_main_thread: None, monkeypatch: pytest.MonkeyPatch, gui_up: object
) -> None:
    _install_freecad(monkeypatch, gui_up)

    for check in _detectors():
        assert check() is False


def test_missing_freecad_module_is_not_the_gui_thread(
    qt_main_thread: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "FreeCAD", None)

    for check in _detectors():
        assert check() is False
