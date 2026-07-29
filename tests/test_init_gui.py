from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path


def test_init_gui_callbacks_work_with_split_exec_namespaces(monkeypatch) -> None:
    """FreeCAD may exec InitGui.py with distinct globals and locals mappings."""

    calls: list[str] = []
    warnings: list[str] = []

    class Signal:
        def __init__(self) -> None:
            self.callbacks = []

        def connect(self, callback) -> None:
            self.callbacks.append(callback)

    class Application:
        def __init__(self) -> None:
            self.aboutToQuit = Signal()

    application = Application()

    class QCoreApplication:
        @staticmethod
        def instance():
            return application

    class QTimer:
        @staticmethod
        def singleShot(_delay, callback) -> None:
            callback()

    qt_core = types.SimpleNamespace(
        QCoreApplication=QCoreApplication,
        QTimer=QTimer,
    )
    pyside = types.ModuleType("PySide")
    pyside.QtCore = qt_core
    monkeypatch.setitem(sys.modules, "PySide", pyside)

    rpc_api = types.SimpleNamespace(
        load_settings=lambda: {"auto_start_rpc": False},
        start_rpc_server=lambda: "started",
        initialize_document_lease_runtime=lambda: calls.append("runtime"),
        shutdown_document_lease_runtime=lambda: calls.append("shutdown"),
    )
    rpc_package = types.ModuleType("rpc_server")
    rpc_package.rpc_server = rpc_api
    monkeypatch.setitem(sys.modules, "rpc_server", rpc_package)

    git_sidecar = types.ModuleType("git_sidecar")
    git_sidecar.register_observer = lambda: calls.append("git_observer")
    monkeypatch.setitem(sys.modules, "git_sidecar", git_sidecar)

    document_lease = types.ModuleType("document_lease")
    document_lease.__path__ = []
    lease_observer = types.ModuleType("document_lease.observer")
    lease_observer.register_observer = (
        lambda notification_callback=None: calls.append("lease_observer") or object()
    )
    lease_observer.unregister_observer = lambda: calls.append("lease_unregister")
    monkeypatch.setitem(sys.modules, "document_lease", document_lease)
    monkeypatch.setitem(sys.modules, "document_lease.observer", lease_observer)

    document_lock = types.ModuleType("document_lock")
    document_lock.register_lock_feature = lambda: calls.append("document_lock")
    monkeypatch.setitem(sys.modules, "document_lock", document_lock)

    class Console:
        @staticmethod
        def PrintMessage(_message) -> None:
            pass

        @staticmethod
        def PrintWarning(message) -> None:
            warnings.append(message)

    class Workbench:
        pass

    gui = types.SimpleNamespace(addWorkbench=lambda _workbench: None)
    freecad = types.SimpleNamespace(Console=Console)
    init_gui = (
        Path(__file__).parents[1] / "addon" / "FreeCADMCP" / "InitGui.py"
    )
    script_globals = {
        "__builtins__": builtins.__dict__,
        "__file__": str(init_gui),
        "FreeCAD": freecad,
        "Gui": gui,
        "Workbench": Workbench,
    }

    exec(
        compile(init_gui.read_bytes(), str(init_gui), "exec"),
        script_globals,
        {},
    )

    assert warnings == []
    assert calls == ["runtime", "git_observer", "lease_observer", "document_lock"]
    assert application.aboutToQuit.callbacks == [
        rpc_api.shutdown_document_lease_runtime,
        lease_observer.unregister_observer,
    ]
