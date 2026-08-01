from __future__ import annotations

import builtins
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _init_gui_path() -> Path:
    return Path(__file__).parents[1] / "addon" / "FreeCADMCP" / "InitGui.py"


def _exec_init_gui(
    monkeypatch,
    *,
    run_timers: bool = True,
    workbench_append: Callable[[str, list[str]], None] | None = None,
    on_rpc_server_import: Callable[[], None] | None = None,
    timeline: list[str] | None = None,
) -> dict[str, Any]:
    """Load InitGui.py the way FreeCAD does: injected globals, empty locals."""

    calls: list[str] = []
    warnings: list[str] = []
    workbenches: list[Any] = []
    events: list[str] = timeline if timeline is not None else []

    class Signal:
        def __init__(self) -> None:
            self.callbacks: list[Any] = []

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
            if run_timers:
                callback()

    qt_core = types.SimpleNamespace(
        QCoreApplication=QCoreApplication,
        QTimer=QTimer,
    )
    pyside = types.ModuleType("PySide")
    pyside.QtCore = qt_core
    monkeypatch.setitem(sys.modules, "PySide", pyside)

    def _record_register_commands() -> None:
        events.append("register_commands")

    rpc_api = types.SimpleNamespace(
        load_settings=lambda: {"auto_start_rpc": False},
        start_rpc_server=lambda: "started",
        initialize_document_lease_runtime=lambda: calls.append("runtime"),
        shutdown_document_lease_runtime=lambda: calls.append("shutdown"),
    )
    rpc_package = types.ModuleType("rpc_server")

    def _rpc_server_import_side_effect() -> None:
        _record_register_commands()
        if on_rpc_server_import is not None:
            on_rpc_server_import()

    real_import = builtins.__import__

    def tracking_import(
        name,
        globals=None,
        locals=None,
        fromlist=(),
        level=0,
    ):
        result = real_import(name, globals, locals, fromlist, level)
        if name == "rpc_server" and "rpc_server" in fromlist:
            _rpc_server_import_side_effect()
        return result

    monkeypatch.setattr(builtins, "__import__", tracking_import)
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
        def appendToolbar(self, _name, _commands) -> None:
            events.append("append_toolbar")
            if workbench_append is not None:
                workbench_append("append_toolbar", _commands)

        def appendMenu(self, _name, _commands) -> None:
            events.append("append_menu")
            if workbench_append is not None:
                workbench_append("append_menu", _commands)

    def add_workbench(workbench) -> None:
        workbenches.append(workbench)

    gui = types.SimpleNamespace(addWorkbench=add_workbench)
    freecad = types.SimpleNamespace(Console=Console)
    init_gui = _init_gui_path()
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

    return {
        "application": application,
        "calls": calls,
        "warnings": warnings,
        "workbenches": workbenches,
        "timeline": events,
        "rpc_api": rpc_api,
        "lease_observer": lease_observer,
    }


def test_init_gui_callbacks_work_with_split_exec_namespaces(monkeypatch) -> None:
    """FreeCAD may exec InitGui.py with distinct globals and locals mappings."""

    context = _exec_init_gui(monkeypatch)

    assert context["warnings"] == []
    assert context["calls"] == [
        "runtime",
        "git_observer",
        "lease_observer",
        "document_lock",
    ]
    assert context["application"].aboutToQuit.callbacks == [
        context["rpc_api"].shutdown_document_lease_runtime,
        context["lease_observer"].unregister_observer,
    ]


def test_initialize_registers_commands_before_toolbar(monkeypatch) -> None:
    """Initialize must import rpc_server (register commands) before UI append."""

    timeline: list[str] = []

    context = _exec_init_gui(
        monkeypatch,
        run_timers=False,
        timeline=timeline,
    )

    assert context["workbenches"], "InitGui should register a workbench"
    context["workbenches"][0].Initialize()

    # Single shared timeline: import side effect and toolbar/menu hooks must
    # interleave in real call order. Concatenating separate lists would
    # false-pass even if append ran before register_commands.
    assert timeline == [
        "register_commands",
        "append_toolbar",
        "append_menu",
    ]
    assert timeline.index("register_commands") < timeline.index("append_toolbar")
