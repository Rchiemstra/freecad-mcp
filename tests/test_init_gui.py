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
    auto_start: bool = False,
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

    def stop_rpc_server(*, wait_for_completion=False):
        assert wait_for_completion is True
        calls.append("stop")
        return "stopped"

    rpc_api = types.SimpleNamespace(
        load_settings=lambda: {"auto_start_rpc": auto_start},
        start_rpc_server=lambda: calls.append("start") or "started",
        stop_rpc_server=stop_rpc_server,
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

    script_locals: dict[str, Any] = {}
    exec(
        compile(init_gui.read_bytes(), str(init_gui), "exec"),
        script_globals,
        script_locals,
    )

    return {
        "application": application,
        "calls": calls,
        "warnings": warnings,
        "workbenches": workbenches,
        "timeline": events,
        "rpc_api": rpc_api,
        "freecad": freecad,
        "gui": gui,
        "script_locals": script_locals,
    }


def test_init_gui_callbacks_work_with_split_exec_namespaces(monkeypatch) -> None:
    """FreeCAD may exec InitGui.py with distinct globals and locals mappings."""

    context = _exec_init_gui(monkeypatch)

    assert context["warnings"] == []
    assert context["calls"] == ["git_observer"]
    callbacks = context["application"].aboutToQuit.callbacks
    assert len(callbacks) == 1

    callbacks[0]()
    assert context["calls"][-1:] == ["stop"]


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


def test_auto_start_and_about_to_quit_share_one_root_without_duplicate_callback(
    monkeypatch,
) -> None:
    context = _exec_init_gui(monkeypatch, auto_start=True)

    assert context["calls"][:2] == ["start", "git_observer"]
    callbacks = context["application"].aboutToQuit.callbacks
    connect_shutdown = context["script_locals"][
        "_connect_rpc_runtime_shutdown"
    ]
    connect_shutdown(context["rpc_api"])

    assert context["application"].aboutToQuit.callbacks == callbacks
    assert len(callbacks) == 1
    callbacks[0]()
    assert context["calls"][-1:] == ["stop"]


def test_init_gui_does_not_start_lease_runtime_or_register_authority_observers(
    monkeypatch,
) -> None:
    _exec_init_gui(monkeypatch)

    source = _init_gui_path().read_text(encoding="utf-8")
    assert "initialize_document_lease_runtime" not in source
    assert "document_lease.observer" not in source
    assert "register_lock_feature" not in source
